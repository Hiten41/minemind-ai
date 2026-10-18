import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from models.schemas import QueryRequest
from services.evidence import document_chunks, validated_sources
from services.query_cache import TTLCache


def fixture_doc(doc_id='one', text='Pump pressure must not exceed 42 kPa.'):
    return {'id':doc_id,'name':'same.pdf','dataset_name':'dataset_'+doc_id,'extracted_text':text,'status':'ingested'}


@pytest.mark.parametrize('payload', [
    {'sources':[{'title':'invented.pdf','excerpt':'999'}]},
    {'claims':[{'source_id':'SRC_9','quote':'Pump pressure must not exceed 42 kPa.'}]},
    {'claims':[{'source_id':'SRC_1','quote':'Pump pressure must not exceed 99 kPa.'}]},
    {'claims':[{'source_id':'SRC_1','quote':'Pump pressure must not exceed 42 kPa.','title':'secret.pdf'}]},
    {'answer':'Trust me','claims':[]},
])
def test_fabricated_citations_rejected(payload):
    assert validated_sources(payload, {'SRC_1':document_chunks(fixture_doc())[0]}) == []


def test_valid_source_is_exact_and_immutable():
    chunk = document_chunks(fixture_doc())[0]
    source = validated_sources({'claims':[{'source_id':'SRC_1','quote':chunk.text}]},{'SRC_1':chunk})[0]
    assert source.excerpt == chunk.text and source.document_id == 'one'
    assert document_chunks(fixture_doc('two'))[0].id != chunk.id
    assert chunk.id == document_chunks(fixture_doc())[0].id


def test_cache_bound_ttl_and_user_invalidation():
    clock = [0]
    cache = TTLCache(maxsize=2,ttl=5,clock=lambda:clock[0])
    cache.set(('a','1'),1); cache.set(('a','2'),2); cache.set(('b','3'),3)
    assert cache.get(('a','1')) is None
    cache.invalidate_user('a')
    assert cache.get(('a','2')) is None and cache.get(('b','3')) == 3
    clock[0] = 6
    assert cache.get(('b','3')) is None and not cache.entries


def test_scope_all_ignores_history():
    from services.retrieval import select_documents
    docs = [fixture_doc('incident'),fixture_doc('rules')]
    request = QueryRequest(question='Compare incident against regulations',chat_history=[{'role':'user','content':'same.pdf'}],scope_mode='all')
    assert len(select_documents(request,docs)) == 2


def test_semantic_considered_with_lexical_hit():
    from services.retrieval import retrieve
    docs=[fixture_doc('lex','Pump specifications and casing.'),fixture_doc('semantic','Isolate electrical power before servicing.')]
    provider=AsyncMock(return_value=[{'source':'dataset_semantic','text':docs[1]['extracted_text']}])
    with patch('services.retrieval.query_memory',provider):
        chunks, diagnostics=asyncio.run(retrieve('Pump shutdown procedure',docs))
    assert provider.await_count == 1
    assert {c.document_id for c in chunks} == {'lex','semantic'}
    assert diagnostics['semantic'] == 'ok'


def test_provider_failure_keeps_lexical_evidence():
    from services.retrieval import retrieve
    from services.cognee_service import MemoryProviderError
    with patch('services.retrieval.query_memory',AsyncMock(side_effect=MemoryProviderError('offline'))):
        chunks, diagnostics=asyncio.run(retrieve('pump pressure', [fixture_doc()]))
    assert chunks and diagnostics['semantic'] == 'unavailable'


def test_exact_substring_cannot_strip_negation():
    chunk = document_chunks(fixture_doc(text='No pump failure was recorded during the inspection.'))[0]
    source = validated_sources({'claims':[{'source_id':'SRC_1','quote':'pump failure was recorded'}]}, {'SRC_1':chunk})[0]
    assert source.excerpt.startswith('No pump failure')


def test_accidents_followup_retrieves_singular_when_semantic_is_offline():
    from services.retrieval import retrieve, retrieval_question
    from services.cognee_service import MemoryProviderError
    request = QueryRequest(question='wht kind of accidents', chat_history=[
        {'role': 'user', 'content': 'Analyze the risks in file-169036421359637.pdf'},
        {'role': 'assistant', 'content': '76 safety violations. Fabricated explosion claim.'},
    ])
    search = retrieval_question(request)
    assert 'file-169036421359637.pdf' in search
    assert 'Fabricated' not in search and '76' not in search
    doc = fixture_doc(text='A roof fall accident must be reported to the inspector.')
    with patch('services.retrieval.query_memory', AsyncMock(side_effect=MemoryProviderError('offline'))):
        chunks, diagnostics = asyncio.run(retrieve(search, [doc]))
    assert chunks and chunks[0].text == doc['extracted_text']
    assert diagnostics['semantic'] == 'unavailable'


def test_standalone_question_does_not_inherit_previous_topic():
    from services.retrieval import retrieval_question
    request = QueryRequest(question='What is the boiler inspection interval?', chat_history=[
        {'role': 'user', 'content': 'Analyze blasting accidents'},
    ])
    assert retrieval_question(request) == request.question


def test_followup_context_cannot_expand_selected_document_scope():
    from services.retrieval import select_documents
    docs = [fixture_doc('chosen'), fixture_doc('other')]
    request = QueryRequest(question='What kind of accidents in that?', scope_mode='selected',
        document_ids=['chosen'], chat_history=[{'role': 'user', 'content': 'Search other documents'}])
    assert [d['id'] for d in select_documents(request, docs)] == ['chosen']
