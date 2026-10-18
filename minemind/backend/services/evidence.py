"""Immutable, server-owned evidence. Model text never becomes a trusted quote."""
import hashlib
import re
from dataclasses import dataclass

from models.schemas import Source


@dataclass(frozen=True)
class Chunk:
    document_id: str
    document_version: str
    title: str
    dataset: str
    start: int
    end: int
    text: str
    page: int | None
    section: str | None

    @property
    def id(self):
        return hashlib.sha256(f'{self.document_id}:{self.document_version}:{self.start}:{self.end}'.encode()).hexdigest()[:24]

    def source(self, source_id: str, quote: str | None = None):
        excerpt = self.text if quote is None else quote
        offset = self.text.find(excerpt)
        if offset < 0 or not excerpt.strip():
            raise ValueError('Quote is not an exact source span')
        return Source(title=self.title, excerpt=excerpt, document_id=self.document_id,
                      document_version=self.document_version, chunk_id=self.id, source_id=source_id,
                      start_offset=self.start+offset, end_offset=self.start+offset+len(excerpt),
                      page=self.page, section=self.section)


def document_chunks(doc: dict, size: int = 1200) -> list[Chunk]:
    text = str(doc.get('extracted_text') or '')
    if not text or not doc.get('id'):
        return []
    version = hashlib.sha256(text.encode()).hexdigest()
    markers = list(re.finditer(r'\[(?:PDF|OCR) page (\d+)\]|\[Table [^\]]+\]', text))
    # Section labels are copied from the document, never supplied by the model.
    # Accept numbered headings on one line or with the title on the next line;
    # discard dotted-leader contents entries. These labels aid disambiguation.
    headings = [h for h in re.finditer(
        r'(?m)^[ \t]*(?:(?:CHAPTER|SECTION)[ \t]+(?:[IVXLCDM]+|\d+(?:\.\d+)*)(?:[ \t]+[^\n]{1,100})?|'
        r'\d{1,2}\.[ \t]+[A-Z][^\n]{1,80}|'
        r'\d{1,2}\.[ \t]*\n[A-Z][^\n]{1,80}|'
        r'(?:EXECUTIVE SUMMARY|Executive [Ss]ummary|ABSTRACT|Abstract))[ \t]*$', text)
        if not re.search(r'\.{3,}',h.group())]
    # Reports often use unnumbered or run-in headings. Keep their evidence
    # separate: an investigation finding must not inherit a preceding test or
    # reenactment's provenance merely because it fits in the same chunk.
    report_headings = list(re.finditer(
        r'(?m)^[ \t]*[A-Z][A-Z /&()\-]{2,90}[ \t]*$', text))
    report_headings += list(re.finditer(
        r'(?m)^[ \t]*[A-Z][a-z]+(?:[ \t]+(?:[A-Z][a-z]+|and|of|the|for|in)){0,8}'
        r'(?=[ \t]{2,}[A-Z])', text))
    # PDF extraction sometimes collapses the gap after common report labels.
    # These are section types, not document-specific names or expected answers.
    report_headings += list(re.finditer(
        r'(?im)^[ \t]*(?:(?:accident|incident)[ \t]+)?(?:re[ -]?enactment|reconstruction)\b|'
        r'^[ \t]*(?:training and experience|root cause analysis|general information|'
        r'description of (?:the )?(?:accident|incident)|investigation of (?:the )?(?:accident|incident)|'
        r'enforcement actions|corrective actions|conclusions?)(?=[ \t]+|$)', text))
    # Tables retain their row/header structure rather than treating uppercase
    # cells as new sections. A page marker ends a table's extracted block.
    report_headings = [h for h in report_headings if not any(
        m.end() <= h.start() < (markers[i+1].start() if i+1 < len(markers) else len(text))
        and not m.group(1) for i,m in enumerate(markers))]
    page_headers = {}
    for marker in markers:
        if marker.group(1):
            first_line = re.match(r'\s*([^\n]+)', text[marker.end():])
            if first_line:
                label = ' '.join(first_line.group(1).split())
                page_headers.setdefault(label, set()).add(marker.group(1))
    repeated_headers = {label for label, pages in page_headers.items() if len(pages) > 1}
    report_headings = [h for h in report_headings
                       if ' '.join(h.group().split()) not in repeated_headers
                       and h.group().strip().lower() not in {'note', 'notes', 'warning', 'warnings', 'caution', 'important'}]
    headings = sorted(headings + report_headings, key=lambda h: (h.start(), h.end()))
    boundaries = sorted({0, len(text), *(m.start() for m in markers), *(m.end() for m in markers),
                         *(h.start() for h in report_headings)})
    result = []
    for left, right in zip(boundaries, boundaries[1:]):
        if any(left == m.start() and right == m.end() for m in markers):
            continue
        cursor = left
        while cursor < right:
            end = min(cursor+size, right)
            if end < right:
                split = text.rfind('\n', cursor+size//2, end)
                if split > cursor:
                    end = split
                # Keep a sentence and its nearby qualification together when it
                # fits within the fixed budget, instead of cutting at a PDF line wrap.
                sentences=list(re.finditer(r'[.!?](?=\s+(?:[A-Z]|\n)|$)',text[cursor:end]))
                if sentences and sentences[-1].end() >= size//2:
                    end=cursor+sentences[-1].end()
            start = cursor
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end-1].isspace():
                end -= 1
            if end > start:
                prior = [m for m in markers if m.end() <= start]
                marker = prior[-1] if prior else None
                page = int(marker.group(1)) if marker and marker.group(1) else None
                section = marker.group(0).strip('[]') if marker and not marker.group(1) else None
                prior_headings = [h for h in headings if h.start() <= start]
                if not section and prior_headings:
                    section = ' '.join(prior_headings[-1].group().split())
                result.append(Chunk(str(doc['id']),version,str(doc['name']),str(doc['dataset_name']),start,end,text[start:end],page,section))
            cursor = max(end, cursor+1)
    return result


def validated_sources(payload: dict, allowed: dict[str, Chunk]) -> list[Source]:
    """Reject the whole claim batch on malformed/unknown/altered evidence."""
    claims = payload.get('claims')
    if not isinstance(claims, list) or not claims or len(claims) > 8:
        return []
    sources = []
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {'source_id', 'quote'}:
            return []
        source_id, quote = claim['source_id'], claim['quote']
        if not isinstance(source_id,str) or source_id not in allowed or not isinstance(quote,str):
            return []
        if len(quote.strip()) < 8 or len(quote) > 1600:
            return []
        try:
            # Validate the proposed quote, but show the entire server chunk.
            # A valid substring must not strip a preceding negation or caveat.
            allowed[source_id].source(source_id,quote)
            source = allowed[source_id].source(source_id)
        except ValueError:
            return []
        if source not in sources:
            sources.append(source)
    return sources
