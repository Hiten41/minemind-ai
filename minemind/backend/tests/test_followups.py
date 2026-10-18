import asyncio
from unittest.mock import AsyncMock, patch

from models.schemas import QueryRequest
from services.retrieval import retrieval_question, retrieve, select_documents


def test_followup_selection_uses_only_exact_server_passages():
    from api.query import followup_sources
    from services.evidence import document_chunks
    doc = {'id': 'one', 'name': 'e1712.pdf', 'dataset_name': 'one',
           'extracted_text': 'No accident was recorded.\n  Ventilation must be maintained.'}
    chunk = document_chunks(doc)[0]
    sources = followup_sources({'claims': [{'source_id': 'SRC_1'}]}, {'SRC_1': chunk})
    assert sources[0].excerpt == chunk.text
    assert followup_sources({'claims': [{'source_id': 'unknown'}]}, {'SRC_1': chunk}) == []
    assert followup_sources({'claims': [{'source_id': 'SRC_1', 'quote': 'An accident occurred'}]}, {'SRC_1': chunk}) == []


def test_multiple_short_followups_keep_original_subject():
    request = QueryRequest(question='explain more', chat_history=[
        {'role': 'user', 'content': 'Explain ventilation requirements in e1712.pdf'},
        {'role': 'assistant', 'content': 'Untrusted fabricated explosion claim'},
        {'role': 'user', 'content': 'tell me more'},
    ])
    search = retrieval_question(request)
    assert 'ventilation' in search
    assert 'fabricated' not in search


def test_new_topic_followup_becomes_subject_for_next_turn():
    request = QueryRequest(question='what about its inspection?', chat_history=[
        {'role': 'user', 'content': 'Explain ventilation requirements'},
        {'role': 'user', 'content': 'What about winding equipment?'},
    ])
    search = retrieval_question(request)
    assert 'winding equipment' in search
    assert 'ventilation' not in search


def test_auto_scope_resolves_followup_filename_but_all_stays_all():
    docs = [{'id': 'one', 'name': 'e1712.pdf'}, {'id': 'two', 'name': 'other.pdf'}]
    request = QueryRequest(question='tell me more', scope_mode='auto', chat_history=[
        {'role': 'user', 'content': 'Explain ventilation in e1712.pdf'},
    ])
    assert select_documents(request, docs) == docs[:1]
    assert select_documents(request.model_copy(update={'scope_mode': 'all'}), docs) == docs


def test_followup_search_does_not_rank_generic_pronouns_above_subject():
    docs = [{'id': 'one', 'name': 'e1712.pdf', 'dataset_name': 'one',
             'extracted_text': '[PDF page 1]\nVentilation requires a continuous supply of air.\n'
                               '[PDF page 2]\nThis is the same thing. This is that. This is the same.'}]
    request = QueryRequest(question='explain this', chat_history=[
        {'role': 'user', 'content': 'ventilation'},
    ])
    with patch('services.retrieval.query_memory', AsyncMock(return_value=[])):
        chunks, _ = asyncio.run(retrieve(retrieval_question(request), docs, limit=1))
    assert 'Ventilation' in chunks[0].text
