import os
import asyncio
import json
import time
from pathlib import Path
from typing import Any

import requests
from services.settings import STORAGE_ROOT

COGNEE_ROOT = STORAGE_ROOT
COGNEE_ROOT.mkdir(exist_ok=True)
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"

os.environ.setdefault("COGNEE_LOGS_DIR", str(COGNEE_ROOT / "logs"))
os.environ.setdefault("SYSTEM_ROOT_DIRECTORY", str(COGNEE_ROOT))
os.environ.setdefault("DATA_ROOT_DIRECTORY", str(COGNEE_ROOT / "data"))
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")
os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")
if os.getenv("LLM_PROVIDER", "groq").lower() == "groq":
    groq_model = os.getenv("GROQ_MODEL") or os.getenv("LLM_MODEL", DEFAULT_GROQ_MODEL)
    if groq_model.startswith("groq/"):
        groq_model = groq_model.split("/", 1)[1]
    if groq_model == "llama3-8b-8192":
        groq_model = DEFAULT_GROQ_MODEL
    if not os.getenv("GROQ_API_KEY") and os.getenv("LLM_API_KEY"):
        os.environ["GROQ_API_KEY"] = os.environ["LLM_API_KEY"]
    os.environ["LLM_PROVIDER"] = "custom"
    os.environ["LLM_MODEL"] = f"groq/{groq_model}"
    os.environ.setdefault("LLM_ENDPOINT", "https://api.groq.com/openai/v1")
    os.environ.pop("LLM_API_KEY", None)


