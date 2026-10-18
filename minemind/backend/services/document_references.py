"""Resolve numbered references against stored document structure, not keywords."""
import re
from dataclasses import replace

REFERENCE = re.compile(r'\b(chapters?|ch\.?|regulations?|reg\.?|sections?|sec\.?)\s*(\d+(?:\.\d+)*|[IVXLCDM]+)\b', re.I)
SECTIONS = re.compile(r'(?m)^[ \t]*(?:SECTION[ \t]+)?(\d+(?:\.\d+)*)[.)]?[ \t]+[A-Z][^\n]{0,160}$')
CHAPTERS = re.compile(r'(?m)^[ \t]*CHAPTER[ \t]+([IVXLCDM]+|\d+)\b[^\n]*')
REGULATIONS = re.compile(r'(?m)^[ \t]*(\d+)\.[ \t]+([A-Z][^\n]*?(?:\n[^\n]*?){0,2}?)(?:\.[ \t]*[-–—]|[–—])')


def number(value):
    if re.fullmatch(r'\d+\.\d+(?:\.\d+)*', value):
        return value
    if value.isdigit():
        return int(value)
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    nums = [values[c] for c in value.upper()]
    return sum(-n if i+1 < len(nums) and n < nums[i+1] else n for i,n in enumerate(nums))


def reference(question):
    match = REFERENCE.search(question)
    return ('chapter' if match.group(1).lower().startswith('ch') else 'section' if match.group(1).lower().startswith('sec') else 'regulation', number(match.group(2))) if match else None


def _headings(text, kind):
    pattern = CHAPTERS if kind == 'chapter' else SECTIONS if kind == 'section' else REGULATIONS
    return [h for h in pattern.finditer(text) if not re.search(r'\.{3,}', h.group())]


def adjacent_reference(kind, value, delta, context, docs):
    """Navigate observed headings, never invent a number at a hierarchy boundary."""
    if len(list(REFERENCE.finditer(context.split('\nPrevious user question (search context only): ')[0]))) > 1:
        return None
    named = [d for d in docs if str(d['name']).lower() in context.lower()]
    candidates = named or docs
    targets = []
    for doc in candidates:
        headings = _headings(str(doc.get('extracted_text') or ''), kind)
        positions = [i for i, h in enumerate(headings) if number(h.group(1)) == value]
        if len(positions) != 1:
            continue
        start = positions[0]
        depth = len(str(value).split('.'))
        indexes = range(start + delta, len(headings) if delta > 0 else -1, delta)
        neighbor = next((headings[i] for i in indexes if kind != 'section'
                         or len(headings[i].group(1).split('.')) <= depth), None)
        targets.append((number(neighbor.group(1)), doc['name']) if neighbor else None)
    return targets[0] if len(targets) == 1 else None


def _single_reference_chunks(question, docs, chunks):
    ref = reference(question)
    if not ref:
        return chunks, False
    kind, wanted = ref
    result = []
    ordinal = re.search(r'\bitem\s+(\d+)\b', question, re.I)
    for doc in docs:
        text = str(doc.get('extracted_text') or '')
        headings = _headings(text, kind)
        for index, heading in enumerate(headings):
            if number(heading.group(1)) != wanted:
                continue
            left = heading.start()
            right = headings[index+1].start() if index+1 < len(headings) else len(text)
            if kind == 'section':
                # A parent section includes its children, ending at the next
                # sibling/ancestor rather than the first subsection heading.
                depth = len(str(wanted).split('.'))
                right = next((h.start() for h in headings[index+1:]
                              if len(h.group(1).split('.')) <= depth), len(text))
            if kind == 'regulation':
                next_chapter = CHAPTERS.search(text, heading.end())
                if next_chapter:
                    right = min(right, next_chapter.start())
            if ordinal and kind == 'chapter':
                rules = list(REGULATIONS.finditer(text, left, right))
                position = int(ordinal.group(1))-1
                if not 0 <= position < len(rules):
                    continue
                left = rules[position].start()
                right = rules[position+1].start() if position+1 < len(rules) else right
            for chunk in chunks:
                if chunk.document_id != str(doc['id']):
                    continue
                start, end = max(left, chunk.start), min(right, chunk.end)
                if start < end and text[start:end].strip():
                    result.append(replace(chunk, start=start, end=end, text=text[start:end], section=f'{kind.title()} {wanted}'))
    return result, True


def referenced_chunks(question, docs, chunks):
    current = question.split('\nPrevious user question (search context only): ')[0]
    target = current if reference(current) else question
    matches = list(REFERENCE.finditer(target))
    if not matches:
        return chunks, False
    queries = []
    for index, match in enumerate(matches):
        # Bind each side of a named-document comparison separately. Scope is
        # already authorized; a filename can narrow it, never expand it.
        stop = matches[index+1].start() if index+1 < len(matches) else len(target)
        clause = target[match.start():stop]
        if index == 0 and not re.search(r'\.(?:pdf|docx?|txt)\b', clause, re.I):
            clause = target[:match.start()] + clause
        names = re.findall(r'\b[\w.-]+\.(?:pdf|docx?|txt)\b', clause, re.I)
        named_docs = [d for d in docs if str(d['name']).lower() in clause.lower()]
        selected_docs = named_docs if named_docs or names else docs
        queries.append((match.group(), selected_docs))
        # Number lists such as "regulations 1 and 2" or "chapters I, II".
        tail = target[match.end():]
        listed = re.match(r'(?:(?:\s*,\s*|\s+and\s+)(?:\d+(?:\.\d+)*|[IVXLCDM]+)\b)+', tail, re.I)
        if listed:
            for value in re.findall(r'\b(?:\d+(?:\.\d+)*|[IVXLCDM]+)\b', listed.group(), re.I):
                queries.append((f'{match.group(1)} {value}', selected_docs))
    if len(queries) == 1:
        return _single_reference_chunks(target, queries[0][1], chunks)
    result = {}
    for query, selected_docs in queries:
        selected, _ = _single_reference_chunks(query, selected_docs, chunks)
        for chunk in selected:
            result[chunk.id] = chunk
    return list(result.values()), True
