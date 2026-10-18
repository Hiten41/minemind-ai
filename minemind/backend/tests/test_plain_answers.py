import asyncio
from unittest.mock import patch, AsyncMock

import pytest
from api import query
from models.schemas import QueryRequest
from services.evidence import document_chunks
from test_query_contract import AnswerClient


DOC={'id':'one','name':'manual.pdf','dataset_name':'one','status':'ingested',
     'extracted_text':'Disconnect power before servicing except during authorized diagnostics.'}


def test_plain_explanation_keeps_citation_and_exception(user):
    model=AnswerClient({'status':'source_excerpts','claims':[{'source_id':'SRC_1',
        'text':'Before maintenance, isolate the power unless performing authorized diagnostics.'}]})
    with patch.object(query,'active_documents',return_value=[DOC]), patch.object(query,'save_chat_turn'), \
         patch.object(query,'create_llm_client',return_value=model), patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        result=asyncio.run(query.query_ai(QueryRequest(question='Explain servicing'),user))
    assert 'unless performing authorized diagnostics' in result.answer
    assert result.sources[0].excerpt==DOC['extracted_text']
    assert 'Retrieved source excerpts' not in result.answer


@pytest.mark.parametrize('claim',[
    {'source_id':'OTHER','text':'Disconnect power.'},
    {'source_id':'SRC_1','text':'Wait 30 minutes before servicing.'},
])
def test_explanation_rejects_unknown_sources_and_invented_numbers(claim):
    with pytest.raises(ValueError):
        query.explained_sources({'claims':[claim]},{'SRC_1':document_chunks(DOC)[0]})


def test_explanation_can_cite_both_spans_for_a_combined_claim():
    left=document_chunks({**DOC,'extracted_text':'The brake switch was faulty.'})[0]
    right=document_chunks({**DOC,'extracted_text':'Its two retaining tabs were worn.'})[0]
    sources,answer=query.explained_sources({'claims':[{'source_ids':['SRC_1','SRC_2'],
        'text':'The switch was faulty and its two retaining tabs were worn.'}]},{'SRC_1':left,'SRC_2':right})
    assert len(sources)==2 and '[SRC_1] [SRC_2]' in answer
    assert sources[0].excerpt==left.text and sources[1].excerpt==right.text


def test_explanation_rejects_same_number_with_wrong_unit():
    chunk=document_chunks({**DOC,'extracted_text':'The permitted concentration is 30 ppm.'})[0]
    with pytest.raises(ValueError,match='unit'):
        query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'The permitted concentration is 30%.'}]},{'SRC_1':chunk})


def test_reenactment_cannot_be_presented_as_observed_accident():
    chunk=document_chunks({**DOC,'extracted_text':'Accident Reenactment\nThe repaired truck moved forward on the grade during loading.'})[0]
    with pytest.raises(ValueError,match='reenactment'):
        query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'The truck moved because of the grade and loading.'}]},{'SRC_1':chunk})
    _,answer=query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'In the reenactment, the repaired truck moved forward on the grade during loading.'}]},{'SRC_1':chunk})
    assert 'reenactment' in answer


def test_noncausal_fact_after_reenactment_does_not_require_scenario_label():
    chunks=document_chunks({**DOC,'extracted_text':'Accident Reenactment\nThe repaired truck moved.\nTraining and Experience\nThe operator had 17 years of mining experience.'})
    chunk=next(c for c in chunks if '17 years' in c.text)
    _,answer=query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'The operator had 17 years of mining experience.'}]},{'SRC_1':chunk})
    assert '17 years' in answer


def test_broad_summary_can_cite_more_than_four_valid_passages():
    allowed={f'SRC_{i}':document_chunks({**DOC,'id':str(i),'extracted_text':f'Topic {i} is covered.'})[0] for i in range(1,7)}
    sources,_=query.explained_sources({'claims':[{'source_ids':list(allowed),'text':'The document covers topics 1, 2, 3, 4, 5 and 6.'}]},allowed)
    assert len(sources)==6


def test_verified_structural_reference_supports_arabic_chapter_number():
    from dataclasses import replace
    chunk=replace(document_chunks({**DOC,'extracted_text':'CHAPTER II\nReturns, notices and records.'})[0],section='Chapter 2')
    _,answer=query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'Chapter 2 covers returns, notices and records.'}]},{'SRC_1':chunk})
    assert 'Chapter 2' in answer


def test_spelled_out_count_and_unit_support_equivalent_digits():
    chunk=document_chunks({**DOC,'extracted_text':'Seventeen operations were audited. Retain records for seven years. Twenty-one files were inspected.'})[0]
    _,answer=query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'17 operations were audited; retain records for 7 years. 21 files were inspected.'}]},{'SRC_1':chunk})
    assert '17 operations' in answer and '7 years' in answer


def test_recommendation_cannot_be_strengthened_into_obligation():
    chunk=document_chunks({**DOC,'extracted_text':'The operator should oversee the checks before restarting.'})[0]
    with pytest.raises(ValueError,match='recommendation'):
        query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'The operator must oversee the checks before restarting.'}]},{'SRC_1':chunk})
    _,answer=query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'The operator should oversee the checks before restarting.'}]},{'SRC_1':chunk})
    assert 'should' in answer


def test_document_obligation_remains_an_obligation():
    chunk=document_chunks({**DOC,'extracted_text':'The operator shall test the guard before restarting.'})[0]
    _,answer=query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'The operator must test the guard before restarting.'}]},{'SRC_1':chunk})
    assert 'must' in answer


def test_spelled_out_wrong_quantity_is_rejected():
    chunk=document_chunks({**DOC,'extracted_text':'Keep records for seven years.'})[0]
    with pytest.raises(ValueError,match='quantity'):
        query.explained_sources({'claims':[{'source_ids':['SRC_1'],'text':'Keep records for eight years.'}]},{'SRC_1':chunk})
