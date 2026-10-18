"""Accident evidence must retain the distinction between events and reconstruction."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from api.query import explained_sources
from models.schemas import QueryRequest
from services.evidence import document_chunks
from services.retrieval import FOLLOWUP_CONTEXT, retrieval_question, select_documents
from services.retrieval import lexical_ranking, retrieve


def report(text, *, name='incident-notes.pdf', doc_id='incident'):
    return {'id': doc_id, 'name': name, 'dataset_name': doc_id,
            'status': 'ingested', 'extracted_text': text}


MIXED_REPORT = (
    '[PDF page 6]\n'
    'Accident Reenactment  After the switch was repaired, the truck was tested. '
    'During the reenactment, the truck moved forward on the grade during loading.\n'
    'Training and Experience  The operator had seven years of mining experience.\n'
    'ROOT CAUSE ANALYSIS\n'
    'Inadequate task training caused the operator to use an unsafe parking procedure.\n'
    'CONCLUSION\n'
    'Failure to chock the wheels was contributory.\n'
    '[PDF page 7]\n'
    'ENFORCEMENT ACTIONS\n'
    'The operator was instructed to correct the inspection procedure.\n'
)


def test_report_sections_do_not_mix_reenactment_with_actual_causal_findings():
    chunks = document_chunks(report(MIXED_REPORT))
    reenactment = next(c for c in chunks if 'After the switch was repaired' in c.text)
    training = next(c for c in chunks if 'seven years' in c.text)
    cause = next(c for c in chunks if 'Inadequate task training caused' in c.text)
    conclusion = next(c for c in chunks if 'Failure to chock' in c.text)
    assert len({c.id for c in (reenactment, training, cause, conclusion)}) == 4
    assert reenactment.section == 'Accident Reenactment'
    assert training.section == 'Training and Experience'
    assert cause.section == 'ROOT CAUSE ANALYSIS'
    assert conclusion.section == 'CONCLUSION'
    assert 'ROOT CAUSE ANALYSIS' not in reenactment.text
    assert 'Training and Experience' not in reenactment.text
    assert 'Failure to chock' not in cause.text


def test_section_split_keeps_immutable_source_offsets_and_pdf_pages():
    chunks = document_chunks(report(MIXED_REPORT))
    assert chunks
    for index, chunk in enumerate(chunks, 1):
        assert chunk.text == MIXED_REPORT[chunk.start:chunk.end]
        source = chunk.source(f'SRC_{index}')
        assert source.excerpt == MIXED_REPORT[source.start_offset:source.end_offset]
        assert source.document_id == 'incident'
        assert source.page == (7 if 'inspection procedure' in chunk.text else 6)
    # Text splitting must never silently discard the inline heading's first sentence.
    assert any('After the switch was repaired, the truck was tested.' in c.text for c in chunks)
    assert any('The operator had seven years of mining experience.' in c.text for c in chunks)


def long_reenactment():
    return (
        '[PDF page 2]\nAccident Reenactment\n'
        + 'The repaired truck was placed at the test location with the engine running. ' * 20
        + '\n[PDF page 3]\nThe truck moved forward during the reconstructed loading test.\n'
        + 'ROOT CAUSE ANALYSIS\nInadequate task training caused the unsafe parking procedure.\n'
    )


def test_reenactment_provenance_survives_chunk_and_page_continuations():
    chunks = document_chunks(report(long_reenactment()), size=400)
    reenactment = [c for c in chunks if 'ROOT CAUSE ANALYSIS' not in c.text]
    assert len(reenactment) > 2
    assert all(c.section == 'Accident Reenactment' for c in reenactment)
    continuation = next(c for c in chunks if 'reconstructed loading test' in c.text)
    assert continuation.page == 3
    assert not continuation.text.startswith('Accident Reenactment')
    cause = next(c for c in chunks if 'Inadequate task training' in c.text)
    assert cause.section == 'ROOT CAUSE ANALYSIS'
    assert cause.page == 3


def test_actual_training_cause_after_reenactment_can_be_explained():
    chunks = document_chunks(report(MIXED_REPORT))
    cause = next(c for c in chunks if 'Inadequate task training caused' in c.text)
    sources, answer = explained_sources({'claims': [{
        'source_ids': ['SRC_1'],
        'text': 'Inadequate task training caused the operator to use an unsafe parking procedure.',
    }]}, {'SRC_1': cause})
    assert 'unsafe parking procedure' in answer
    assert sources[0].section == 'ROOT CAUSE ANALYSIS'
    assert 'reenactment' not in answer.lower()


@pytest.mark.parametrize('add_actual_event_source', [False, True])
def test_unlabeled_reenactment_motion_rejected_even_with_extra_actual_source(add_actual_event_source):
    chunks = document_chunks(report(long_reenactment()), size=400)
    continuation = next(c for c in chunks if 'reconstructed loading test' in c.text)
    actual = document_chunks(report('OVERVIEW\nA miner was injured beside a parked truck.',
                                     doc_id='actual'))[0]
    allowed = {'SRC_1': continuation, 'SRC_2': actual}
    ids = ['SRC_1', 'SRC_2'] if add_actual_event_source else ['SRC_1']
    with pytest.raises(ValueError, match='reenactment'):
        explained_sources({'claims': [{
            'source_ids': ids, 'text': 'The truck moved forward during loading.',
        }]}, allowed)


def test_labeled_reenactment_motion_from_continuation_is_allowed():
    chunks = document_chunks(report(long_reenactment()), size=400)
    continuation = next(c for c in chunks if 'reconstructed loading test' in c.text)
    _, answer = explained_sources({'claims': [{
        'source_ids': ['SRC_1'],
        'text': 'In the reenactment, the truck moved forward during loading.',
    }]}, {'SRC_1': continuation})
    assert 'In the reenactment' in answer


def test_explicit_new_document_resets_unnamed_earlier_topic():
    request = QueryRequest(
        question='In incident-notes.pdf, what happened in this accident?',
        chat_history=[
            {'role': 'user', 'content': 'What should I inspect on the tires?'},
            {'role': 'user', 'content': 'And what brake tests should I perform?'},
        ],
    )
    resolved = retrieval_question(request)
    assert resolved == request.question
    assert 'tires' not in resolved and 'brake tests' not in resolved


def test_document_switch_in_history_resets_unnamed_topic_before_followup():
    request = QueryRequest(question='What caused it?', chat_history=[
        {'role': 'user', 'content': 'What should I inspect on the tires?'},
        {'role': 'user', 'content': 'In incident-notes.pdf, what happened in this accident?'},
    ])
    resolved = retrieval_question(request)
    assert 'incident-notes.pdf' in resolved
    assert 'accident' in resolved
    assert 'tires' not in resolved


def test_same_named_document_keeps_immediate_subject_for_followup():
    request = QueryRequest(question='In incident-notes.pdf, what caused it?', chat_history=[
        {'role': 'user', 'content': 'Describe the parking switch failure in incident-notes.pdf.'},
    ])
    resolved = retrieval_question(request)
    assert FOLLOWUP_CONTEXT in resolved
    assert 'parking switch failure' in resolved


def test_cross_document_comparison_retains_both_subjects_and_auto_scope():
    docs = [report('Brake inspection instructions.', name='inspection-card.pdf', doc_id='card'),
            report('Brake inspection findings.')]
    request = QueryRequest(
        question='Compare that with the brake inspection findings in incident-notes.pdf.',
        scope_mode='auto',
        chat_history=[{'role': 'user', 'content':
                       'Explain the brake inspection instructions in inspection-card.pdf.'}],
    )
    resolved = retrieval_question(request, docs)
    assert 'inspection-card.pdf' in resolved and 'incident-notes.pdf' in resolved
    assert {d['id'] for d in select_documents(request, docs)} == {'card', 'incident'}


def test_cross_document_comparison_keeps_unnamed_immediate_topic():
    request = QueryRequest(
        question='Compare that with the brake findings in incident-notes.pdf.',
        chat_history=[{'role': 'user', 'content': 'What brake inspections are recommended?'}],
    )
    assert 'What brake inspections are recommended?' in retrieval_question(request)


def test_repeated_page_headers_and_callouts_do_not_reset_reenactment():
    text = ('[PDF page 1]\nACCIDENT INVESTIGATION REPORT\nAccident Reenactment\n'
            'The repaired vehicle was tested.\n[PDF page 2]\nACCIDENT INVESTIGATION REPORT\n'
            'WARNING\nThe truck moved forward during loading.\nROOT CAUSE ANALYSIS\n'
            'Lack of training was contributory.')
    chunks = document_chunks(report(text))
    moved = next(c for c in chunks if 'The truck moved' in c.text)
    assert moved.section == 'Accident Reenactment'
    with pytest.raises(ValueError, match='reenactment'):
        explained_sources({'claims':[{'source_ids':['SRC_1'], 'text':'The truck moved forward during loading.'}]}, {'SRC_1':moved})
    assert next(c for c in chunks if 'Lack of training' in c.text).section == 'ROOT CAUSE ANALYSIS'


def test_filename_tokens_do_not_prioritize_cover_details():
    chunks = document_chunks(report('[PDF page 1]\nRedstone 2012\n[PDF page 2]\nThe parking brake failed.'))
    ranked = lexical_ranking(chunks, 'What failed in redstone-2012.pdf?')
    assert ranked[0][0].page == 2


def test_summary_retains_event_and_causal_evidence_despite_semantic_cover_hits():
    text = ('[PDF page 1]\nREPORT OF INVESTIGATION\nInvestigators identified at Cedar Mine.\n'
            '[PDF page 2]\nREPORT OF INVESTIGATION\nInvestigators identified at Cedar Mine.\n'
            '[PDF page 3]\nOVERVIEW\nA vehicle drifted and injured a worker.\n'
            '[PDF page 4]\nROOT CAUSE ANALYSIS\nTraining was inadequate. The parking brake was not repaired.')
    doc = report(text)
    recalled = [{'source':doc['dataset_name'],'text':text[:text.index('[PDF page 3]')]}]
    with patch('services.retrieval.query_memory', AsyncMock(return_value=recalled)):
        chunks, _ = asyncio.run(retrieve('What happened and what contributing factors did investigators identify?', [doc], limit=2))
    assert {c.section for c in chunks} == {'OVERVIEW', 'ROOT CAUSE ANALYSIS'}


@pytest.mark.parametrize('limit', [1, 2, 3])
def test_prioritized_evidence_respects_limit_and_document_coverage(limit):
    docs = [report('OVERVIEW\nA truck drifted.\nROOT CAUSE ANALYSIS\nThe brake was faulty.', doc_id=str(i)) for i in range(3)]
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve('What happened and what contributing factors were identified?', docs, limit=limit))
    assert len(chunks) == limit
    assert len({c.document_id for c in chunks}) == limit
