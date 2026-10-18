import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from models.schemas import QueryRequest
from services.retrieval import retrieval_question, retrieve, select_documents


def request(question, questions, **kwargs):
    history = []
    for question_in_history in questions:
        history.extend([{'role': 'user', 'content': question_in_history},
                        {'role': 'assistant', 'content': 'Untrusted earlier answer.'}])
    return QueryRequest(question=question, chat_history=history, **kwargs)


@pytest.mark.parametrize('question,history,expected', [
    ('next section', ['Explain section 3.2.1', 'next section'], 'section 3.2.3'),
    ('previous section', ['Explain section 3.2.3', 'previous section'], 'section 3.2.1'),
    ('explain this', ['Explain section 3.2.1', 'next section', 'next section'], 'section 3.2.3'),
])
def test_repeated_nested_section_navigation(question, history, expected):
    assert expected in retrieval_question(request(question, history))


def test_navigation_retains_original_subject_after_six_exchanges():
    questions = ['Explain section 3.2.1'] + ['next section'] * 5
    assert 'section 3.2.7' in retrieval_question(request('next section', questions))


def test_chapter_navigation_survives_intervening_regulation_explanation():
    questions=['What is in chapter 1?', 'Regulation 2: Definitions explain', 'explain that in simpler words']
    resolved=retrieval_question(request('what is in the next chapter and when are annual returns due?',questions))
    assert 'chapter 2' in resolved and 'regulation 3' not in resolved.lower()


def test_decimal_reference_comparison_does_not_include_parent_section():
    doc = {'id': 'a', 'name': 'manual.pdf', 'dataset_name': 'a', 'extracted_text':
           '3. General\nUnrelated general rule.\n'
           '3.2 Isolation\nDisconnect power.\n3.3 Inspection\nInspect the guard.\n'
           '3.4 Restart\nReapply power.'}
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve('Compare sections 3.2 and 3.3', [doc]))
    joined = ' '.join(c.text for c in chunks)
    assert 'Disconnect power' in joined and 'Inspect the guard' in joined
    assert 'Unrelated general rule' not in joined and 'Reapply power' not in joined


DOCS = [{'id': 'a', 'name': 'manual.pdf'}, {'id': 'b', 'name': 'audit.pdf'}]


@pytest.mark.parametrize('question,history', [
    ('next section', ['Explain section 3.2.1 in manual.pdf']),
    ('explain this', ['Explain section 3.2.1 in manual.pdf', 'next section']),
    ('Explain section 4', ['Explain section 3.2.1 in manual.pdf']),
    ('next section', ['Explain section 3.2.1 in manual.pdf'] + ['next section'] * 5),
])
def test_auto_scope_does_not_expand_during_navigation(question, history):
    req = request(question, history, scope_mode='auto')
    assert select_documents(req, DOCS) == DOCS[:1]


def test_auto_comparison_includes_prior_and_new_document():
    req = request('Compare this with the controls in audit.pdf',
                  ['Explain the controls in manual.pdf'], scope_mode='auto')
    assert select_documents(req, DOCS) == DOCS


def test_new_named_document_replaces_auto_scope():
    req = request('Explain section 2 in audit.pdf',
                  ['Explain section 1 in manual.pdf'], scope_mode='auto')
    assert select_documents(req, DOCS) == DOCS[1:]


def test_selected_scope_cannot_be_expanded_by_history_or_comparison():
    req = request('Compare this with audit.pdf', ['Explain manual.pdf'],
                  scope_mode='selected', document_ids=['a'])
    assert select_documents(req, DOCS) == DOCS[:1]


def test_all_scope_ignores_previous_filename_focus():
    req = request('next section', ['Explain section 1 in manual.pdf'], scope_mode='all')
    assert select_documents(req, DOCS) == DOCS


def test_long_history_subject_is_part_of_cache_identity():
    from api.query import cache_key
    doc = {**DOCS[0], 'status': 'ingested'}
    recent = ['next section'] * 5
    first = request('next section', ['Explain section 3.2.1', *recent])
    second = request('next section', ['Explain section 4.2.1', *recent])
    assert retrieval_question(first) != retrieval_question(second)
    assert cache_key('u', first, [doc]) != cache_key('u', second, [doc])


def test_navigation_does_not_reuse_reference_from_another_document():
    req=request('next chapter',['Explain chapter 1 in manual.pdf','Explain section 2 in audit.pdf'])
    assert retrieval_question(req)=='next chapter'


def test_answer_question_uses_resolved_navigation_target():
    from api.query import answer_question
    req=request('what is in the next chapter?', ['Explain chapter 1','Explain regulation 2'])
    assert answer_question(req.question,retrieval_question(req))=='what is in the chapter 2?'


