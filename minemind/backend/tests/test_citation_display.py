from copy import deepcopy
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api import query
from main import app
from models.schemas import QueryResponse, Source
from services import auth_service as auth
from services.citation_display import display_history, display_response, readable_content


def source(source_id='SRC_4', **changes):
    values = dict(title='report.pdf', excerpt='Exact evidence [SRC_27] remains verbatim.',
                  document_id='report', document_version='version', chunk_id=source_id,
                  source_id=source_id, start_offset=0, end_offset=50, page=7)
    return Source(**{**values, **changes})


def response(**changes):
    values = dict(answer='The switch was faulty. [SRC_4] [SRC_5]',
                  reasoning='Supported by [SRC_4].', sources=[source(), source('SRC_5')],
                  related_memories=[], evidence_status='source_excerpts')
    return QueryResponse(**{**values, **changes})


def assert_parts_match(text, parts):
    assert ''.join(part.text for part in parts) == text


def test_readable_answer_groups_same_page_without_losing_either_passage():
    original = response()
    snapshot = original.model_dump()
    result = display_response(original)
    assert result.answer == 'The switch was faulty. (pg. 7)'
    assert result.reasoning == 'Supported by (pg. 7).'
    assert result.content_parts[-1].source_ids == ['SRC_4', 'SRC_5']
    assert_parts_match(result.answer, result.content_parts)
    assert original.model_dump() == snapshot
    assert result.sources == original.sources
    assert result.sources[0].excerpt == 'Exact evidence [SRC_27] remains verbatim.'


def test_different_documents_same_page_are_distinguishable_and_keep_claim_mapping():
    text, parts = readable_content('First [SRC_4], second [SRC_5].', [
        source(), source('SRC_5', title='audit.pdf', document_id='audit')])
    assert text == 'First (report.pdf · pg. 7), second (audit.pdf · pg. 7).'
    assert [part.source_ids for part in parts if part.source_ids] == [['SRC_4'], ['SRC_5']]
    assert_parts_match(text, parts)


def test_whitespace_unicode_and_newlines_outside_citation_groups_are_preserved():
    text, parts = readable_content('श्रमिक —  café\n[SRC_4]\t[SRC_5]  Next\n[SRC_4]\n',
                                   [source(), source('SRC_5')])
    assert text == 'श्रमिक —  café\n(pg. 7)  Next\n(pg. 7)\n'
    assert_parts_match(text, parts)


def test_unknown_sources_are_explicit_and_do_not_get_fabricated_references():
    text, parts = readable_content('Check [SRC_4] [SRC_99] [SRC_99] again.', [source()])
    assert text == 'Check (pg. 7) (Source unavailable) again.'
    assert [part.source_ids for part in parts if 'unavailable' in part.text] == [[]]
    assert_parts_match(text, parts)


def test_section_and_unpaginated_sources_remain_linkable_and_ordinary_text_is_untouched():
    text, parts = readable_content('[SRC_LABEL] [SRC_4] [SRC_5]', [
        source(page=None, section='Brake inspection'), source('SRC_5', page=None)])
    assert text == '[SRC_LABEL] (Brake inspection) (Source)'
    assert [part.source_ids for part in parts if part.source_ids] == [['SRC_4'], ['SRC_5']]
    assert_parts_match(text, parts)


def test_deleted_sources_keep_the_historical_location_and_availability_metadata():
    original = response(sources=[source(available=False)])
    result = display_response(original)
    assert result.answer == 'The switch was faulty. (pg. 7) (Source unavailable)'
    assert result.sources[0].available is False
    assert result.content_parts[1].source_ids == ['SRC_4']


def test_history_formats_assistant_content_answer_reasoning_without_mutating_user_or_sources():
    model = response()
    records = [
        {'role': 'user', 'content': 'Explain [SRC_4] [SRC_5]'},
        {'role': 'assistant', 'content': model.answer, **model.model_dump()},
    ]
    snapshot = deepcopy(records)
    result = display_history(records)
    assert result[0] == records[0]
    assert result[1]['content'] == result[1]['answer'] == 'The switch was faulty. (pg. 7)'
    assert result[1]['reasoning'] == 'Supported by (pg. 7).'
    assert ''.join(part['text'] for part in result[1]['content_parts']) == result[1]['content']
    assert result[1]['content_parts'][-1]['source_ids'] == ['SRC_4', 'SRC_5']
    assert records == snapshot
    assert result[1]['sources'] == snapshot[1]['sources']


def test_live_and_history_http_boundaries_format_identically_without_rewriting_storage(user):
    canonical = response()
    auth.save_chat_turn(user['id'], 'Explain [SRC_4]', canonical.model_dump())
    headers = {'Authorization': 'Bearer ' + auth.create_token(user['id'])}
    with TestClient(app) as client, patch.object(query, 'query_ai', AsyncMock(return_value=canonical)):
        live = client.post('/api/query', headers=headers, json={'question': 'Explain the switch'}).json()
        history = client.get('/api/chat/history', headers=headers).json()
    assert live['answer'] == history[1]['content'] == history[1]['answer'] == 'The switch was faulty. (pg. 7)'
    assert live['content_parts'] == history[1]['content_parts']
    assert history[0]['content'] == 'Explain [SRC_4]'
    stored = auth.list_chat_messages(user['id'])
    assert stored[1]['content'] == canonical.answer
    assert stored[1]['answer'] == canonical.answer
    assert stored[1]['reasoning'] == canonical.reasoning


def test_answers_without_citations_stay_exact_and_have_valid_plain_text_parts():
    for original in ('', 'No supporting passage was found.\n', 'Voltage [SRC_LABEL] is a field.'):
        text, parts = readable_content(original, [])
        assert text == original
        assert_parts_match(text, parts)
        assert all(part.source_ids == [] for part in parts)
