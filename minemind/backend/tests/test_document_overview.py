import pytest
from services.document_overview import document_overview


DOC = {'id': 'one', 'name': 'e1712.pdf', 'dataset_name': 'owned',
       'extracted_text': '[PDF page 2]\nCHAPTER I\nPRELIMINARY\n1. These regulations apply.\n'
                         '[PDF page 3]\nCHAPTER II\nRETURNS, NOTICES AND RECORDS\n2. Report details.'}


@pytest.mark.parametrize('question', ['What are the key regulations in e1712.pdf?', 'whts given in this pdf'])
def test_overview_is_cited_from_document_headings(question):
    answer, sources = document_overview(question, [DOC])
    assert 'Preliminary' in answer and 'Returns, notices and records' in answer
    assert [s.page for s in sources] == [2, 3]
    for source in sources:
        assert DOC['extracted_text'][source.start_offset:source.end_offset] == source.excerpt


def test_specific_question_and_missing_headings_do_not_get_overview():
    assert document_overview('What is the gas limit in this pdf?', [DOC]) is None
    assert document_overview('What are the key regulations?', [{**DOC, 'extracted_text': 'No headings'}]) is None
    assert document_overview('Summarize ventilation requirements in this pdf', [DOC]) is None
    assert document_overview('Give an overview of accident reporting in this document', [DOC]) is None
    assert document_overview('Summarize e1712.pdf', [DOC]) is not None
    assert document_overview('What is this pdf about?', [DOC]) is not None


@pytest.mark.parametrize('question', ['whts in ch 1', 'what is in chapter I', 'explain chapter 1'])
def test_chapter_followup_resolves_arabic_and_roman_numbers(question):
    from services.document_overview import chapter_overview
    doc = {**DOC, 'extracted_text': '[PDF page 2]\nCHAPTER I\nPRELIMINARY\n1. Application.- All mines.\n2. Definitions.- Terms.\nCHAPTER II\nNOTICES\n3. Opening.- Notify.'}
    answer, sources = chapter_overview(question, [doc])
    assert 'Application' in answer and 'Definitions' in answer
    assert 'Opening' not in answer
    for source in sources:
        assert doc['extracted_text'][source.start_offset:source.end_offset] == source.excerpt
    assert chapter_overview('whts in ch 99', [doc]) is None
    assert chapter_overview('what is the gas limit in chapter 1?', [doc]) is None
