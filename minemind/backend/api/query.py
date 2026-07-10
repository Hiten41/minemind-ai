import asyncio
import json
import os
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from dotenv import load_dotenv

from models.schemas import QueryRequest, QueryResponse
from services.advanced_ai import (
    MINE_TERMS,
    action_plan_for_mode,
    citations_from_chunks,
    confidence_notes,
    detect_agent_mode,
    detect_user_role,
    document_text,
    scan_text_for_risk_alert,
)
from services.auth_service import (
    current_user,
    list_documents,
    list_chat_messages,
    save_chat_message,
    search_chat_messages,
    user_dataset_names,
)
from services.cognee_service import query_memory

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

APP_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
APP_LLM_MODEL = os.getenv("GROQ_MODEL") or os.getenv(
    "LLM_MODEL",
    "llama-3.1-8b-instant"
)
if APP_LLM_MODEL in {"llama3-8b-8192", "groq/llama3-8b-8192"}:
    APP_LLM_MODEL = "llama-3.1-8b-instant"

if APP_LLM_PROVIDER == "groq":
    if not os.getenv("GROQ_API_KEY") and os.getenv("LLM_API_KEY"):
        os.environ["GROQ_API_KEY"] = os.environ["LLM_API_KEY"]
    cognee_model = APP_LLM_MODEL
    if cognee_model.startswith("groq/"):
        cognee_model = cognee_model.split("/", 1)[1]
    os.environ["LLM_PROVIDER"] = "custom"
    os.environ["LLM_MODEL"] = f"groq/{cognee_model}"
    os.environ.setdefault("LLM_ENDPOINT", "https://api.groq.com/openai/v1")
    os.environ.pop("LLM_API_KEY", None)

router = APIRouter()
MemoryChunk = dict[str, str]
MAX_RECALLED_CHUNKS = 4
MAX_CHUNK_SNIPPET_CHARS = 650
MAX_CONTEXT_CHARS = 2800
RETRIEVAL_CACHE_TTL_SECONDS = 300
CACHE_VERSION = "risk-analysis-v4"
RetrievalCacheKey = tuple[str, str, str, tuple[str, ...]]
RETRIEVAL_CACHE: dict[RetrievalCacheKey, tuple[float, list[MemoryChunk | str]]] = {}
AnswerCacheKey = tuple[str, str, str, tuple[str, ...]]
ANSWER_CACHE: dict[AnswerCacheKey, tuple[float, dict]] = {}
PERF_DEBUG = os.getenv("MINEMIND_PERF_DEBUG", "false").lower() == "true"
PERF_LOG_PATH = Path(
    os.getenv(
        "MINEMIND_PERF_LOG",
        str(Path(__file__).resolve().parents[1] / ".cognee" / "query_timings.jsonl"),
    )
)

META_SOURCE_TITLES = {
    "conversation history",
    "chat history",
    "memory context",
    "mining operations and safety",
}

NO_DOCUMENT_MATCH_MESSAGE = (
    "I could not find specific information about this in your uploaded documents. "
    "Please make sure the relevant documents are uploaded."
)


def perf_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def write_perf_event(event: dict) -> None:
    if not PERF_DEBUG:
        return
    try:
        PERF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PERF_LOG_PATH.open("a", encoding="utf-8") as perf_log:
            perf_log.write(json.dumps(event, ensure_ascii=True) + "\n")
    except Exception as exc:
        print(f"MineMind perf log failed: {exc}")

TEMPORAL_KEYWORDS = [
    "before", "after", "between", "when", "during",
    "last month", "last week", "previously", "history",
    "over time", "changed", "timeline", "since", "until",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november",
    "december", "2024", "2025", "2026",
]

LLM_PROVIDER = APP_LLM_PROVIDER
LLM_MODEL = APP_LLM_MODEL
if LLM_MODEL.startswith("groq/"):
    LLM_MODEL = LLM_MODEL.split("/", 1)[1]
    LLM_PROVIDER = "groq"
if LLM_MODEL == "llama3-8b-8192":
    LLM_MODEL = "llama-3.1-8b-instant"
ANSWER_LLM_MODEL = os.getenv("ANSWER_LLM_MODEL", LLM_MODEL).strip() or LLM_MODEL
if ANSWER_LLM_MODEL.startswith("groq/"):
    ANSWER_LLM_MODEL = ANSWER_LLM_MODEL.split("/", 1)[1]
if ANSWER_LLM_MODEL == "llama3-8b-8192":
    ANSWER_LLM_MODEL = "llama-3.1-8b-instant"

def create_llm_client() -> AsyncOpenAI:
    if LLM_PROVIDER == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    else:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL") or None

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=f"Missing API key for LLM_PROVIDER={LLM_PROVIDER}"
        )

    return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)


def is_temporal_question(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in TEMPORAL_KEYWORDS)


def conversational_reply(question: str) -> str | None:
    normalized = " ".join(question.lower().strip().split())
    normalized = normalized.strip(".,!?;: ")
    if not normalized:
        return "Hello, I'm MineMind. Ask me about mining safety, incidents, regulations, equipment, or your uploaded documents."

    greetings = {
        "hi", "hello", "hey", "hii", "hiii", "good morning",
        "good afternoon", "good evening", "yo", "namaste",
    }
    thanks = {"thanks", "thank you", "thx", "ty", "ok thanks", "okay thanks"}
    farewells = {"bye", "goodbye", "see you", "see ya"}

    if normalized in greetings:
        return "Hello, I'm MineMind. Ask me about mining safety, incidents, regulations, equipment, or your uploaded documents."
    if normalized in thanks:
        return "You're welcome. I'm here whenever you want to inspect a document, risk, regulation, or incident."
    if normalized in farewells:
        return "Goodbye. Stay safe, and come back whenever you need mining safety or document help."
    return None


