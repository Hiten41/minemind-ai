import asyncio
import re
import math
from collections import Counter

from fastapi import HTTPException
from models.schemas import QueryRequest
from services.cognee_service import query_memory, MemoryProviderError
from services.document_search import _expanded_terms
from services.evidence import Chunk, document_chunks
from services.document_references import reference, referenced_chunks, adjacent_reference
from services.document_overview import is_document_overview

FOLLOWUP_CONTEXT = '\nPrevious user question (search context only): '
HISTORY_WINDOW = 20  # QueryRequest allows ten complete user/assistant exchanges.
FOLLOWUP_FILLER = set('this that these those it its they them their same what wht whats whts which kind kinds type types tell explain more details detail please why how about given previous user question search context only'.split())
SEARCH_FILLER = FOLLOWUP_FILLER | set('who is are was were has have had can could should would will did do does not enough alone also there here say says simple simply words language document documents guideline guide pdf chapter section regulation reported according based mean means need want know use using into all any each both check example summary detailed findings'.split())


def clean_question(question: str) -> str:
    question = re.sub(r'\[SRC_\d+\]', '', question, flags=re.I)
    return re.sub(r'^\s*(?:\\?-\s*)', '', question).strip().rstrip('\\').strip()


def _followup_terms(question: str) -> list[str]:
    return [term for term in _expanded_terms(question) if term not in FOLLOWUP_FILLER]


def _resolve_turn(question: str, previous: str, docs=None) -> str:
    question = clean_question(question)
    previous_reference = reference(previous)
    navigation = re.search(r'\b(next|previous)\s+(chapter|regulation|section)\b',question,re.I)
    if navigation and previous_reference and previous_reference[0] == navigation.group(2).lower():
        kind, value = previous_reference
        delta = -1 if navigation.group(1).lower() == 'previous' else 1
        if docs is not None:
            target = adjacent_reference(kind, value, delta, previous, docs)
            if target is None:
                return question
            value, document_name = target
            return f'{question}{FOLLOWUP_CONTEXT}{kind} {value} in {document_name}'
        parts = str(value).split('.')
        parts[-1] = str(max(0, int(parts[-1]) + delta))
        return f'{question}{FOLLOWUP_CONTEXT}{kind} {".".join(parts)}'
    current_reference = reference(question)
    if current_reference:
        if previous_reference and re.search(r'\b(compare|comparison|differ|difference)\b',question,re.I) and re.search(r'\b(this|that|it|previous)\b',question,re.I):
            kind, value = previous_reference
            names = [str(d['name']) for d in (docs or []) if str(d['name']).lower() in previous.lower()]
            names = names or re.findall(r'\b[\w.-]+\.(?:pdf|docx?|txt)\b', previous, re.I)
            document = f' in {names[0]}' if names else ''
            return f'Compare {kind} {value}{document} with {question}'
        return question
    ordinal = re.search(r'\b(first|second|third|fourth|fifth)\s+(one|item|regulation)\b', question, re.I)
    if ordinal and previous_reference and previous_reference[0] == 'chapter':
        position = ['first','second','third','fourth','fifth'].index(ordinal.group(1).lower())+1
        return f'{question}{FOLLOWUP_CONTEXT}chapter {previous_reference[1]} item {position}'
    follow_up = re.search(
        r'\b(this|that|these|those|it|its|they|them|their|same)\b|'
        r'^(?:what|wht|which)\s+(?:kind|kinds|type|types)\b|'
        r'^(?:and\b|why\b|how so\b|tell me more|explain more|in simple words|simplify|say that simply)|'
        r'^explain\s+(?:in\s+)?(?:simple(?:r)?\s+(?:words|language)|simply)\b|'
        r'^(?:is|can|could|does|did|should)\b|'
        r'^(?:who\s+(?:is|was|should|must)|what|wht)\s*(?:responsible|caused|were the corrective|was the cause|happened next)\b', question,re.I)
    if not follow_up or not previous:
        return question
    # Keep the immediately preceding subject when bounding nested context.
    return question + FOLLOWUP_CONTEXT + previous[:1600]