def test_named_document_comparison_uses_the_correct_reference_from_each():
    docs = [{**DOCS[0], 'dataset_name': 'a', 'extracted_text':
             '1. Isolation\nDisconnect the motor.\n2. Inspection\nInspect the guard.'},
            {**DOCS[1], 'dataset_name': 'b', 'extracted_text':
             '1. Scope\nAudit scope only.\n2. Findings\nThe guard was missing.'}]
    req = request('Compare this with section 2 in audit.pdf',
                  ['Explain section 1 in manual.pdf'], scope_mode='auto')
    selected = select_documents(req, docs)
    resolved = retrieval_question(req, selected)
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve(resolved, selected))
    assert {c.document_id for c in chunks} == {'a', 'b'}
    joined = ' '.join(c.text for c in chunks)
    assert 'Disconnect the motor' in joined and 'guard was missing' in joined
    assert 'Inspect the guard' not in joined and 'Audit scope only' not in joined


def test_named_reference_outside_selected_scope_does_not_use_wrong_document():
    doc = {**DOCS[0], 'dataset_name': 'a', 'extracted_text': '2. Inspection\nInspect the guard.'}
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve('Explain section 2 in audit.pdf', [doc]))
    assert chunks == []


def test_reference_binding_accepts_document_names_with_spaces():
    doc = {'id': 'a', 'name': 'Equipment Manual.pdf', 'dataset_name': 'a',
           'extracted_text': '2. Inspection\nInspect the guard.'}
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve('Explain section 2 in Equipment Manual.pdf', [doc]))
    assert chunks and all(c.document_id == 'a' for c in chunks)


@pytest.mark.parametrize('question,history,expected', [
    ('next section', ['Explain section 3.2'], 'section 4.0'),
    ('previous section', ['Explain section 4.0'], 'section 3.2'),
    ('next section', ['Explain section 3.1', 'next section'], 'section 4.0'),
])
def test_navigation_follows_existing_headings_across_boundaries(question, history, expected):
    doc = {'id': 'a', 'name': 'manual.pdf', 'extracted_text':
           '3.1 Isolation\nDisconnect.\n3.1.1 Locks\nLock out.\n'
           '3.2 Testing\nTest.\n4.0 Records\nRecord.'}
    assert expected in retrieval_question(request(question, history), [doc])


def test_navigation_at_end_or_ambiguous_documents_stays_unresolved():
    doc = {'id': 'a', 'name': 'manual.pdf', 'extracted_text': '1. First\nFirst.\n3. Last\nLast.'}
    assert retrieval_question(request('next section', ['Explain section 3']), [doc]) == 'next section'
    other = {**doc, 'id': 'b', 'name': 'other.pdf'}
    assert retrieval_question(request('next section', ['Explain section 1']), [doc, other]) == 'next section'


def test_explicit_reference_does_not_jump_to_nearest_existing_heading():
    doc = {'id': 'a', 'name': 'manual.pdf', 'extracted_text': '1. First\nFirst.\n3. Last\nLast.'}
    assert retrieval_question(request('Explain section 2', ['Explain section 1']), [doc]) == 'Explain section 2'


def test_next_after_two_reference_comparison_needs_a_target():
    doc = {'id': 'a', 'name': 'manual.pdf', 'extracted_text':
           '1. First\nFirst.\n2. Second\nSecond.\n3. Third\nThird.'}
    req = request('next section', ['Compare section 1 with section 2'])
    assert retrieval_question(req, [doc]) == 'next section'


def test_cross_document_comparison_preserves_filename_with_spaces():
    docs = [{'id': 'a', 'name': 'Equipment Manual.pdf', 'dataset_name': 'a',
             'extracted_text': '1. Procedure\nIsolate the motor.\n2. Other\nOther manual text.'},
            {'id': 'b', 'name': 'Safety Audit.pdf', 'dataset_name': 'b',
             'extracted_text': '1. Other\nOther audit text.\n2. Finding\nThe switch was damaged.'}]
    req = request('Compare this with section 2 in Safety Audit.pdf',
                  ['Explain section 1 in Equipment Manual.pdf'], scope_mode='auto')
    resolved = retrieval_question(req, select_documents(req, docs))
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve(resolved, docs))
    joined = ' '.join(c.text for c in chunks)
    assert 'Isolate the motor' in joined and 'switch was damaged' in joined
    assert 'Other manual text' not in joined and 'Other audit text' not in joined


def test_query_uses_observed_navigation_target_and_clarifies_at_end(user):
    import json
    from api import query
    from test_query_contract import AnswerClient
    doc = {'id': 'a', 'name': 'manual.pdf', 'dataset_name': 'a', 'status': 'ingested',
           'extracted_text': '3.2 Inspection\nInspect.\n4.0 Records\nRecord the inspection.'}
    client = AnswerClient({'status': 'source_excerpts', 'claims': [
        {'source_ids': ['SRC_1'], 'text': 'Record the inspection.'}]})
    with patch.object(query, 'active_documents', return_value=[doc]), patch.object(query, 'save_chat_turn'), \
         patch.object(query, 'create_llm_client', return_value=client), \
         patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        result = asyncio.run(query.query_ai(request('next section', ['Explain section 3.2']), user))
        payload = json.loads(client.create.call_args.kwargs['messages'][1]['content'])
        assert payload['question'] == 'section 4.0'
        assert result.sources[0].section == 'Section 4.0'
        client.create.reset_mock()
        end = asyncio.run(query.query_ai(request('next section', ['Explain section 4.0']), user))
        assert end.evidence_status == 'not_required' and 'Which topic' in end.answer
        client.create.assert_not_called()
