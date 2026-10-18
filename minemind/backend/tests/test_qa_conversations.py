import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from models.schemas import QueryRequest
from services.retrieval import retrieve, retrieval_question


TEXT = '''[PDF page 1]
CHAPTER I
PRELIMINARY
1. Application.- These rules apply to every coal mine.
2. Definitions.- A manager is an appointed person.
[PDF page 2]
CHAPTER II
NOTICES
3. Opening.- Send written notice before opening.
4. Annual returns.- Send annual returns before February.
[PDF page 3]
CHAPTER XII
VENTILATION
150. Air.- Ventilation shall supply fresh air.
151. Fans.- Inspect ventilation fans every day.
'''
DOC = {'id': 'one', 'name': 'rules.pdf', 'dataset_name': 'owned', 'status': 'ingested', 'extracted_text': TEXT}


@pytest.mark.parametrize('question, history, required, excluded', [
    ('Explain regulation 4', [], 'Annual returns', 'Definitions'),
    (r'\- Regulation 2: Definitions [SRC_2] explain', [], 'Definitions', 'Annual returns'),
    ('what does reg 2 mean?', [], 'Definitions', 'Annual returns'),
    ('What are the requirements in ch 12?', [], 'fresh air', 'Definitions'),
    ('explain more', ['What is in chapter 12?'], 'fresh air', 'Definitions'),
    ('and the next chapter?', ['what is in chapter 1?'], 'Opening', 'Definitions'),
    ('what about chapter II?', [], 'Opening', 'Definitions'),
    ('explain the second one', ['Explain regulation 1', 'What is in chapter I?'], 'Definitions', 'Annual returns'),
    ('Compare regulations 1 and 2', [], 'Definitions', 'Annual returns'),
    ('Compare chapter I and chapter XII', [], 'fresh air', 'Annual returns'),
])
def test_reference_conversations(question, history, required, excluded):
    request = QueryRequest(question=question, chat_history=[{'role': 'user', 'content': h} for h in history])
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve(retrieval_question(request), [DOC]))
    text = '\n'.join(c.text for c in chunks)
    assert required in text
    assert excluded not in text


def test_nonexistent_reference_does_not_retrieve_unrelated_chapter():
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve('Explain chapter 99', [DOC]))
    assert chunks == []


def test_multiline_regulation_heading_keeps_exact_boundaries():
    doc = {**DOC, 'extracted_text': '24. Suspension or cancellation of certificates\nfor managers.- Written notice is required.\n25. Fees.- Pay the fee.'}
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve('Explain regulation 24', [doc]))
    assert chunks and 'Written notice is required' in chunks[0].text
    assert all('25. Fees' not in c.text for c in chunks)


@pytest.mark.parametrize('payload', [[], {}, {'status': 'source_excerpts', 'claims': []},
    {'status': 'made_up', 'claims': []}, {'status': 'source_excerpts', 'claims': [{'source_id': 'secret'}]}])
def test_invalid_provider_output_is_not_missing_document_evidence(user, payload):
    from api import query
    from test_query_contract import AnswerClient
    from services.evidence import document_chunks
    chunks = document_chunks(DOC)
    with patch.object(query, 'active_documents', return_value=[DOC]), \
         patch.object(query, 'save_chat_turn'), \
         patch.object(query, 'retrieve', AsyncMock(return_value=(chunks, {'semantic':'ok'}))), \
         patch.object(query, 'create_llm_client', return_value=AnswerClient(payload)):
        result = asyncio.run(query.query_ai(QueryRequest(question='What does regulation 4 require?'), user))
    assert result.evidence_status == 'partial'
    assert result.sources == []
    assert 'answer service' in result.answer.lower()
    assert result.retrieval_diagnostics['answer_provider'] == 'unavailable'


def test_complete_followup_conversation_uses_resolved_reference(user):
    from api import query
    from test_query_contract import AnswerClient
    model = AnswerClient({'status':'source_excerpts','claims':[{'source_id':'SRC_1'}]})
    history = []
    with patch.object(query, 'active_documents', return_value=[DOC]), \
         patch.object(query, 'save_chat_turn'), \
         patch.object(query, 'create_llm_client', return_value=model):
        for question, expected in [('Explain regulation 4', 'Annual returns'), ('tell me more', 'Annual returns'),
                                   ('what about reg 2?', 'Definitions'), ('explain this', 'Definitions')]:
            result = asyncio.run(query.query_ai(QueryRequest(question=question, chat_history=history,
                scope_mode='selected', document_ids=['one']), user))
            assert result.evidence_status == 'source_excerpts'
            assert expected in result.answer
            for source in result.sources:
                assert TEXT[source.start_offset:source.end_offset] == source.excerpt
            history.extend([{'role':'user','content':question}, {'role':'assistant','content':result.answer}])


def test_ambiguous_followup_asks_for_subject_without_provider(user):
    from api import query
    with patch.object(query, 'active_documents', return_value=[DOC]), patch.object(query, 'save_chat_turn'), \
         patch.object(query, 'create_llm_client') as provider:
        result = asyncio.run(query.query_ai(QueryRequest(question='explain this'), user))
    assert result.evidence_status == 'not_required'
    assert 'Which topic' in result.answer
    provider.assert_not_called()


def test_empty_scope_has_actionable_response_without_provider(user):
    from api import query
    with patch.object(query, 'active_documents', return_value=[]), patch.object(query, 'save_chat_turn'), \
         patch.object(query, 'create_llm_client') as provider:
        result = asyncio.run(query.query_ai(QueryRequest(question='Explain regulations'), user))
    assert 'no available documents' in result.answer
    provider.assert_not_called()


def test_provider_timeout_does_not_claim_information_is_absent(user):
    from api import query
    with patch.object(query, 'active_documents', return_value=[DOC]), patch.object(query, 'save_chat_turn'), \
         patch.object(query, 'create_llm_client', side_effect=TimeoutError):
        result = asyncio.run(query.query_ai(QueryRequest(question='Explain regulation 4'), user))
    assert result.evidence_status == 'partial'
    assert result.sources == []
    assert 'Please retry' in result.answer


def test_context_used_for_retrieval_is_in_cache_key():
    from api.query import cache_key
    recent = [{'role': 'user', 'content': 'tell me more'}] * 7
    first = QueryRequest(question='explain more', chat_history=[{'role':'user','content':'regulation 1'}, *recent])
    second = QueryRequest(question='explain more', chat_history=[{'role':'user','content':'regulation 4'}, *recent])
    assert cache_key('u', first, [DOC]) != cache_key('u', second, [DOC])