def retrieval_question(request: QueryRequest, docs=None) -> str:
    """Replay bounded USER turns so navigation and short follow-ups preserve resolved subjects."""
    previous = ''
    references = {}
    named_documents = set()
    for message in request.chat_history[-HISTORY_WINDOW:]:
        if message.role != 'user' or not message.content.strip():
            continue
        explicit_names = set(re.findall(r'\b[\w.-]+\.(?:pdf|docx?|txt)\b',message.content,re.I))
        explicit_names = {name.lower() for name in explicit_names}
        if explicit_names:
            comparison = bool(re.search(r'\b(compare|comparison|differ|difference)\b', message.content, re.I)
                              and re.search(r'\b(this|that|it|previous)\b', message.content, re.I))
            if explicit_names != named_documents and not comparison:
                previous = ''
                references.clear()
            named_documents = explicit_names
        navigation = re.search(r'\b(next|previous)\s+(chapter|regulation|section)\b', message.content, re.I)
        context = references.get(navigation.group(2).lower(), '') if navigation else previous
        resolved = _resolve_turn(message.content, context, docs)
        resolved_reference = reference(resolved)
        if resolved_reference:
            references[resolved_reference[0]] = resolved
        # Keep context in chronological order, without repeatedly copying filler-only turns.
        if _followup_terms(clean_question(message.content)):
            previous = resolved
    navigation = re.search(r'\b(next|previous)\s+(chapter|regulation|section)\b', request.question, re.I)
    explicit_names = {name.lower() for name in re.findall(r'\b[\w.-]+\.(?:pdf|docx?|txt)\b',request.question,re.I)}
    comparison = bool(re.search(r'\b(compare|comparison|differ|difference)\b', request.question, re.I)
                      and re.search(r'\b(this|that|it|previous)\b', request.question, re.I))
    if explicit_names and explicit_names != named_documents and not comparison:
        previous = ''
        references.clear()
    context = references.get(navigation.group(2).lower(), '') if navigation else previous
    return _resolve_turn(request.question, context, docs)


def select_documents(request: QueryRequest, documents: list[dict]) -> list[dict]:
    available = [d for d in documents if d.get('status') not in {'delete_pending','delete_failed','deleted'}]
    if request.scope_mode == 'selected':
        wanted = set(request.document_ids)
        if wanted - {str(d['id']) for d in available}:
            raise HTTPException(400, 'Selected documents are unavailable')
        return [d for d in available if str(d['id']) in wanted]
    if request.scope_mode == 'auto':
        explicit = [d for d in available if str(d['name']).lower() in request.question.lower()]
        contextual = retrieval_question(request).lower()
        prior = []
        for message in reversed(request.chat_history[-HISTORY_WINDOW:]):
            if message.role == 'user':
                prior = [d for d in available if str(d['name']).lower() in message.content.lower()]
                if prior:
                    break
        # Numbered navigation replaces search context, but does not imply a
        # switch away from the document the user was discussing.
        comparison = bool(re.search(r'\b(compare|comparison|differ|difference)\b',request.question,re.I)
                          and re.search(r'\b(this|that|it|previous)\b',request.question,re.I))
        if explicit and comparison:
            ids = {str(d['id']) for d in explicit + prior}
            return [d for d in available if str(d['id']) in ids]
        if not explicit:
            explicit = [d for d in available if str(d['name']).lower() in contextual]
            if not explicit and (reference(request.question) or FOLLOWUP_CONTEXT.lower() in contextual):
                explicit = prior
        return explicit or available
    return available


def lexical_score(text: str, terms: list[str]) -> int:
    return sum(len(re.findall(r'\b'+re.escape(term)+r'\b',text.lower())) for term in terms)