def _default_embedding_tokenizer() -> str:
    cached_model_dir = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--nomic-ai--nomic-embed-text-v1.5"
        / "snapshots"
    )
    if cached_model_dir.exists():
        snapshots = sorted(
            (p for p in cached_model_dir.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if snapshots:
            return str(snapshots[0])
    return "nomic-ai/nomic-embed-text-v1.5"


os.environ.setdefault("EMBEDDING_TOKENIZER", _default_embedding_tokenizer())
os.environ.setdefault("HUGGINGFACE_TOKENIZER", os.environ["EMBEDDING_TOKENIZER"])

import cognee
from cognee.api.v1.search import SearchType

MemoryChunk = dict[str, str]
PERF_DEBUG = os.getenv("MINEMIND_PERF_DEBUG", "false").lower() == "true"
PERF_LOG_PATH = Path(
    os.getenv(
        "MINEMIND_PERF_LOG",
        str(Path(__file__).resolve().parents[1] / ".cognee" / "query_timings.jsonl"),
    )
)
COGNEE_SEARCH_ONLY_CONTEXT = os.getenv("COGNEE_SEARCH_ONLY_CONTEXT", "true").lower() != "false"


def _perf_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _write_perf_event(event: dict) -> None:
    if not PERF_DEBUG:
        return
    try:
        PERF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PERF_LOG_PATH.open("a", encoding="utf-8") as perf_log:
            perf_log.write(json.dumps(event, ensure_ascii=True) + "\n")
    except Exception as exc:
        print(f"Cognee perf log failed: {exc}")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _normalize_groq_model(model: str) -> str:
    if model.startswith("groq/"):
        model = model.split("/", 1)[1]
    if model == "llama3-8b-8192":
        return DEFAULT_GROQ_MODEL
    return model


def _cloud_base_url() -> str:
    return _env("COGNEE_BASE_URL").rstrip("/")


def _cloud_api_key() -> str:
    return _env("COGNEE_API_KEY")


def using_cognee_cloud() -> bool:
    return bool(_cloud_base_url() and _cloud_api_key())


def _cloud_headers(content_type: str = "application/json") -> dict[str, str]:
    api_key = _cloud_api_key()
    headers = {"X-Api-Key": api_key}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _cloud_url(path: str) -> str:
    return f"{_cloud_base_url()}/api/v1/{path.lstrip('/')}"


def _raise_for_cloud_response(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:500]
        raise RuntimeError(f"Cognee Cloud request failed: {response.status_code} {detail}") from exc


async def _cloud_post_json(path: str, payload: dict[str, Any]) -> Any:
    def request() -> Any:
        response = requests.post(
            _cloud_url(path),
            json=payload,
            headers=_cloud_headers(),
            timeout=120,
        )
        _raise_for_cloud_response(response)
        if not response.content:
            return {}
        return response.json()

    return await asyncio.to_thread(request)


async def _cloud_post_multipart(path: str, fields: dict[str, Any]) -> Any:
    def request() -> Any:
        multipart_fields = {
            key: (None, "" if value is None else str(value))
            for key, value in fields.items()
        }
        response = requests.post(
            _cloud_url(path),
            files=multipart_fields,
            headers={
                key: value
                for key, value in _cloud_headers(content_type="").items()
            },
            timeout=300,
        )
        _raise_for_cloud_response(response)
        if not response.content:
            return {}
        return response.json()

    return await asyncio.to_thread(request)


def _text_from_cloud_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        search_results = result.get("search_result")
        if isinstance(search_results, str):
            return search_results
        if isinstance(search_results, list):
            texts = []
            for item in search_results:
                if not isinstance(item, dict):
                    continue
                value = item.get("text") or item.get("content") or item.get("context")
                if value:
                    texts.append(str(value))
            if texts:
                return "\n\n".join(texts[:6])
        for key in ("text", "content", "context", "answer", "summary"):
            value = result.get(key)
            if value:
                return str(value)
        return str(result)
    return str(result)


def _source_from_cloud_result(result: Any, index: int) -> str:
    if isinstance(result, dict):
        for key in ("source", "title", "name", "datasetName", "dataset_name", "dataset"):
            value = result.get(key)
            if value:
                return str(value)
        search_results = result.get("search_result")
        if isinstance(search_results, list):
            for item in search_results:
                if not isinstance(item, dict):
                    continue
                for key in ("document_name", "source", "title", "name", "file_name"):
                    value = item.get(key)
                    if value:
                        return str(value)
        references = result.get("references")
        if isinstance(references, list) and references:
            first = references[0]
            if isinstance(first, dict):
                for key in ("source", "title", "name", "file_name"):
                    value = first.get(key)
                    if value:
                        return str(value)
    return f"Cognee Cloud result {index}"


def _cloud_results_to_chunks(results: Any) -> list[MemoryChunk]:
    if isinstance(results, dict):
        for key in ("results", "data", "items"):
            value = results.get(key)
            if isinstance(value, list):
                results = value
                break
        else:
            results = [results]
    if not isinstance(results, list):
        results = [results]

    chunks: list[MemoryChunk] = []
    for index, result in enumerate(results, start=1):
        text = _text_from_cloud_result(result).strip()
        if not text:
            continue
        chunks.append({
            "text": text,
            "source": _source_from_cloud_result(result, index),
        })
    return chunks


async def initialize_cognee():
    """Configure Cognee to use Groq for LLM tasks and Ollama for embeddings."""
    if using_cognee_cloud():
        return

    cognee.config.system_root_directory(str(COGNEE_ROOT))
    cognee.config.data_root_directory(str(COGNEE_ROOT / "data"))

    llm_provider = _env("LLM_PROVIDER", "custom")
    llm_model = _env("GROQ_MODEL") or _env("LLM_MODEL", DEFAULT_GROQ_MODEL)
    llm_api_key = _env("GROQ_API_KEY") or _env("LLM_API_KEY")
    llm_endpoint = _env("GROQ_BASE_URL") or _env(
        "LLM_ENDPOINT",
        "https://api.groq.com/openai/v1"
    )

    if llm_provider == "groq":
        llm_model = _normalize_groq_model(llm_model)

    cognee_llm_provider = (
        "custom" if llm_provider in {"groq", "custom"} else llm_provider
    )
    cognee_llm_model = (
        f"groq/{llm_model}"
        if llm_provider == "groq" and not llm_model.startswith("groq/")
        else llm_model
    )

    cognee.config.set_llm_provider(cognee_llm_provider)
    cognee.config.set_llm_model(cognee_llm_model)
    cognee.config.set_llm_endpoint(llm_endpoint)
    if llm_api_key:
        cognee.config.set_llm_api_key(llm_api_key)
    if llm_provider == "groq":
        os.environ.pop("LLM_API_KEY", None)

    cognee.config.set_embedding_provider(_env("EMBEDDING_PROVIDER", "ollama"))
    cognee.config.set_embedding_model(_env("EMBEDDING_MODEL", "nomic-embed-text"))
    cognee.config.set_embedding_endpoint(
        _env("EMBEDDING_ENDPOINT", "http://localhost:11434/api/embed")
    )
    cognee.config.set_embedding_dimensions(_env("EMBEDDING_DIMENSIONS", "768"))
    cognee.config.set_embedding_config({
        "huggingface_tokenizer": _env(
            "EMBEDDING_TOKENIZER",
            _default_embedding_tokenizer()
        )
    })

    cognee.config.set_vector_db_provider(
        _env("VECTOR_DB_PROVIDER") or _env("COGNEE_VECTOR_DB_PROVIDER", "lancedb")
    )
    graph_provider = (
        _env("GRAPH_DATABASE_PROVIDER")
        or _env("COGNEE_GRAPH_DB_PROVIDER", "kuzu")
    )
    if graph_provider == "networkx":
        graph_provider = "kuzu"
    cognee.config.set_graph_database_provider(graph_provider)


async def ingest_document(
    text: str,
    dataset_name: str,
    doc_name: str
) -> int:
    """
    Ingest document text into Cognee memory.
    Uses correct v1.0 API: cognee.remember()
    with dataset_name parameter.
    """
    indexed_text = (
        f"Document filename: {doc_name}\n"
        f"Dataset name: {dataset_name}\n\n"
        f"{text}"
    )
    if using_cognee_cloud():
        await _cloud_post_json("add_text", {
            "textData": [indexed_text],
            "datasetName": dataset_name,
        })
        await _cloud_post_json("cognify", {
            "datasets": [dataset_name],
            "runInBackground": False,
        })
        return max(10, len(text) // 500)

    await cognee.remember(
        indexed_text,
        dataset_name=dataset_name,
        run_in_background=False
    )
    return max(10, len(text) // 500)


def _metadata_value(metadata: object, keys: list[str]) -> str:
    if isinstance(metadata, dict):
        for key in keys:
            value = metadata.get(key)
            if value:
                return str(value)
        for value in metadata.values():
            nested = _metadata_value(value, keys)
            if nested:
                return nested
    return ""


def _source_name_from_result(result: object, index: int) -> str:
    keys = [
        "filename",
        "file_name",
        "document_name",
        "doc_name",
        "source",
        "source_name",
        "title",
        "name",
        "dataset_name",
        "dataset",
    ]
    for key in keys:
        value = getattr(result, key, None)
        if value:
            return str(value)

    metadata = getattr(result, "metadata", None)
    source = _metadata_value(metadata, keys)
    if source:
        return source

    data = getattr(result, "__dict__", None)
    source = _metadata_value(data, keys)
    if source:
        return source

    text = getattr(result, "text", str(result))
    for line in str(text).splitlines()[:8]:
        lowered = line.lower()
        if lowered.startswith("document filename:"):
            return line.split(":", 1)[1].strip()
        if lowered.startswith("dataset name:"):
            return line.split(":", 1)[1].strip()

    return f"dataset_chunk_{index}"


def _chunk_text(result: object) -> str:
    if hasattr(result, "text"):
        return str(getattr(result, "text"))
    return str(result)


async def query_memory(
    question: str,
    datasets: list[str] | None = None,
    top_k: int = 4,
) -> list[MemoryChunk]:
    """
    Query Cognee memory.
    Uses correct v1.0 API: cognee.recall()
    with query_text parameter.
    Results have .text attribute.
    """
    try:
        if not datasets:
            return []
        if using_cognee_cloud():
            request_start = time.perf_counter()
            results = await _cloud_post_json("search", {
                "searchType": "CHUNKS",
                "datasets": datasets,
                "query": question,
                "topK": top_k,
                "onlyContext": COGNEE_SEARCH_ONLY_CONTEXT,
                "verbose": False,
                "includeReferences": True,
            })
            request_ms = _perf_ms(request_start)

            parse_start = time.perf_counter()
            chunks = _cloud_results_to_chunks(results)
            parse_ms = _perf_ms(parse_start)
            _write_perf_event({
                "event": "cognee_cloud_search",
                "search_type": "CHUNKS",
                "only_context": COGNEE_SEARCH_ONLY_CONTEXT,
                "datasets": len(datasets),
                "top_k": top_k,
                "chunks": len(chunks),
                "timings_ms": {
                    "cloud_request_ms": request_ms,
                    "result_parse_ms": parse_ms,
                    "total_ms": round(request_ms + parse_ms, 2),
                },
            })
            return chunks

        recall_start = time.perf_counter()
        results = await cognee.recall(
            query_text=question,
            query_type=SearchType.CHUNKS,
            datasets=datasets,
            top_k=top_k
        )
        recall_ms = _perf_ms(recall_start)
        parse_start = time.perf_counter()
        chunks: list[MemoryChunk] = []
        for index, r in enumerate(results, start=1):
            chunks.append({
                "text": _chunk_text(r),
                "source": _source_name_from_result(r, index),
            })
        _write_perf_event({
            "event": "cognee_local_recall",
            "search_type": "CHUNKS",
            "datasets": len(datasets),
            "top_k": top_k,
            "chunks": len(chunks),
            "timings_ms": {
                "recall_ms": recall_ms,
                "result_parse_ms": _perf_ms(parse_start),
            },
        })
        return chunks
    except Exception as e:
        print(f"Recall error: {e}")
        return []


async def query_memory_temporal(question: str, datasets: list) -> list:
    from cognee.api.v1.search import SearchType
    try:
        if not datasets:
            return []
        if using_cognee_cloud():
            try:
                results = await _cloud_post_json("search", {
                    "searchType": "TEMPORAL",
                    "datasets": datasets,
                    "query": question,
                    "topK": 10,
                    "onlyContext": False,
                    "verbose": False,
                    "includeReferences": True,
                    "scope": "graph",
                })
            except Exception as exc:
                print(f"Cognee Cloud temporal search failed, falling back to chunks: {exc}")
                results = await _cloud_post_json("search", {
                    "searchType": "CHUNKS",
                    "datasets": datasets,
                    "query": question,
                    "topK": 10,
                    "onlyContext": False,
                    "verbose": False,
                    "includeReferences": True,
                    "scope": "graph",
                })
            return [
                chunk["text"]
                for chunk in _cloud_results_to_chunks(results)
            ]

        results = await cognee.recall(
            query_text=question,
            query_type=SearchType.TEMPORAL,
            datasets=datasets,
            top_k=10
        )
        texts = []
        for r in results:
            if hasattr(r, "text"):
                texts.append(r.text)
            else:
                texts.append(str(r))
        return texts
    except Exception as e:
        print(f"Temporal recall error: {e}")
        return []


async def enrich_memory(datasets: list[str] | None = None) -> bool:
    """
    Enrich Cognee memory graph.
    Uses correct v1.0 API: cognee.improve()
    """
    try:
        if using_cognee_cloud():
            if datasets:
                await _cloud_post_json("cognify", {
                    "datasets": datasets,
                    "runInBackground": False,
                })
            return True

        await cognee.improve()
        return True
    except Exception as e:
        print(f"Improve error: {e}")
        return False


async def delete_dataset(dataset_name: str) -> bool:
    """
    Delete a dataset from Cognee memory.
    Uses correct v1.0 API: cognee.forget()
    with dataset parameter.
    """
    try:
        if using_cognee_cloud():
            await _cloud_post_json("forget", {
                "dataset": dataset_name,
                "everything": False,
                "memoryOnly": False,
            })
            return True

        await cognee.forget(dataset=dataset_name)
        return True
    except Exception as e:
        print(f"Forget error: {e}")
        return False


async def get_graph_data(datasets: list[str] | None = None) -> dict[str, list[dict[str, object]]]:
    """
    Get graph data for visualization.
    Uses recall to get memory and builds
    React Flow compatible nodes and edges.
    """
    try:
        if not datasets:
            return {"nodes": [], "edges": []}
        if using_cognee_cloud():
            results = await _cloud_post_json("search", {
                "searchType": "GRAPH_COMPLETION",
                "datasets": datasets,
                "query": "mining operations safety equipment",
                "topK": 20,
                "onlyContext": False,
                "verbose": False,
                "includeReferences": True,
                "scope": "graph",
            })
            chunks = _cloud_results_to_chunks(results)
            nodes: list[dict[str, object]] = []
            edges: list[dict[str, object]] = []
            for index, chunk in enumerate(chunks[:20]):
                text = chunk["text"]
                text_lower = text.lower()
                node_type = "regulation"
                if "incident" in text_lower:
                    node_type = "incident"
                elif "equipment" in text_lower:
                    node_type = "equipment"
                elif "maintenance" in text_lower:
                    node_type = "maintenance"
                elif "inspection" in text_lower:
                    node_type = "inspection"
                nodes.append({
                    "id": f"cloud_node_{index}",
                    "label": text[:50],
                    "type": node_type,
                    "data": {"full_text": text},
                })
                if index > 0:
                    edges.append({
                        "id": f"cloud_edge_{index}",
                        "source": f"cloud_node_{index - 1}",
                        "target": f"cloud_node_{index}",
                        "label": "related_to",
                    })
            return {"nodes": nodes, "edges": edges}

        results = await cognee.recall(
            query_text="mining operations safety equipment",
            datasets=datasets
        )
        nodes: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        for i, r in enumerate(results[:20]):
            text = r.text if hasattr(r, "text") else str(r)
            node_type = "regulation"
            text_lower = text.lower()
            if "incident" in text_lower:
                node_type = "incident"
            elif "equipment" in text_lower:
                node_type = "equipment"
            elif "maintenance" in text_lower:
                node_type = "maintenance"
            elif "inspection" in text_lower:
                node_type = "inspection"
            nodes.append({
                "id": f"node_{i}",
                "label": text[:50],
                "type": node_type,
                "data": {"full_text": text}
            })
            if i > 0:
                edges.append({
                    "id": f"edge_{i}",
                    "source": f"node_{i-1}",
                    "target": f"node_{i}",
                    "label": "related_to"
                })
        return {"nodes": nodes, "edges": edges}
    except Exception:
        return {"nodes": [], "edges": []}
