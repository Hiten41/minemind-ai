import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from dotenv import load_dotenv

from models.schemas import QueryRequest, QueryResponse
from services.advanced_ai import (
    action_plan_for_mode,
    citations_from_chunks,
    confidence_notes,
    detect_agent_mode,
    detect_user_role,
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
RetrievalCacheKey = tuple[str, str, tuple[str, ...]]
RETRIEVAL_CACHE: dict[RetrievalCacheKey, tuple[float, list[MemoryChunk | str]]] = {}
AnswerCacheKey = tuple[str, str, tuple[str, ...]]
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


def prompt_snippet(value: object, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
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
        return str(chunk.get("text", ""))
    return str(chunk)


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
    cache_key: RetrievalCacheKey = (user_id, normalized_question, tuple(datasets))
    cached = RETRIEVAL_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < RETRIEVAL_CACHE_TTL_SECONDS:
        return cache_safe_chunks(cached[1])

    chunks = await query_memory(question, datasets)
    chunks = cache_safe_chunks(chunks[:MAX_RECALLED_CHUNKS])
    RETRIEVAL_CACHE[cache_key] = (now, chunks)
    return cache_safe_chunks(chunks)


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


def focused_source_names(question: str, history: list, docs: list[dict]) -> set[str]:
    recent_text = " ".join(
        [question] + [str(item.content) for item in history[-4:]]
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
    timings["routing_and_dataset_scope_ms"] = perf_ms(stage_start)

    stage_start = time.perf_counter()
    answer_cache_key: AnswerCacheKey = (
        user["id"],
        normalized_question_key(request.question),
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
        chunks = await cached_query_memory(user["id"], request.question, user_datasets)
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
    if focused_sources:
        recalled_chunks = [
            chunk for chunk in recalled_chunks
            if chunk_source(chunk, 1, source_names).lower() in focused_sources
        ]
    timings["retrieval_filter_ms"] = perf_ms(stage_start)
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
    timings["context_and_prompt_assembly_ms"] = perf_ms(stage_start)

    prompt = f"""You are MineMind AI, a mining safety assistant.
Answer only from the uploaded PDF context below. Start PDF-backed answers with "From your uploaded PDFs:".
Use source names from [Source: ...]. Do not invent facts or cite chat history.
If context is insufficient, return the uploaded-document not-found message.
Role hint: {user_role}. Mode: {agent_mode}. Query type: {query_type}.

COGNEE PDF CONTEXT:
{context}

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
        result = remove_meta_results(json.loads(content))
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