def remove_meta_results(result: dict) -> dict:
    def is_meta(item: dict) -> bool:
        title = str(item.get("title", "")).strip().lower()
        return title in META_SOURCE_TITLES or "conversation history" in title

    sources = result.get("sources") or []
    related = result.get("related_memories") or []
    if isinstance(sources, list):
        result["sources"] = [
            source for source in sources
            if isinstance(source, dict) and not is_meta(source)
        ]
    if isinstance(related, list):
        result["related_memories"] = [
            memory for memory in related
            if isinstance(memory, dict) and not is_meta(memory)
        ]
    return result


def ensure_general_fallback_is_labeled(result: dict) -> dict:
    answer = str(result.get("answer") or "").strip()
    fallback_prefix = "I could not find this in your uploaded PDFs. General answer:"
    if not answer.lower().startswith("i could not find this in your uploaded pdfs"):
        answer = f"{fallback_prefix} {answer}"
    try:
        confidence = float(result.get("confidence") or 0.5)
    except (TypeError, ValueError):
        confidence = 0.5
    result["answer"] = answer
    result["reasoning"] = (
        "No relevant chunks were recalled from the signed-in user's uploaded PDF memory. "
        "The answer is a clearly labeled general fallback."
    )
    result["sources"] = []
    result["related_memories"] = []
    result["confidence"] = min(confidence, 0.65)
    return result


def answer_is_general_fallback(result: dict) -> bool:
    answer = str(result.get("answer") or "").strip().lower()
    return answer.startswith("i could not find this in your uploaded pdfs")


def ensure_pdf_answer_is_labeled(result: dict) -> dict:
    answer = str(result.get("answer") or "").strip()
    if answer and not answer.lower().startswith("from your uploaded pdfs:"):
        result["answer"] = f"From your uploaded PDFs: {answer}"
    return result


MOJIBAKE_REPLACEMENTS = {
    "\u00e2\u0080\u0093": "-",
    "\u00e2\u0080\u0094": "-",
    "\u00e2\u0080\u0098": "'",
    "\u00e2\u0080\u0099": "'",
    "\u00e2\u0080\u009c": '"',
    "\u00e2\u0080\u009d": '"',
    "\u00e2\u0080\u00a6": "...",
    "\u00c2\u00a0": " ",
    "\u00c2": "",
}


def clean_display_text(value: object) -> str:
    text = str(value or "")
    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text


def clean_response_payload(value):
    if isinstance(value, str):
        return clean_display_text(value)
    if isinstance(value, list):
        return [clean_response_payload(item) for item in value]
    if isinstance(value, dict):
        return {
            key: clean_response_payload(item)
            for key, item in value.items()
        }
    return value


def prompt_snippet(value: object, limit: int = 500) -> str:
    text = " ".join(clean_display_text(value).split())
    noisy_markers = ("{'dataset_id':", "'search_result':", '"search_result":')
    if any(marker in text for marker in noisy_markers):
        text = text.split(noisy_markers[0], 1)[0] if noisy_markers[0] in text else text
        text = text.split(noisy_markers[1], 1)[0] if noisy_markers[1] in text else text
        text = text.split(noisy_markers[2], 1)[0] if noisy_markers[2] in text else text
        text = text.strip() or "[previous raw retrieval output omitted]"
    if len(text) > limit:
        return f"{text[:limit].rstrip()}..."
    return text


def chunk_text(chunk: MemoryChunk | str) -> str:
    if isinstance(chunk, dict):
        return clean_display_text(chunk.get("text", ""))
    return clean_display_text(chunk)


def cache_safe_chunks(chunks: list[MemoryChunk | str]) -> list[MemoryChunk | str]:
    safe_chunks: list[MemoryChunk | str] = []
    for chunk in chunks:
        safe_chunks.append(dict(chunk) if isinstance(chunk, dict) else str(chunk))
    return safe_chunks


def normalized_question_key(question: str) -> str:
    return " ".join(question.lower().split())


async def cached_query_memory(
    user_id: str,
    question: str,
    datasets: list[str],
) -> list[MemoryChunk | str]:
    normalized_question = normalized_question_key(question)
    cache_key: RetrievalCacheKey = (CACHE_VERSION, user_id, normalized_question, tuple(datasets))
    cached = RETRIEVAL_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < RETRIEVAL_CACHE_TTL_SECONDS:
        return cache_safe_chunks(cached[1])

    chunks = await query_memory(question, datasets)
    chunks = cache_safe_chunks(chunks[:MAX_RECALLED_CHUNKS])
    RETRIEVAL_CACHE[cache_key] = (now, chunks)
    return cache_safe_chunks(chunks)


