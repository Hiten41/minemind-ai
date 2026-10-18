import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
import httpx
import pytest
from openai import RateLimitError, BadRequestError

from api import query
from models.schemas import QueryRequest
from services.retrieval import retrieval_question
from services.evidence import document_chunks
from test_query_contract import AnswerClient


def test_followup_rewrite_retains_metric_without_becoming_answer_evidence():
    req=QueryRequest(question='compare metals and extractive operations for it',chat_history=[
        {'role':'user','content':'What is the overall CMP audit compliance?'}])
    client=AnswerClient({'search_question':'Compare overall CMP audit compliance for metalliferous and extractive operations.'})
    with patch.object(query,'create_llm_client',return_value=client):
        resolved,status=asyncio.run(query.contextual_search_question(req,retrieval_question(req)))
    assert 'CMP' in resolved and status=='ok'


def test_failed_followup_rewrite_keeps_local_resolution():
    req=QueryRequest(question='explain that simply',chat_history=[{'role':'user','content':'Does the brake work with the engine off?'}])
    fallback=retrieval_question(req)
    with patch.object(query,'create_llm_client',side_effect=TimeoutError):
        resolved,status=asyncio.run(query.contextual_search_question(req,fallback))
    assert resolved==fallback and 'engine off' in resolved and status=='fallback'


def test_rewrite_that_drops_metric_preserves_full_question_context():
    req=QueryRequest(question='compare metals and extractive operations for it',chat_history=[
        {'role':'user','content':'What is the overall CMP audit compliance?'},
        {'role':'user','content':'how many operations was that based on?'}])
    fallback=retrieval_question(req)
    with patch.object(query,'create_llm_client',return_value=AnswerClient({'search_question':'Compare metals and extractive operations'})):
        resolved,status=asyncio.run(query.contextual_search_question(req,fallback))
    assert resolved==fallback and 'CMP audit compliance' in resolved and status=='fallback'


def test_rewritten_question_cannot_expand_selected_scope_or_supply_answer(user):
    doc={'id':'one','name':'checklist.pdf','dataset_name':'one','status':'ingested','extracted_text':'Inspect tires and report damage.'}
    req=QueryRequest(question='what caused it?',scope_mode='selected',document_ids=['one'],chat_history=[
        {'role':'user','content':'Explain the accident in another report.'}])
    with patch.object(query,'active_documents',return_value=[doc]), patch.object(query,'save_chat_turn'), \
         patch.object(query,'contextual_search_question',AsyncMock(return_value=('The accident caused 100 deaths in private.pdf','ok'))), \
         patch('services.retrieval.query_memory',AsyncMock(return_value=[])), \
         patch.object(query,'create_llm_client',return_value=AnswerClient({'status':'unsupported','claims':[]})):
        result=asyncio.run(query.query_ai(req,user))
    assert result.effective_document_ids==['one']
    assert result.sources==[] and '100' not in result.answer


def test_source_metadata_preserves_summary_and_numbered_section():
    doc={'id':'one','name':'audit.pdf','dataset_name':'one','extracted_text':
         '[PDF page 1]\nExecutive Summary\nOverview.\n[PDF page 2]\nSummary continues.\n'
         '[PDF page 3]\n4.\nCompliance by criteria\nDetailed findings.\n[PDF page 4]\nMore detailed findings.'}
    chunks=document_chunks(doc)
    assert next(c for c in chunks if c.page==2).section=='Executive Summary'
    assert next(c for c in chunks if c.page==4).section=='4. Compliance by criteria'


def test_numbered_values_addresses_and_page_headers_are_not_section_labels():
    doc={'id':'a','name':'a.pdf','dataset_name':'a','extracted_text':
         '[PDF page 1]\n2060 Peabody Road\n79.91 Lightning Ridge\n20\nThe VCP needs control.\n'}
    assert all(c.section is None for c in document_chunks(doc))


def test_site_specific_question_asks_for_missing_site(user):
    doc={'id':'a','name':'guide.pdf','dataset_name':'a','status':'ingested','extracted_text':'The ventilation officer checks the fan.'}
    with patch.object(query,'active_documents',return_value=[doc]),patch.object(query,'save_chat_turn'),patch.object(query,'create_llm_client') as provider:
        result=asyncio.run(query.query_ai(QueryRequest(question='Who is the ventilation officer at my mine?'),user))
    assert result.evidence_status=='not_required' and 'Which mine' in result.answer
    provider.assert_not_called()


def test_current_question_can_identify_its_site(user):
    doc={'id':'a','name':'guide.pdf','dataset_name':'a','status':'ingested','extracted_text':'The ventilation officer checks the fan.'}
    with patch.object(query,'active_documents',return_value=[doc]),patch.object(query,'save_chat_turn'), \
         patch.object(query,'create_llm_client',return_value=AnswerClient({'status':'unsupported','claims':[]})), \
         patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        result=asyncio.run(query.query_ai(QueryRequest(question='Our mine is Meikle. Who is the ventilation officer at our mine?'),user))
    assert 'Which mine' not in result.answer and result.evidence_status=='unsupported'


