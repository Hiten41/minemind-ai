import re
from pathlib import Path

from services.auth_service import _connect, list_documents
from services.settings import STORAGE_ROOT


COGNEE_ROOT = STORAGE_ROOT
USER_TEXT_ROOT = COGNEE_ROOT / "user_text"
LEGACY_TEXT_ROOT = COGNEE_ROOT / "data"

MINING_SYNONYMS = {
    "death": ["fatal", "killed", "deceased", "loss of life", "expiry"],
    "dies": ["death", "fatal", "killed", "deceased", "loss of life"],
    "die": ["death", "fatal", "killed", "deceased", "loss of life"],
    "accident": ["occurrence", "injury", "serious bodily injury"],
    "report": ["notice", "form iv-a", "form iv-b", "inquiry", "enquiry"],
    "notify": ["notice", "inform", "chief inspector", "regional inspector"],
}

STOP_WORDS = {
    "according",
    "uploaded",
    "pdf",
    "pdfs",
    "what",
    "must",
    "done",
    "does",
    "someone",
    "person",
    "mine",
    "mines",
    "from",
    "your",
    "about",
    "when",
    "then",
}


def store_document_text(user_id: str, doc_id: str, text: str) -> str:
    user_dir = USER_TEXT_ROOT / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    text_path = user_dir / f"{doc_id}.txt"
    text_path.write_text(text, encoding="utf-8", errors="ignore")
    return str(text_path)


def estimate_node_count(text: str) -> int:
    return max(10, len(text) // 500)


def _tokens(value: str) -> list[str]:
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Za-z])(\d)", r"\1 \2", value)
    value = re.sub(r"(\d)([A-Za-z])", r"\1 \2", value)
    return [
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in STOP_WORDS and token not in {"the", "and", "for"}
    ]


def _expanded_terms(question: str) -> list[str]:
    terms = set(_tokens(question))
    lowered = question.lower()
    for key, synonyms in MINING_SYNONYMS.items():
        if key in lowered or key in terms:
            terms.update(_tokens(" ".join(synonyms)))
            terms.update(synonyms)
    return sorted(terms, key=len, reverse=True)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _legacy_text_for_doc(doc: dict) -> str:
    if not LEGACY_TEXT_ROOT.exists():
        return ""

    doc_terms = _tokens(Path(str(doc.get("name", ""))).stem)
    if not doc_terms:
        return ""

    best_score = 0
    best_text = ""
    for path in LEGACY_TEXT_ROOT.glob("text_*.txt"):
        if path.stat().st_size < 1000:
            continue
        text = _read_text(path)
        head = text[:12000].lower()
        score = 0
        for term in doc_terms:
            if term in head:
                score += 2 if term.isdigit() else 1
        if "regulations" in head and "regulation" in doc_terms:
            score += 1
        if "rules" in head and "rules" in doc_terms:
            score += 1
        if score > best_score:
            best_score = score
            best_text = text

    return best_text if best_score >= 2 else ""


def _document_text(doc: dict) -> str:
    text_path = doc.get("text_path")
    if text_path:
        path = Path(str(text_path))
        if path.exists():
            return _read_text(path)
    return _legacy_text_for_doc(doc)


def rank_relevant_documents(
    user_id: str,
    question: str,
    limit: int = 40,
    focused_sources: set[str] | None = None,
) -> list[dict]:
    docs = list_documents(user_id)
    if focused_sources:
        focused_docs = [
            doc for doc in docs
            if str(doc["name"]).lower() in focused_sources
        ]
        if focused_docs:
            return focused_docs[:limit]

    terms = _expanded_terms(question)
    if not terms:
        return docs[:limit]

    ranked: list[tuple[int, str, dict]] = []
    for doc in docs:
        name = str(doc.get("name", ""))
        haystack = f"{name} {doc.get('type', '')}".lower()
        score = sum(3 for term in terms if term in haystack)
        text = _document_text(doc)
        if text:
            head = text[:16000].lower()
            score += sum(1 for term in terms if term in head)
        ranked.append((score, str(doc.get("uploaded_at", "")), doc))

    relevant = [
        doc for score, _uploaded_at, doc in sorted(
            ranked,
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )
        if score > 0
    ]
    return (relevant or docs)[:limit]


def _score_line(line: str, terms: list[str]) -> int:
    lowered = line.lower()
    score = 0
    for term in terms:
        if " " in term:
            if term in lowered:
                score += 4
        elif re.search(rf"\b{re.escape(term)}\b", lowered):
            score += 2
    return score