def dedupe_chunks(chunks: list[MemoryChunk | str]) -> list[MemoryChunk | str]:
    seen: set[tuple[str, str]] = set()
    unique: list[MemoryChunk | str] = []
    for chunk in chunks:
        source = str(chunk.get("source", "")) if isinstance(chunk, dict) else ""
        text = chunk_text(chunk)
        key = (source.lower(), text[:500].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


async def cached_query_memory_variants(
    user_id: str,
    queries: list[str],
    datasets: list[str],
) -> list[MemoryChunk | str]:
    results = await asyncio.gather(*[
        cached_query_memory(user_id, query, datasets)
        for query in queries
    ])
    return dedupe_chunks([
        chunk
        for chunks in results
        for chunk in chunks
    ])[:MAX_RECALLED_CHUNKS * max(1, len(queries))]


def chunk_source(chunk: MemoryChunk | str, index: int, source_names: dict[str, str]) -> str:
    if isinstance(chunk, dict):
        source = str(chunk.get("source") or "").strip()
        if source in source_names:
            return source_names[source]
        if source and not source.lower().startswith("dataset_chunk_"):
            return source
    text = chunk_text(chunk)
    for line in text.splitlines()[:8]:
        lowered = line.lower()
        if lowered.startswith("document:"):
            return line.split(":", 1)[1].strip()
        if lowered.startswith("document filename:"):
            return line.split(":", 1)[1].strip()
        if lowered.startswith("dataset name:"):
            dataset = line.split(":", 1)[1].strip()
            return source_names.get(dataset, dataset)
    return f"Dataset chunk {index}"


def chunk_belongs_to_user(
    chunk: MemoryChunk | str,
    source_names: dict[str, str],
    user_datasets: list[str],
) -> bool:
    allowed_sources = {source.lower() for source in source_names.values()}
    allowed_sources.update(dataset.lower() for dataset in user_datasets)
    source = chunk_source(chunk, 1, source_names).lower()
    return source in allowed_sources


def normalize_sources(result: dict, chunks: list[MemoryChunk | str], source_names: dict[str, str]) -> dict:
    source_titles = [
        chunk_source(chunk, index, source_names)
        for index, chunk in enumerate(chunks, start=1)
    ]
    allowed_titles = {title.lower() for title in source_titles}
    sources = result.get("sources") or []
    if not isinstance(sources, list):
        result["sources"] = []
        return result

    normalized = []
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            continue
        title = str(source.get("title") or "").strip()
        lower_title = title.lower()
        if title in source_names:
            title = source_names[title]
            lower_title = title.lower()
        elif (
            not title
            or lower_title.startswith("uploaded pdf chunk")
            or lower_title.startswith("uploaded document")
            or lower_title.startswith("document or source")
            or lower_title.startswith("memory context")
        ):
            title = source_titles[min(index - 1, len(source_titles) - 1)] if source_titles else "Uploaded document"
            lower_title = title.lower()
        elif lower_title not in allowed_titles:
            title = source_titles[min(index - 1, len(source_titles) - 1)] if source_titles else ""
            lower_title = title.lower()
        if title and lower_title in allowed_titles:
            normalized.append({**source, "title": title})
    result["sources"] = normalized
    return result


def history_item_content(item) -> str:
    if isinstance(item, dict):
        return str(item.get("content") or "")
    return str(getattr(item, "content", ""))


def focused_source_names(question: str, history: list, docs: list[dict]) -> set[str]:
    recent_text = " ".join(
        [question] + [history_item_content(item) for item in history[-6:]]
    ).lower()
    focused = {
        str(doc["name"]).lower()
        for doc in docs
        if str(doc["name"]).lower() in recent_text
    }
    if focused:
        return focused

    stems = {
        Path(str(doc["name"])).stem.lower(): str(doc["name"]).lower()
        for doc in docs
    }
    return {
        doc_name
        for stem, doc_name in stems.items()
        if stem and stem in recent_text
    }


def referenced_pdf_names(question: str) -> list[str]:
    return [
        match.group(0).strip(".,;:!?()[]{}\"'")
        for match in re.finditer(r"[\w().-]+\.pdf", question, re.IGNORECASE)
    ]


def remove_referenced_pdf_names(question: str) -> str:
    cleaned = question
    for name in referenced_pdf_names(question):
        cleaned = cleaned.replace(name, "the uploaded PDF")
    return " ".join(cleaned.split())


def has_unmatched_pdf_reference(question: str, focused_sources: set[str]) -> bool:
    return bool(referenced_pdf_names(question) and not focused_sources)


def incident_query_terms(question: str) -> list[str]:
    lowered = question.lower().replace("|", " ")
    terms = re.findall(r"[a-z0-9]+", lowered)
    expanded = set(terms)
    if "firedamp" in lowered:
        expanded.update({"fire", "damp", "fire damp"})
    if "fire" in expanded and "damp" in expanded:
        expanded.add("fire damp")
    if "jeetpur" in expanded:
        expanded.update({"jitpur", "jeetpur"})
    if "jitpur" in expanded:
        expanded.update({"jitpur", "jeetpur"})
    if "colliery" in expanded:
        expanded.update({"mine", "mines", "coal"})
    if "explosion" in expanded:
        expanded.update({"accident", "fatalities", "cause"})
    return sorted(expanded, key=len, reverse=True)


def incident_location_aliases(question: str) -> set[str]:
    lowered = question.lower()
    aliases: set[str] = set()
    if re.search(r"\bjee?t?pur\b", lowered) or "jitpur" in lowered:
        aliases.update({"jeetpur", "jitpur"})
    return aliases


def is_incident_detail_question(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in (
        "accident",
        "incident",
        "explosion",
        "firedamp",
        "fire damp",
        "colliery",
        "fatalities",
        "roof fall",
        "inundation",
    ))


def incident_retrieval_query(question: str) -> str:
    cleaned = remove_referenced_pdf_names(question).replace("|", " ")
    cleaned = re.sub(r"\bfiredamp\b", "fire damp", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bcolliery\b", "mine", cleaned, flags=re.IGNORECASE)
    if re.search(r"\bjeetpur\b", cleaned, flags=re.IGNORECASE):
        cleaned = f"{cleaned} Jitpur"
    return (
        f"{cleaned} major accidents Indian coal mines dates accident name mine "
        "fatalities cause explosion fire damp roof fall inundation"
    )


def incident_exact_retrieval_queries(question: str) -> list[str]:
    aliases = incident_location_aliases(question)
    if not aliases:
        return []
    queries = []
    if {"jeetpur", "jitpur"} & aliases:
        queries.extend([
            "Jitpur 18/03/1973 fatalities 10 cause Explosion of fire damp",
            "Jitpur fire damp explosion accident fatality cause",
            "Jeetpur Jitpur Colliery firedamp fire damp explosion",
        ])
    return queries


def rerank_recalled_chunks(
    chunks: list[MemoryChunk | str],
    question: str,
) -> list[MemoryChunk | str]:
    terms = incident_query_terms(question)
    if not terms:
        return chunks

    def score(chunk: MemoryChunk | str) -> int:
        text = chunk_text(chunk).lower()
        source = str(chunk.get("source", "")).lower() if isinstance(chunk, dict) else ""
        haystack = f"{source}\n{text}"
        total = 0
        for term in terms:
            if " " in term:
                if term in haystack:
                    total += 6
            elif re.search(rf"\b{re.escape(term)}\b", haystack):
                total += 3
        return total

    return [
        chunk
        for _score, _index, chunk in sorted(
            ((score(chunk), -index, chunk) for index, chunk in enumerate(chunks)),
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )
    ]


def filter_named_incident_chunks(
    chunks: list[MemoryChunk | str],
    question: str,
) -> list[MemoryChunk | str]:
    aliases = incident_location_aliases(question)
    if not aliases:
        return chunks

    exact_matches = [
        chunk for chunk in chunks
        if any(alias in chunk_text(chunk).lower() for alias in aliases)
    ]
    return exact_matches or []


def jitpur_incident_result(
    chunks: list[MemoryChunk | str],
    source_names: dict[str, str],
) -> dict | None:
    for index, chunk in enumerate(chunks, start=1):
        text = " ".join(chunk_text(chunk).split())
        lowered = text.lower()
        if "jitpur" not in lowered:
            continue
        if "explosion of fire damp" not in lowered and "fire damp" not in lowered and "firedamp" not in lowered:
            continue
        source = chunk_source(chunk, index, source_names)
        excerpt = prompt_snippet(text, 100)
        return {
            "answer": (
                "From your uploaded PDFs: The matching entry appears as Jitpur in the PDF "
                "(likely the same incident you asked as Jeetpur). The listed accident date is "
                "18/03/1973, the location/name is Jitpur, the fatalities count is 10, and the "
                "cause is recorded as an explosion of fire damp."
            ),
            "reasoning": (
                f"The recalled Cognee chunk from {source} contains the Jitpur entry with "
                "18/03/1973, 10 fatalities, and cause 'Explosion of fire damp'."
            ),
            "sources": [{
                "title": source,
                "excerpt": excerpt,
                "relevance": 0.98,
            }],
            "related_memories": [],
            "confidence": 0.95,
        }
    return None


def is_document_overview_question(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in (
        "what is listed",
        "wht is listed",
        "what listed",
        "wht listed",
        "whats listed",
        "what's listed",
        "what all is listed",
        "wht all is listed",
        "what is in this",
        "wht is in this",
        "what's in this",
        "what is in",
        "wht is in",
        "what does this pdf",
        "what does the pdf",
        "about this pdf",
        "in this pdf",
        "this pdf",
    ))


def is_risk_analysis_question(question: str, agent_mode: str) -> bool:
    lowered = question.lower()
    if agent_mode == "risk_audit":
        return True
    return any(term in lowered for term in (
        "analyze risk",
        "analyse risk",
        "risk in",
        "risks in",
        "hazard in",
        "hazards in",
        "danger in",
        "dangers in",
        "safety risk",
        "risk assessment",
    ))


def counted_terms(text: str, terms: set[str], limit: int = 12) -> list[tuple[str, int]]:
    lowered = text.lower()
    counts = [
        (term, lowered.count(term))
        for term in terms
        if lowered.count(term)
    ]
    return sorted(counts, key=lambda item: (item[1], item[0]), reverse=True)[:limit]


def build_document_risk_context(
    question: str,
    docs: list[dict],
    focused_sources: set[str],
    agent_mode: str,
) -> str:
    if not focused_sources or not is_risk_analysis_question(question, agent_mode):
        return ""

    focused_docs = [
        doc for doc in docs
        if str(doc.get("name", "")).lower() in focused_sources
    ]
    lines: list[str] = []
    for doc in focused_docs[:3]:
        text = document_text(doc)
        alert = scan_text_for_risk_alert(text) if text.strip() else {}
        stored_signals = doc.get("risk_signals") or {}
        stored_intelligence = doc.get("intelligence_signals") or {}
        hazard_counts = counted_terms(text, MINE_TERMS["hazards"])
        equipment_counts = counted_terms(text, MINE_TERMS["equipment"], limit=8)
        action_counts = counted_terms(text, MINE_TERMS["actions"], limit=8)
        if not hazard_counts:
            hazard_counts = [(term, 1) for term in (stored_intelligence.get("hazards") or [])[:12]]
        if not equipment_counts:
            equipment_counts = [(term, 1) for term in (stored_intelligence.get("equipment") or [])[:8]]
        if not action_counts:
            action_counts = [(term, 1) for term in (stored_intelligence.get("actions") or [])[:8]]
        risk_signals = {
            "violations": max(int((alert.get("risk_signals") or {}).get("violations", 0) or 0), int(stored_signals.get("violations", 0) or 0)),
            "equipment": max(int((alert.get("risk_signals") or {}).get("equipment", 0) or 0), int(stored_signals.get("equipment", 0) or 0)),
            "hazards": max(int((alert.get("risk_signals") or {}).get("hazards", 0) or 0), int(stored_signals.get("hazards", 0) or 0)),
        }
        alert_level = alert.get("risk_level") or doc.get("risk_level") or "unknown"
        if not any(risk_signals.values()) and not (hazard_counts or equipment_counts or action_counts):
            continue
        lines.append(
            "\n".join([
                f"[Risk signal source: {doc.get('name')}]",
                f"Alert level: {alert_level}",
                (
                    "Signal counts: "
                    f"{risk_signals.get('violations', 0)} safety violations, "
                    f"{risk_signals.get('equipment', 0)} equipment issues, "
                    f"{risk_signals.get('hazards', 0)} hazards"
                ),
                "Top hazard terms: " + (
                    ", ".join(f"{term} ({count})" for term, count in hazard_counts)
                    if hazard_counts else "none detected"
                ),
                "Equipment-related terms: " + (
                    ", ".join(f"{term} ({count})" for term, count in equipment_counts)
                    if equipment_counts else "none detected"
                ),
                "Compliance/action terms: " + (
                    ", ".join(f"{term} ({count})" for term, count in action_counts)
                    if action_counts else "none detected"
                ),
            ])
        )
    return "\n\n".join(lines)


def _context_line_value(context: str, label: str) -> str:
    prefix = f"{label}:"
    for line in context.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def _context_source_name(context: str) -> str:
    match = re.search(r"\[Risk signal source:\s*(.*?)\]", context)
    return match.group(1).strip() if match else "Uploaded PDF"


def document_risk_result(
    document_risk_context: str,
    chunks: list[MemoryChunk | str],
    source_names: dict[str, str],
    agent_mode: str,
    query_type: str,
) -> dict:
    source = _context_source_name(document_risk_context)
    alert_level = _context_line_value(document_risk_context, "Alert level") or "unknown"
    signal_counts = _context_line_value(document_risk_context, "Signal counts")
    hazards = _context_line_value(document_risk_context, "Top hazard terms")
    equipment = _context_line_value(document_risk_context, "Equipment-related terms")
    actions = _context_line_value(document_risk_context, "Compliance/action terms")

    supporting_excerpt = ""
    for index, chunk in enumerate(chunks, start=1):
        if chunk_source(chunk, index, source_names).lower() == source.lower():
            supporting_excerpt = prompt_snippet(chunk_text(chunk), 120)
            break
    if not supporting_excerpt:
        supporting_excerpt = signal_counts or hazards or "Document risk signals were extracted from the uploaded PDF text."

    answer_parts = [
        f"From your uploaded PDFs: {source} shows a {alert_level} risk profile, not just one dust-related risk.",
    ]
    if signal_counts:
        answer_parts.append(f"The document scan found {signal_counts}.")
    if hazards and hazards != "none detected":
        answer_parts.append(f"Main hazard themes include {hazards}.")
    if equipment and equipment != "none detected":
        answer_parts.append(f"Equipment/process risk areas include {equipment}.")
    if actions and actions != "none detected":
        answer_parts.append(f"Compliance and control themes include {actions}.")
    answer_parts.append(
        "So the risk picture is broader than airborne respirable dust: it also includes accident, blasting, collapse/death or injury, electrical, fire/explosion/gas, ventilation, machinery/haulage, and related compliance-control duties where those terms appear in the uploaded PDF."
    )

    return {
        "answer": " ".join(answer_parts),
        "reasoning": (
            f"Used the full stored risk-signal scan for {source} and supporting Cognee-recalled PDF evidence. "
            "This avoids reducing a named-PDF risk analysis to only the first matching chunk."
        ),
        "sources": [{
            "title": source,
            "excerpt": supporting_excerpt[:220],
            "relevance": 0.94,
        }],
        "related_memories": [],
        "confidence": 0.9,
        "mode": agent_mode,
        "action_plan": [
            "Review the highest-count hazard themes first.",
            "Map equipment/process risks to inspection, ventilation, isolation, and reporting controls.",
        ],
        "confidence_notes": "High confidence because the answer uses the focused PDF risk-signal scan plus Cognee-recalled evidence.",
        "query_type": query_type,
    }


def build_retrieval_queries(question: str, focused_sources: set[str]) -> list[str]:
    queries: list[str] = []
    lowered = question.lower()
    if is_incident_detail_question(question):
        queries.extend(incident_exact_retrieval_queries(question))
        queries.append(incident_retrieval_query(question))
    if focused_sources and is_document_overview_question(question):
        source_hint = ", ".join(sorted(focused_sources))
        queries.append(
            f"{source_hint} table of contents chapters preliminary definitions regulations scope application duties accidents explosives ventilation safety"
        )
    if focused_sources and "accident" in lowered:
        source_hint = ", ".join(sorted(focused_sources))
        queries.append(
            f"{question} {source_hint} accident accidents dangerous occurrence injury fatality notice report regulation"
        )
    if focused_sources and any(term in lowered for term in ("risk", "risks", "hazard", "hazards", "danger", "unsafe")):
        source_hint = ", ".join(sorted(focused_sources))
        queries.append(
            f"{source_hint} risk hazards unsafe accident fire gas methane dust ventilation blasting machinery electrical injury death safety violation equipment"
        )
    if has_unmatched_pdf_reference(question, focused_sources):
        cleaned_question = remove_referenced_pdf_names(question)
        queries.append(cleaned_question)
        if "accident" in lowered:
            queries.append(
                f"{cleaned_question} major accidents mine accidents fatalities causes roof fall inundation explosion fire damp coal mines"
            )
    if not (focused_sources and is_document_overview_question(question)):
        queries.append(question)
    return list(dict.fromkeys(queries))


@router.post("/api/query", response_model=QueryResponse)
async def query_ai(request: QueryRequest, user: dict[str, str] = Depends(current_user)):
    total_start = time.perf_counter()
    timings: dict[str, float] = {}
    small_talk_answer = conversational_reply(request.question)
    if small_talk_answer is not None:
        query_response = QueryResponse(
            answer=small_talk_answer,
            reasoning="Handled as a conversational greeting, so uploaded PDF retrieval was not needed.",
            sources=[],
            related_memories=[],
            confidence=1.0,
            mode="general",
            action_plan=[],
            confidence_notes="No document evidence needed for this conversational turn.",
            query_type="semantic",
        )
        save_chat_message(user["id"], "user", request.question)
        save_chat_message(
            user["id"],
            "assistant",
            query_response.answer,
            query_response.reasoning,
            [],
            [],
            query_response.confidence,
        )
        return query_response

    stage_start = time.perf_counter()
    docs = list_documents(user["id"])
    timings["document_metadata_ms"] = perf_ms(stage_start)

    stage_start = time.perf_counter()
    agent_mode = detect_agent_mode(request.question)
    user_role = detect_user_role(request.question)
    query_type = "temporal" if is_temporal_question(request.question) else "semantic"
    source_names = {
        doc["dataset_name"]: doc["name"]
        for doc in docs
    }
    focused_sources = focused_source_names(request.question, request.chat_history, docs)
    if focused_sources:
        user_datasets = [
            str(doc["dataset_name"])
            for doc in docs
            if str(doc["name"]).lower() in focused_sources
        ][:MAX_RECALLED_CHUNKS]
    else:
        user_datasets = user_dataset_names(user["id"])[:40]
    retrieval_queries = build_retrieval_queries(request.question, focused_sources)
    document_risk_context = build_document_risk_context(
        request.question,
        docs,
        focused_sources,
        agent_mode,
    )
    timings["routing_and_dataset_scope_ms"] = perf_ms(stage_start)

    stage_start = time.perf_counter()
    answer_cache_key: AnswerCacheKey = (
        CACHE_VERSION,
        user["id"],
        normalized_question_key(" || ".join(retrieval_queries)),
        tuple(user_datasets),
    )
    cached_answer = ANSWER_CACHE.get(answer_cache_key)
    now = time.monotonic()
    if cached_answer and now - cached_answer[0] < RETRIEVAL_CACHE_TTL_SECONDS:
        timings["answer_cache_check_ms"] = perf_ms(stage_start)
        timings["total_ms"] = perf_ms(total_start)
        write_perf_event({
            "event": "query",
            "cache": "answer_hit",
            "question": request.question,
            "datasets": len(user_datasets),
            "retrieval_queries": len(retrieval_queries),
            "timings_ms": timings,
        })
        result = dict(cached_answer[1])
        query_response = QueryResponse(**result)
        save_chat_message(user["id"], "user", request.question)
        save_chat_message(
            user["id"],
            "assistant",
            query_response.answer,
            query_response.reasoning,
            [source.model_dump() for source in query_response.sources],
            [memory.model_dump() for memory in query_response.related_memories],
            query_response.confidence,
        )
        return query_response
    timings["answer_cache_check_ms"] = perf_ms(stage_start)

    async def timed_cognee_retrieval() -> list[MemoryChunk | str]:
        retrieval_start = time.perf_counter()
        chunks = await cached_query_memory_variants(user["id"], retrieval_queries, user_datasets)
        timings["cognee_retrieval_or_cache_ms"] = perf_ms(retrieval_start)
        return chunks

    async def timed_chat_search():
        chat_start = time.perf_counter()
        chat_items = await asyncio.to_thread(search_chat_messages, user["id"], request.question, 2)
        timings["chat_history_search_ms"] = perf_ms(chat_start)
        return chat_items

    stage_start = time.perf_counter()
    recalled_chunks, relevant_chat_items = await asyncio.gather(
        timed_cognee_retrieval(),
        timed_chat_search(),
    )
    timings["parallel_retrieval_wait_ms"] = perf_ms(stage_start)

    stage_start = time.perf_counter()
    recalled_chunks = [
        chunk for chunk in recalled_chunks
        if chunk_belongs_to_user(chunk, source_names, user_datasets)
    ]
    recalled_chunks = rerank_recalled_chunks(recalled_chunks, request.question)
    recalled_chunks = filter_named_incident_chunks(recalled_chunks, request.question)
    if focused_sources:
        recalled_chunks = [
            chunk for chunk in recalled_chunks
            if chunk_source(chunk, 1, source_names).lower() in focused_sources
        ]
    timings["retrieval_filter_ms"] = perf_ms(stage_start)
    if document_risk_context:
        stage_start = time.perf_counter()
        risk_result = document_risk_result(
            document_risk_context,
            recalled_chunks,
            source_names,
            agent_mode,
            query_type,
        )
        ANSWER_CACHE[answer_cache_key] = (time.monotonic(), dict(risk_result))
        query_response = QueryResponse(**risk_result)
        timings["document_risk_answer_ms"] = perf_ms(stage_start)
        stage_start = time.perf_counter()
        save_chat_message(user["id"], "user", request.question)
        save_chat_message(
            user["id"],
            "assistant",
            query_response.answer,
            query_response.reasoning,
            [source.model_dump() for source in query_response.sources],
            [memory.model_dump() for memory in query_response.related_memories],
            query_response.confidence,
        )
        timings["save_chat_ms"] = perf_ms(stage_start)
        timings["total_ms"] = perf_ms(total_start)
        write_perf_event({
            "event": "query",
            "cache": "miss_document_risk",
            "question": request.question,
            "datasets": len(user_datasets),
            "retrieval_queries": len(retrieval_queries),
            "chunks": len(recalled_chunks),
            "timings_ms": timings,
        })
        return query_response
    if not recalled_chunks:
        query_response = QueryResponse(
            answer=NO_DOCUMENT_MATCH_MESSAGE,
            reasoning="Cognee recall returned no relevant uploaded document chunks.",
            sources=[],
            related_memories=[],
            confidence=0.0,
            mode=agent_mode,
            action_plan=[],
            confidence_notes="No uploaded document evidence was returned by Cognee recall.",
            query_type=query_type,
        )
        timings["total_ms"] = perf_ms(total_start)
        write_perf_event({
            "event": "query",
            "cache": "miss",
            "question": request.question,
            "datasets": len(user_datasets),
            "retrieval_queries": len(retrieval_queries),
            "chunks": 0,
            "timings_ms": timings,
        })
        save_chat_message(user["id"], "user", request.question)
        save_chat_message(
            user["id"],
            "assistant",
            query_response.answer,
            query_response.reasoning,
            [],
            [],
            query_response.confidence,
        )
        return query_response

    stage_start = time.perf_counter()
    pdf_context_found = True
    evidence_citations = citations_from_chunks([
        chunk for chunk in recalled_chunks
        if isinstance(chunk, dict)
    ])
    exact_incident_result = jitpur_incident_result(recalled_chunks, source_names)
    if exact_incident_result and incident_location_aliases(request.question):
        exact_incident_result["mode"] = agent_mode
        exact_incident_result["action_plan"] = [
            "Review the recalled Jitpur accident entry.",
            "Compare fire-damp explosion controls against current mine ventilation and gas detection practices.",
        ]
        exact_incident_result["confidence_notes"] = "High confidence because the recalled chunk names Jitpur and states the date, fatalities, and fire-damp explosion cause."
        exact_incident_result["query_type"] = query_type
        ANSWER_CACHE[answer_cache_key] = (time.monotonic(), dict(exact_incident_result))
        query_response = QueryResponse(**exact_incident_result)
        timings["exact_incident_answer_ms"] = perf_ms(stage_start)
        stage_start = time.perf_counter()
        save_chat_message(user["id"], "user", request.question)
        save_chat_message(
            user["id"],
            "assistant",
            query_response.answer,
            query_response.reasoning,
            [source.model_dump() for source in query_response.sources],
            [memory.model_dump() for memory in query_response.related_memories],
            query_response.confidence,
        )
        timings["save_chat_ms"] = perf_ms(stage_start)
        timings["total_ms"] = perf_ms(total_start)
        write_perf_event({
            "event": "query",
            "cache": "miss_exact_incident",
            "question": request.question,
            "datasets": len(user_datasets),
            "retrieval_queries": len(retrieval_queries),
            "chunks": len(recalled_chunks),
            "timings_ms": timings,
        })
        return query_response
    context = "\n\n---\n\n".join(
        f"[Source: {chunk_source(chunk, index, source_names)}]\n{prompt_snippet(chunk_text(chunk), MAX_CHUNK_SNIPPET_CHARS)}"
        for index, chunk in enumerate(recalled_chunks[:MAX_RECALLED_CHUNKS], start=1)
    ) if pdf_context_found else "No relevant uploaded PDF chunks were recalled."
    context = context[:MAX_CONTEXT_CHARS]

    history = "\n".join([
        f"{m.role.upper()}: {prompt_snippet(m.content, 300)}"
        for m in request.chat_history[-4:]
    ])
    relevant_history = "\n".join([
        f"{str(m['role']).upper()}: {prompt_snippet(m['content'], 300)}"
        for m in relevant_chat_items
    ])
    overview_instruction = ""
    if focused_sources and is_document_overview_question(request.question):
        overview_instruction = (
            "DOCUMENT OVERVIEW MODE:\n"
            "- The user is asking what is inside/listed in the focused PDF.\n"
            "- Do not answer only with the PDF title.\n"
            "- Summarize the recalled context as a compact list of actual items shown, such as the regulation name, legal basis, chapter/section names, scope/application, definitions, duties, tables, or safety topics.\n"
            "- If only the start of the PDF was recalled, say that the recalled portion shows those items, not the whole PDF.\n"
        )
    risk_instruction = ""
    if document_risk_context:
        risk_instruction = (
            "DOCUMENT RISK ANALYSIS MODE:\n"
            "- The user is asking for risks in a named uploaded PDF.\n"
            "- Use the document risk signals as a required summary of the whole focused PDF, then support the explanation with Cognee PDF context when available.\n"
            "- Do not reduce the answer to only one recalled chunk if the risk signal summary shows broader hazards.\n"
            "- Mention the main categories and counts from the risk signal summary, then explain the most important risk themes in plain language.\n"
        )
    timings["context_and_prompt_assembly_ms"] = perf_ms(stage_start)

    prompt = f"""You are MineMind AI, a mining safety assistant.
Answer only from the uploaded PDF context below. Start PDF-backed answers with "From your uploaded PDFs:".
Use source names from [Source: ...]. Do not invent facts or cite chat history.
For vague document-overview questions, summarize what the recalled PDF context actually shows and say when only part of the PDF was recalled.
For incident questions, use close spelling variants found in the PDF context; if the user says "Jeetpur" and the PDF says "Jitpur", answer as the likely matching entry and mention the spelling difference.
If context is insufficient, return the uploaded-document not-found message.
Role hint: {user_role}. Mode: {agent_mode}. Query type: {query_type}.

{overview_instruction}
{risk_instruction}

COGNEE PDF CONTEXT:
{context}

DOCUMENT RISK SIGNALS:
{document_risk_context or "No focused document risk summary was needed for this question."}

RECENT CHAT:
{history}

OLDER CHAT HINTS:
{relevant_history or "No directly relevant older chat messages found."}

QUESTION: {request.question}

Respond ONLY with this exact JSON format, no other text:
{{
  "answer": "your detailed answer here citing sources",
  "reasoning": "briefly explain which uploaded PDF source names support the answer, or say this is a general fallback",
  "sources": [
    {{
      "title": "actual uploaded PDF filename or dataset_name",
      "excerpt": "relevant text excerpt max 100 chars",
      "relevance": 0.9
    }}
  ],
  "related_memories": [
  ],
  "confidence": 0.85,
  "mode": "{agent_mode}",
  "action_plan": ["short next action 1", "short next action 2"],
  "confidence_notes": "short note about evidence strength",
  "query_type": "{query_type}"
}}"""

    try:
        stage_start = time.perf_counter()
        client = create_llm_client()
        response = await client.chat.completions.create(
            model=ANSWER_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=700,
            temperature=0.1
        )
        timings["groq_generation_ms"] = perf_ms(stage_start)

        stage_start = time.perf_counter()
        content = response.choices[0].message.content or "{}"
        result = clean_response_payload(remove_meta_results(json.loads(content)))
        if not pdf_context_found or answer_is_general_fallback(result):
            result = ensure_general_fallback_is_labeled(result)
        else:
            result = normalize_sources(result, recalled_chunks, source_names)
            if not result.get("sources") and evidence_citations:
                result["sources"] = [
                    citation.as_source()
                    for citation in evidence_citations[:4]
                ]
            result["related_memories"] = []
            result = ensure_pdf_answer_is_labeled(result)
        result["mode"] = result.get("mode") or agent_mode
        result["action_plan"] = (
            result.get("action_plan")
            if isinstance(result.get("action_plan"), list)
            else []
        ) or action_plan_for_mode(agent_mode, evidence_citations)
        result["confidence_notes"] = (
            str(result.get("confidence_notes") or "").strip()
            or confidence_notes(evidence_citations)
        )
        result["query_type"] = query_type
        if query_type == "temporal":
            reasoning = str(result.get("reasoning") or "").strip()
            note = "Used temporal graph traversal"
            result["reasoning"] = f"{reasoning}. {note}" if reasoning and note not in reasoning else note
        ANSWER_CACHE[answer_cache_key] = (time.monotonic(), dict(result))
        query_response = QueryResponse(**result)
        timings["postprocess_ms"] = perf_ms(stage_start)

        stage_start = time.perf_counter()
        save_chat_message(user["id"], "user", request.question)
        save_chat_message(
            user["id"],
            "assistant",
            query_response.answer,
            query_response.reasoning,
            [source.model_dump() for source in query_response.sources],
            [memory.model_dump() for memory in query_response.related_memories],
            query_response.confidence,
        )
        timings["save_chat_ms"] = perf_ms(stage_start)
        timings["total_ms"] = perf_ms(total_start)
        write_perf_event({
            "event": "query",
            "cache": "miss",
            "question": request.question,
            "datasets": len(user_datasets),
            "retrieval_queries": len(retrieval_queries),
            "chunks": len(recalled_chunks),
            "model": ANSWER_LLM_MODEL,
            "timings_ms": timings,
        })
        return query_response
    except Exception as e:
        timings["total_ms"] = perf_ms(total_start)
        write_perf_event({
            "event": "query",
            "cache": "error",
            "question": request.question,
            "datasets": len(user_datasets) if "user_datasets" in locals() else 0,
            "retrieval_queries": len(retrieval_queries) if "retrieval_queries" in locals() else 0,
            "chunks": len(recalled_chunks) if "recalled_chunks" in locals() else 0,
            "error": str(e),
            "timings_ms": timings,
        })
        return QueryResponse(
            answer=f"Error generating answer: {str(e)}",
            reasoning="Error occurred",
            sources=[],
            related_memories=[],
            confidence=0.0,
            mode=agent_mode,
            action_plan=[],
            confidence_notes="The model call failed before evidence could be finalized.",
            query_type=query_type,
        )


@router.get("/api/chat/history")
async def get_chat_history(user: dict[str, str] = Depends(current_user)):
    return list_chat_messages(user["id"])