def lexical_ranking(chunks: list[Chunk], question: str) -> list[tuple[Chunk, float]]:
    """Saturating, rarity-weighted matches; the latest question outweighs older context."""
    def tokens(text):
        return re.findall(r'[a-z0-9]+', text.lower())
    # A filename selects a document; its date/title tokens are not the subject
    # of the question and must not make a cover page outrank the requested facts.
    question = re.sub(r'\b[\w.-]+\.(?:pdf|docx?|txt)\b', '', question, flags=re.I)
    parts = question.split(FOLLOWUP_CONTEXT)
    weights = {}
    for depth, part in enumerate(parts):
        for term in _expanded_terms(part):
            if term in SEARCH_FILLER:
                continue
            weights[term] = max(weights.get(term, 0), 1.0 if depth == 0 else 0.25 / depth)
    # Acronyms identify the retained programme/metric even several turns back.
    # Do not demote them below generic words such as "operations" in a comparison.
    for label in re.findall(r'\b[A-Z][A-Z0-9]{1,9}\b',question):
        weights[label.lower()] = max(weights.get(label.lower(),0),1.5)
    counts = [Counter(tokens((c.section or '')+' '+c.text)) for c in chunks]
    lengths = [sum(count.values()) for count in counts]
    average = sum(lengths) / max(1, len(lengths)) or 1
    frequencies = {term: sum(bool(count.get(term)) for count in counts) for term in weights}
    broad_findings = bool(re.search(
        r'\bwhat happened\b|\bwhy\b.*\b(?:happen|occur)|\bwhat caused\b|\b(?:main|key|contributing|causal|root) (?:findings|factors|causes)\b|'
        r'\bsummari[sz]e (?:the |this )?(?:report|document|accident|incident)\b', parts[0], re.I))
    scores = []
    current_tokens = tokens(parts[0])
    phrases = [(a,b) for a,b in zip(current_tokens,current_tokens[1:]) if a in weights and b in weights]
    for chunk, count, length in zip(chunks, counts, lengths):
        score = 0.0
        if broad_findings and re.fullmatch(r'(?:executive )?summary|overview|conclusions?|root cause analysis', chunk.section or '', re.I):
            score += 6.0
        rarity_by_term = {}
        for term, weight in weights.items():
            tf = count.get(term, 0)
            if tf:
                rarity = math.log(1 + (len(chunks) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                rarity_by_term[term] = rarity
                score += weight * rarity * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
        normalized = ' ' + ' '.join(tokens(chunk.text)) + ' '
        for a,b in phrases:
            if f' {a} {b} ' in normalized:
                score += 2 * (rarity_by_term.get(a,0) + rarity_by_term.get(b,0))
        scores.append((chunk, score))
    return sorted(scores, key=lambda item:item[1], reverse=True)


async def retrieve(question: str, docs: list[dict], limit: int = 10) -> tuple[list[Chunk], dict]:
    chunks = [c for d in docs for c in document_chunks(d)]
    if is_document_overview(question):
        # Overview questions have no topical keywords. Cover the introduction,
        # then distinct sections and distributed locations within authorized docs.
        selected = []
        per_doc = [[c for c in chunks if c.document_id == str(d['id'])] for d in docs]
        queues = []
        for group in per_doc:
            sections = {}
            for c in group:
                if c.section:
                    sections.setdefault(c.section, c)
            distributed = [group[round(i*(len(group)-1)/max(1,limit-1))] for i in range(limit)] if group else []
            queues.append(list(dict.fromkeys(group[:1] + list(sections.values()) + distributed)))
        while any(queues) and len(selected) < limit:
            for queue in queues:
                if queue and len(selected) < limit:
                    selected.append(queue.pop(0))
        return selected, {'lexical_candidates':len(chunks), 'semantic':'not_requested',
            'selected_chunks':len(selected), 'overview_retrieval':True,
            'retrieved_document_ids':sorted({c.document_id for c in selected}),
            'authorized_document_count':len(docs), 'context_character_budget':limit*1200}
    chunks, has_reference = referenced_chunks(question, docs, chunks)
    ranked = lexical_ranking(chunks, question)
    current = question.split(FOLLOWUP_CONTEXT)[0]
    if has_reference and re.fullmatch(r'(?:explain\s+)?(?:regulation|reg\.?)\s*(?:\d+|[ivxlcdm]+)(?:\s*:\s*[^?]+?)?(?:\s+explain)?[?.!]*', current, re.I):
        ranked = [(c, 1.0) for c in chunks]
    lexical = [c for c, score in ranked if has_reference or score > 0][:32]
    if not has_reference and lexical:
        # Keep continuations of the strongest passages: a definition or scope
        # statement can place its exception just beyond a chunk boundary.
        expanded=[]
        for candidate in lexical[:2]:
            expanded.append(candidate)
            following=next((c for c in chunks if c.document_id==candidate.document_id
                            and c.page==candidate.page and 0 <= c.start-candidate.end <= 8),None)
            if following and following not in expanded:
                expanded.append(following)
        lexical=list(dict.fromkeys(expanded+lexical))
    if FOLLOWUP_CONTEXT in question and not has_reference:
        # Keep a small amount of earlier evidence for elliptical questions such
        # as "how many operations was that based on?" without dominating ranking.
        context = question.split(FOLLOWUP_CONTEXT,1)[1]
        anchors = [c for c,score in lexical_ranking(chunks,context) if score > 0][:2]
        lexical = lexical[:max(0,limit-len(anchors))] + [c for c in anchors if c not in lexical[:max(0,limit-len(anchors))]] + lexical[max(0,limit-len(anchors)):]
    diagnostics = {'lexical_candidates':len(lexical),'semantic':'not_requested','rejected_semantic_results':0}
    semantic = []
    if docs and not has_reference:
        try:
            recalled = await asyncio.wait_for(query_memory(question,[str(d['dataset_name']) for d in docs],top_k=12),timeout=14)
            diagnostics['semantic'] = 'ok'
            for item in recalled:
                text = str(item.get('text',''))
                source = str(item.get('source',''))
                # Provider text is only a retrieval hint. Trust solely exact stored spans.
                matches = [c for c in chunks if source in {c.dataset,c.title} and
                           (c.text in text or (len(text.strip())>=25 and text.strip() in c.text))]
                if not matches:
                    diagnostics['rejected_semantic_results'] += 1
                semantic.extend(matches)
        except (MemoryProviderError, TimeoutError):
            diagnostics['semantic'] = 'unavailable'
    scores = {}
    by_id = {}
    for candidates in [lexical,semantic]:
        seen = set()
        for rank,c in enumerate(candidates):
            if c.id in seen:
                continue
            seen.add(c.id)
            by_id[c.id] = c
            scores[c.id] = scores.get(c.id,0)+1/(60+rank+1)
    ordered = [by_id[key] for key in sorted(scores,key=scores.get,reverse=True)]
    # Reserve coverage for each matching document before filling remaining context.
    # Preserve the strongest content matches when old semantic page-sized hits
    # expand to many newly separated sections. They must not crowd out direct
    # evidence for the current question.
    prioritized = list(dict.fromkeys(lexical[:2] + ordered))
    selected = []
    covered = set()
    for c in prioritized:
        if c.document_id not in covered:
            selected.append(c); covered.add(c.document_id)
            if len(selected) == limit:
                break
    for c in prioritized:
        if len(selected) >= limit:
            break
        if c not in selected:
            selected.append(c)
    diagnostics['selected_chunks'] = len(selected)
    diagnostics['retrieved_document_ids'] = sorted({c.document_id for c in selected})
    diagnostics['authorized_document_count'] = len(docs)
    diagnostics['context_character_budget'] = limit * 1200
    return selected, diagnostics
