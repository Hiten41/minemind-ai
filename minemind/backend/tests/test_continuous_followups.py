import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from models.schemas import QueryRequest
from services.retrieval import retrieval_question, retrieve


def request(q, history):
    return QueryRequest(question=q,chat_history=[{'role':'user','content':s} for s in history])


def test_successive_next_chapters_advance_not_repeat():
    resolved=retrieval_question(request('and the next chapter?', ['Explain chapter 1','and the next chapter?']))
    assert 'chapter 3' in resolved.lower()


def test_followup_keeps_resolved_navigation_target():
    resolved=retrieval_question(request('explain this', ['Explain chapter 1','and the next chapter?']))
    assert 'chapter 2' in resolved.lower()


def test_comparison_includes_current_and_previous_reference():
    resolved=retrieval_question(request('How does this compare with regulation 4?', ['Explain regulation 1']))
    assert 'regulation 1' in resolved.lower() and 'regulation 4' in resolved.lower()
    text='1. Opening.- Notify before opening.\n2. Fees.- Pay fee.\n4. Returns.- File annual returns.\n5. Records.- Keep records.'
    doc={'id':'a','name':'a.pdf','dataset_name':'a','extracted_text':text}
    with patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        chunks,_=asyncio.run(retrieve(resolved,[doc]))
    joined=' '.join(c.text for c in chunks)
    assert 'Notify before' in joined and 'annual returns' in joined


@pytest.mark.parametrize('q',['why?','what caused the accident?','what were the corrective actions?','and how was it fixed?','Who is responsible?'])
def test_incident_followups_retain_document_subject(q):
    resolved=retrieval_question(request(q,['Explain the conveyor accident in investigation.pdf']))
    assert 'conveyor' in resolved and 'investigation.pdf' in resolved


def test_short_request_for_simpler_language_keeps_subject():
    resolved=retrieval_question(request('in simple words',['Explain the dust control procedure','tell me more']))
    assert 'dust control' in resolved


@pytest.mark.parametrize('question',['explain simply','explain in simple words','explain in simpler language'])
def test_elliptical_explanation_keeps_subject_without_pronoun(question):
    assert 'dust control' in retrieval_question(request(question,['Explain the dust control procedure']))


def test_dotted_section_returns_only_requested_scope():
    doc={'id':'a','name':'manual.pdf','dataset_name':'a','extracted_text':
        '2.1 Maintenance\nIsolate the drill before servicing.\n2.2 Storage\nKeep fuel away from flames.'}
    with patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        chunks,_=asyncio.run(retrieve('Explain section 2.1',[doc]))
    assert chunks and any('Isolate' in c.text for c in chunks)
    assert all('Keep fuel' not in c.text for c in chunks)


def test_parent_section_includes_children_and_skips_contents():
    doc={'id':'a','name':'manual.pdf','dataset_name':'a','extracted_text':
         '3.2 Risk controls .......... 4\n3.3 Records ........ 5\n'
         '[PDF page 4]\n3.2 Risk controls\n3.2.1 Isolation\nDisconnect power.\n'
         '3.2.2 Testing\nVerify isolation.\n3.3 Records\nRecord the result.'}
    with patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        chunks,_=asyncio.run(retrieve('Explain section 3.2',[doc]))
    joined=' '.join(c.text for c in chunks)
    assert 'Disconnect power' in joined and 'Verify isolation' in joined
    assert 'Record the result' not in joined and '........' not in joined


def test_new_topic_terms_outweigh_repeated_old_subject():
    text=''.join(f'[PDF page {i}]\nVentilation airflow ventilation fans ventilation air.\n' for i in range(1,11))
    text+='[PDF page 11]\nAir monitoring records must be kept for seven years.'
    doc={'id':'a','name':'guide.pdf','dataset_name':'a','extracted_text':text}
    resolved=retrieval_question(request('how long must air monitoring records be kept according to it?',
                                      ['Explain ventilation airflow','does it cover fans?']))
    with patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        chunks,_=asyncio.run(retrieve(resolved,[doc]))
    assert chunks[0].page==11


def test_switching_off_followup_preserves_isolation_subject():
    resolved=retrieval_question(request('is switching off alone enough?', ['Explain isolation in this guideline']))
    assert 'isolation' in resolved