def _best_windows(doc_name: str, text: str, terms: list[str], limit: int) -> list[tuple[int, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    scored: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        score = _score_line(line, terms)
        if score:
            scored.append((score, index))

    windows: list[tuple[int, str]] = []
    used_ranges: list[range] = []
    for score, index in sorted(scored, reverse=True):
        start = max(0, index - 5)
        end = min(len(lines), index + 8)
        current = range(start, end)
        if any(index in used for used in used_ranges):
            continue
        used_ranges.append(current)
        chunk = "\n".join(lines[start:end])
        windows.append((
            score,
            f"Document: {doc_name}\nMatched uploaded PDF text:\n{chunk[:1800]}"
        ))
        if len(windows) >= limit:
            break
    return windows


def search_uploaded_texts(
    user_id: str,
    question: str,
    limit: int = 4,
    allowed_sources: set[str] | None = None,
) -> list[dict[str, str]]:
    terms = _expanded_terms(question)
    if not terms:
        return []

    results: list[tuple[int, dict[str, str]]] = []
    for doc in list_documents(user_id):
        doc_name = str(doc["name"])
        if allowed_sources and doc_name.lower() not in allowed_sources:
            continue
        text = _document_text(doc)
        if not text:
            continue
        for score, chunk in _best_windows(doc_name, text, terms, limit):
            results.append((score, {
                "text": chunk,
                "source": doc_name or str(doc.get("dataset_name") or "Uploaded document"),
            }))

    return [
        chunk
        for _score, chunk in sorted(results, key=lambda item: item[0], reverse=True)[:limit]
    ]


def repair_document_node_counts(user_id: str) -> None:
    updates: list[tuple[int, str]] = []
    for doc in list_documents(user_id):
        if int(doc.get("node_count") or 0) > 0:
            continue
        text = _document_text(doc)
        node_count = estimate_node_count(text) if text else 10
        updates.append((node_count, str(doc["id"])))

    if not updates:
        return

    with _connect() as conn:
        for node_count, doc_id in updates:
            conn.execute(
                "UPDATE documents SET node_count = %s WHERE id = %s",
                (node_count, doc_id),
            )


def _label_from_chunk(chunk: str, fallback: str) -> str:
    for line in chunk.splitlines():
        line = line.strip(" -\t")
        if not line or line.startswith("Document:") or line.startswith("Matched uploaded"):
            continue
        if len(line) < 12:
            continue
        return line[:80]
    return fallback


def build_uploaded_text_graph(user_id: str) -> dict[str, list[dict[str, object]]]:
    graph_query = (
        "accident notice fatal death loss of life inspector manager inquiry "
        "safety ventilation equipment machinery rescue medical rules regulations"
    )
    terms = _expanded_terms(graph_query) + _tokens(graph_query)
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []

    for doc_index, doc in enumerate(list_documents(user_id)):
        doc_id = f"doc_{doc_index}"
        doc_name = str(doc["name"])
        nodes.append({
            "id": doc_id,
            "label": doc_name,
            "type": str(doc.get("type") or "regulation"),
            "data": {
                "full_text": (
                    f"Uploaded document: {doc_name}\n"
                    f"Dataset: {doc.get('dataset_name', '')}"
                )
            },
        })

        text = _document_text(doc)
        if not text:
            continue

        windows = _best_windows(doc_name, text, terms, limit=6)
        for chunk_index, (_score, chunk) in enumerate(windows, start=1):
            text_lower = chunk.lower()
            node_type = "regulation"
            if "accident" in text_lower or "fatal" in text_lower:
                node_type = "incident"
            elif "equipment" in text_lower or "machinery" in text_lower:
                node_type = "equipment"
            elif "medical" in text_lower:
                node_type = "maintenance"
            elif "inspection" in text_lower or "inspector" in text_lower:
                node_type = "inspection"

            node_id = f"{doc_id}_chunk_{chunk_index}"
            nodes.append({
                "id": node_id,
                "label": _label_from_chunk(chunk, f"{doc_name} topic {chunk_index}"),
                "type": node_type,
                "data": {"full_text": chunk},
            })
            edges.append({
                "id": f"edge_{doc_id}_{chunk_index}",
                "source": doc_id,
                "target": node_id,
                "label": "contains",
            })
            if chunk_index > 1:
                edges.append({
                    "id": f"edge_{doc_id}_{chunk_index - 1}_{chunk_index}",
                    "source": f"{doc_id}_chunk_{chunk_index - 1}",
                    "target": node_id,
                    "label": "related_to",
                })

    return {"nodes": nodes, "edges": edges}