def test_ambiguous_document_meaning_can_ask_focused_clarification(user):
    docs=[{'id':'a','name':'energy.pdf','dataset_name':'a','status':'ingested','extracted_text':'Isolation disconnects energy.'},
          {'id':'b','name':'ventilation.pdf','dataset_name':'b','status':'ingested','extracted_text':'Isolation separates workings from ventilation air.'}]
    with patch.object(query,'active_documents',return_value=docs),patch.object(query,'save_chat_turn'), \
         patch.object(query,'create_llm_client',return_value=AnswerClient({'status':'clarification','question':'Do you mean energy isolation or ventilation isolation?'})), \
         patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        result=asyncio.run(query.query_ai(QueryRequest(question='What does isolation mean?'),user))
    assert result.answer=='Do you mean energy isolation or ventilation isolation?'
    assert result.sources==[] and result.evidence_status=='not_required'


def test_provider_json_format_failure_gets_one_bounded_repair(user):
    doc={'id':'a','name':'guide.pdf','dataset_name':'a','status':'ingested','extracted_text':'Keep records for seven years.'}
    client=AnswerClient({})
    error=BadRequestError('Invalid generated JSON',response=httpx.Response(400,request=httpx.Request('POST','https://example.com')),body={'code':'json_validate_failed'})
    answer={'status':'source_excerpts','claims':[{'source_ids':['SRC_1'],'text':'Keep records for seven years.'}]}
    client.create.side_effect=[error,SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(answer)))])]
    with patch.object(query,'active_documents',return_value=[doc]),patch.object(query,'save_chat_turn'), \
         patch.object(query,'create_llm_client',return_value=client),patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        result=asyncio.run(query.query_ai(QueryRequest(question='How long are records kept?'),user))
    assert 'seven years' in result.answer and client.create.call_count==2
    assert result.retrieval_diagnostics['answer_repair']=='provider_json_format'


def test_invalid_numeric_citation_gets_one_bounded_repair(user):
    doc={'id':'a','name':'guide.pdf','dataset_name':'a','status':'ingested','extracted_text':'Keep records for seven years.'}
    client=AnswerClient({})
    def response(text):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
        {'status':'source_excerpts','claims':[{'source_ids':['SRC_1'],'text':text}]})))])
    client.create.side_effect=[response('Keep records for 8 years.'),response('Keep records for seven years.')]
    with patch.object(query,'active_documents',return_value=[doc]),patch.object(query,'save_chat_turn'), \
         patch.object(query,'create_llm_client',return_value=client),patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        result=asyncio.run(query.query_ai(QueryRequest(question='How long are records kept?'),user))
    assert 'seven years' in result.answer and client.create.call_count==2
    assert result.retrieval_diagnostics['answer_repair']=='attempted'


def test_rewrite_cannot_turn_an_action_followup_into_invented_causes():
    req=QueryRequest(question='and separation from the rim?',chat_history=[{'role':'user','content':'what if I notice swelling?'}])
    fallback=retrieval_question(req)
    with patch.object(query,'create_llm_client',return_value=AnswerClient({'search_question':'What causes separation from the rim?'})):
        resolved,status=asyncio.run(query.contextual_search_question(req,fallback))
    assert resolved==fallback and status=='fallback'


@pytest.mark.parametrize('delay',[1,10])
def test_brief_provider_throttle_retries_only_once(delay):
    response=httpx.Response(429,headers={'retry-after':str(delay)},request=httpx.Request('POST','https://example.com'))
    error=RateLimitError('throttled',response=response,body=None)
    create=AsyncMock(side_effect=[error,'ok'])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with patch.object(query.asyncio,'sleep',new_callable=AsyncMock) as sleep:
        assert asyncio.run(query.complete_with_short_retry(client,model='test'))=='ok'
    assert create.call_count==2
    sleep.assert_awaited_once_with(float(delay))


@pytest.mark.parametrize('retry_after',['60','invalid'])
def test_long_or_invalid_throttle_does_not_wait_or_loop(retry_after):
    response=httpx.Response(429,headers={'retry-after':retry_after},request=httpx.Request('POST','https://example.com'))
    create=AsyncMock(side_effect=RateLimitError('throttled',response=response,body=None))
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with patch.object(query.asyncio,'sleep',new_callable=AsyncMock) as sleep,pytest.raises(RateLimitError):
        asyncio.run(query.complete_with_short_retry(client,model='test'))
    assert create.call_count==1
    sleep.assert_not_awaited()


def test_missing_retry_header_uses_bounded_provider_delay():
    response=httpx.Response(429,request=httpx.Request('POST','https://example.com'))
    error=RateLimitError('throttled',response=response,body={'message':'Please try again in 9.25s.'})
    create=AsyncMock(side_effect=[error,'ok'])
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with patch.object(query.asyncio,'sleep',new_callable=AsyncMock) as sleep:
        assert asyncio.run(query.complete_with_short_retry(client,model='test'))=='ok'
    sleep.assert_awaited_once_with(9.25)
    assert create.call_count==2


def test_oversized_or_daily_quota_error_without_retry_hint_does_not_retry():
    response=httpx.Response(429,request=httpx.Request('POST','https://example.com'))
    error=RateLimitError('Request too large',response=response,body={'message':'Output tokens exceed the limit.'})
    create=AsyncMock(side_effect=error)
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with patch.object(query.asyncio,'sleep',new_callable=AsyncMock) as sleep,pytest.raises(RateLimitError):
        asyncio.run(query.complete_with_short_retry(client,model='test'))
    sleep.assert_not_awaited()
    assert create.call_count==1
