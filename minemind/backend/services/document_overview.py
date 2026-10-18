"""Source-derived chapter overview for broad document questions."""
import hashlib
import re

from services.evidence import Chunk
from services.document_references import REGULATIONS


def chapter_overview(question: str, docs: list[dict]):
    match = re.fullmatch(r"\s*(?:(?:what(?:'s| is)?|whats|whts|wht)\s+(?:given\s+)?in|explain|summari[sz]e|show)\s+(?:me\s+)?(?:ch\.?|chapter)\s*(\d+|[ivxlcdm]+)\s*[?.!]*\s*", question, re.I)
    if not match:
        return None
    token = match.group(1).upper()
    if token.isdigit():
        number = int(token)
        if not 1 <= number <= 100:
            return None
        token = ''
        for value, symbol in [(100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]:
            while number >= value:
                token += symbol
                number -= value
    sources, answers = [], []
    for doc in docs:
        text = str(doc.get('extracted_text') or '')
        headings = list(re.finditer(r'(?m)^[ \t]*CHAPTER[ \t]+([IVXLCDM]+)\b[^\n]*\n', text))
        for index, heading in enumerate(headings):
            if heading.group(1) != token:
                continue
            end = headings[index+1].start() if index+1 < len(headings) else len(text)
            chapter = text[heading.end():end]
            title = chapter.splitlines()[0].strip()
            rules = list(REGULATIONS.finditer(chapter))
            lines = []
            for rule in rules[:40]:
                start = heading.end() + rule.start()
                excerpt = text[start:heading.end()+rule.end()]
                pages = list(re.finditer(r'\[(?:PDF|OCR) page (\d+)\]', text[:start]))
                chunk = Chunk(str(doc['id']), hashlib.sha256(text.encode()).hexdigest(),
                              str(doc['name']), str(doc['dataset_name']), start, start+len(excerpt),
                              excerpt, int(pages[-1].group(1)) if pages else None, f'Chapter {token}')
                sid = f'SRC_{len(sources)+1}'
                sources.append(chunk.source(sid))
                lines.append(f'- Regulation {rule.group(1)}: {" ".join(rule.group(2).split())} [{sid}]')
            if lines:
                answers.append(f'{doc["name"]} — Chapter {token}: {title.capitalize()}\n\nThis chapter contains:\n' + '\n'.join(lines))
    if not sources:
        return None
    return '\n\n'.join(answers) + '\n\nThese are the regulation headings in this chapter. Ask about a named regulation for its detailed requirements.', sources


def document_overview(question: str, docs: list[dict]):
    broad = re.search(
        r'\b(key|main)\s+(regulations|topics|sections)\b|'
        r'\b(what|whats|wht|whts)(?:\s+is)?\s+(?:given\s+)?in\s+(?:this|the)\s+(?:pdf|document)\b|'
        r'\bwhat\s+does\s+(?:this|the)\s+(?:pdf|document)\s+(?:contain|cover)\b|'
        r'\bwhat\s+is\s+(?:this|the)\s+(?:pdf|document)\s+about\b|'
        r'^\s*(?:summarize|summarise|(?:give me (?:an? )?)?overview of)\s+(?:(?:this|the|my)\s+)?(?:pdf|document|\S+\.pdf)\s*[?.!]*\s*$', question, re.I)
    if not broad:
        return None
    # Do not turn specific fact questions into generic chapter lists.
    if not re.search(r'\b(pdf|document|regulations|overview)\b', question, re.I):
        return None
    sources, sections = [], []
    for doc in docs:
        text = str(doc.get('extracted_text') or '')
        headings = list(re.finditer(r'(?m)^[ \t]*CHAPTER[ \t]+[IVXLCDM]+[^\n]*\n', text))
        if not headings:
            continue
        lines = []
        for heading in headings[:30]:
            end = heading.end()
            title_lines = []
            for line in text[end:].splitlines(keepends=True)[:4]:
                clean = line.strip()
                if not clean or not clean.isupper() or not re.search('[A-Z]', clean):
                    break
                title_lines.append(clean)
                end += len(line)
            if not title_lines:
                continue
            excerpt = text[heading.start():end].strip()
            start = text.find(excerpt, heading.start())
            pages = list(re.finditer(r'\[(?:PDF|OCR) page (\d+)\]', text[:start]))
            page = int(pages[-1].group(1)) if pages else None
            chunk = Chunk(str(doc['id']), hashlib.sha256(text.encode()).hexdigest(),
                          str(doc['name']), str(doc['dataset_name']), start,
                          start + len(excerpt), excerpt, page, None)
            sid = f'SRC_{len(sources)+1}'
            sources.append(chunk.source(sid))
            label = heading.group().strip()
            lines.append(f'- {label}: {" ".join(title_lines).capitalize()} [{sid}]')
        if lines:
            sections.append(f'{doc["name"]} covers these chapters:\n\n' + '\n'.join(lines))
    if not sources:
        return None
    return ('\n\n'.join(sections) + '\n\nThis is an overview of the document’s chapter headings, '
            'not a complete statement of its requirements. Ask about a chapter for the specific rules.', sources)
