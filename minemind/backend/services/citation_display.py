"""Readable API text with separate, immutable citation-to-source references."""
import re
from collections.abc import Mapping, Sequence
from typing import Any

from models.schemas import ContentPart, QueryResponse, Source


_CITATIONS = re.compile(r'\[SRC_\d+\](?:[ \t]*\[SRC_\d+\])*')
_SOURCE_ID = re.compile(r'\[(SRC_\d+)\]')


def readable_content(text: str, sources: Sequence[Source | Mapping[str, Any]]) -> tuple[str, list[ContentPart]]:
    """Replace only internal citation tokens; preserve prose and source metadata."""
    records = [source.model_dump() if isinstance(source, Source) else source for source in sources]
    by_id = {source.get('source_id'): source for source in records}
    documents = {source.get('document_id') or source.get('title') for source in records}
    multiple_documents = len(documents) > 1
    parts: list[ContentPart] = []
    cursor = 0
    for match in _CITATIONS.finditer(text):
        if match.start() > cursor:
            parts.append(ContentPart(text=text[cursor:match.start()]))
        groups: dict[tuple, ContentPart] = {}
        for source_id in _SOURCE_ID.findall(match.group()):
            source = by_id.get(source_id)
            if source is None:
                groups.setdefault(('unavailable',), ContentPart(text='(Source unavailable)'))
                continue
            page, section = source.get('page'), source.get('section')
            location = f'pg. {page}' if page is not None else section or 'Source'
            document = source.get('document_id') or source.get('title') or source_id
            key = (document, 'page', page) if page is not None else (document, 'section', section) if section else (document, 'chunk', source.get('chunk_id') or source_id)
            label = f'{source.get("title") or "Document"} · {location}' if multiple_documents else location
            part = groups.setdefault(key, ContentPart(text=f'({label})'))
            if source_id not in part.source_ids:
                part.source_ids.append(source_id)
        for index, part in enumerate(groups.values()):
            if index:
                parts.append(ContentPart(text=' '))
            parts.append(part)
        cursor = match.end()
    if cursor < len(text):
        parts.append(ContentPart(text=text[cursor:]))
    return ''.join(part.text for part in parts), parts


def display_response(response: QueryResponse) -> QueryResponse:
    """Adapt at the HTTP boundary, leaving generation/cache/persistence canonical."""
    answer, parts = readable_content(response.answer, response.sources)
    reasoning, _ = readable_content(response.reasoning, response.sources)
    return response.model_copy(update={'answer': answer, 'reasoning': reasoning, 'content_parts': parts})


def display_history(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Format historical assistant text without rewriting stored conversations."""
    result = []
    for message in messages:
        item = dict(message)
        if item.get('role') == 'assistant':
            sources = item.get('sources') or []
            content, parts = readable_content(item.get('content') or '', sources)
            item.update(content=content, content_parts=[part.model_dump() for part in parts])
            for field in ('answer', 'reasoning'):
                if isinstance(item.get(field), str):
                    item[field], _ = readable_content(item[field], sources)
        result.append(item)
    return result
