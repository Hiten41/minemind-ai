"""Optional regression checks against downloaded, independently reviewed public PDFs.

Set MINEMIND_CORPUS_DIR to the directory containing evals/mining_corpus.json's PDFs.
These checks assert that known supporting pages are retrieved; live answer quality
is evaluated separately by the corpus runner and source review.
"""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from services.parser import parse_pdf
from services.retrieval import retrieve
from services.retrieval import retrieval_question
from models.schemas import QueryRequest

CORPUS=Path(os.environ['MINEMIND_CORPUS_DIR']) if os.environ.get('MINEMIND_CORPUS_DIR') else None
pytestmark=pytest.mark.skipif(CORPUS is None,reason='Public PDF corpus not configured')


@pytest.fixture(scope='module')
def documents():
    manifest=json.loads((Path(__file__).resolve().parents[1]/'evals/mining_corpus.json').read_text(encoding='utf-8'))
    return {p.name:dict(id=p.name,name=p.name,dataset_name=p.stem,extracted_text=parse_pdf(str(p)))
            for p in (CORPUS/item['file'] for item in manifest['documents'])}


@pytest.mark.parametrize('filename,question,pages',[
    ('nsw-hazardous-energy-guideline.pdf','Explain isolation in this guideline in simple language.',{9}),
    ('nsw-ventilation-technical-guide.pdf','How long must air monitoring records be kept?',{25}),
    ('nsw-ventilation-technical-guide.pdf','Explain section 3.2.7',{25}),
    ('nsw-mine-safety-audit-2011.pdf','What was the overall average CMP audit compliance?',{53}),
    ('nsw-mine-safety-audit-2011.pdf','What percentage was emergency preparedness compliance? Check both the executive summary and detailed findings.',{10,34}),
    ('msha-meikle-accident-2004.pdf','What was wrong with the parking brake?',{7}),
    ('msha-haulage-inspection-card.pdf','What if I notice tire swelling?',{2}),
])
def test_known_supporting_pages_are_retrieved(documents,filename,question,pages):
    with patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        chunks,_=asyncio.run(retrieve(question,[documents[filename]]))
    assert pages <= {c.page for c in chunks}
    for c in chunks:
        assert documents[filename]['extracted_text'][c.start:c.end]==c.text


def test_scope_excludes_other_corpus_documents(documents):
    with patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        chunks,_=asyncio.run(retrieve('What caused the Meikle accident?',[documents['msha-haulage-inspection-card.pdf']]))
    assert all(c.title=='msha-haulage-inspection-card.pdf' for c in chunks)


def test_derived_scan_uses_ocr_and_preserves_warning():
    fixture=CORPUS/'derived-scan-haulage-page-2.pdf'
    if not fixture.exists():pytest.skip('Derived scan fixture not present')
    text=parse_pdf(str(fixture))
    assert '[OCR page 1]' in text
    assert 'swelling' in text and 'Move away' in text and 'appropriate supervisor' in text


def test_table_keeps_brattice_role_in_its_own_row(documents):
    text=documents['nsw-ventilation-technical-guide.pdf']['extracted_text']
    assert 'Installation of temporary stoppings (brattice) in a mains development unit | Deputy' in text


def test_audit_comparison_retains_named_metric_after_population_followup(documents):
    question=retrieval_question(QueryRequest(question='compare metals and extractive operations for it',chat_history=[
        {'role':'user','content':'What was the overall average CMP audit compliance?'},
        {'role':'user','content':'how many operations was that based on?'}]))
    with patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        chunks,_=asyncio.run(retrieve(question,[documents['nsw-mine-safety-audit-2011.pdf']]))
    assert any('88.89%' in c.text and '79.33%' in c.text for c in chunks)


def test_scope_retrieval_includes_its_continued_limitation(documents):
    with patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
        chunks,_=asyncio.run(retrieve('What is the scope of this ventilation guide?',[documents['nsw-ventilation-technical-guide.pdf']]))
    joined=' '.join(' '.join(c.text.split()) for c in chunks)
    assert 'limited to underground mines' in joined and 'not intended to be used for the management of ventilation in any other context' in joined
