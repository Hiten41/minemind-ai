"""Measure lexical, dense, and hybrid graph-aware retrieval over a labelled corpus.

The benchmark deliberately measures retrieval and source selection only. It does not
score generated answers, so source-citation precision is not LLM answer accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "corpus"
RAW_DIR = CORPUS_DIR / "raw"
SOURCES_PATH = CORPUS_DIR / "sources.json"
QUESTIONS_PATH = CORPUS_DIR / "questions.json"
RESULTS_DIR = ROOT / "results"
CACHE_DIR = ROOT / "cache"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "this", "to", "what", "which", "with"}


@dataclass(frozen=True)
class SourceDocument:
    id: str
    title: str
    url: str
    landing_page: str
    filename: str
    text: str


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    title: str
    text: str


def tokenize(value: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall(value.lower()) if len(token) > 1 and token not in STOP_WORDS]


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_pdf_text(path: Path) -> str:
    with pymupdf.open(path) as pdf:
        return "\n".join(page.get_text("text") for page in pdf)


def load_documents() -> list[SourceDocument]:
    payload = load_json(SOURCES_PATH)
    documents: list[SourceDocument] = []
    missing: list[str] = []
    for source in payload["sources"]:
        path = RAW_DIR / source["filename"]
        if not path.exists():
            missing.append(path.name)
            continue
        text = extract_pdf_text(path).strip()
        if len(text) < 300:
            raise RuntimeError(f"{path.name} has too little extractable text for evaluation")
        documents.append(SourceDocument(text=text, **source))
    if missing:
        raise RuntimeError("Missing benchmark PDFs: " + ", ".join(missing) + ". Run `python evaluation/download_corpus.py` first.")
    return documents


def chunks_for(documents: Iterable[SourceDocument], size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        words = document.text.split()
        step = max(1, size - overlap)
        for start in range(0, len(words), step):
            section = " ".join(words[start:start + size]).strip()
            if len(section) < 80:
                continue
            chunks.append(Chunk(id=f"{document.id}:{start}", document_id=document.id, title=document.title, text=section))
            if start + size >= len(words):
                break
    return chunks


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.tokenized = [tokenize(chunk.text) for chunk in chunks]
        self.doc_lengths = [len(tokens) for tokens in self.tokenized]
        self.average_length = sum(self.doc_lengths) / max(1, len(self.doc_lengths))
        self.frequencies = [Counter(tokens) for tokens in self.tokenized]
        document_frequency: Counter[str] = Counter()
        for tokens in self.tokenized:
            document_frequency.update(set(tokens))
        self.idf = {term: math.log(1 + (len(chunks) - count + 0.5) / (count + 0.5)) for term, count in document_frequency.items()}

    def scores(self, query: str) -> list[float]:
        values: list[float] = []
        for length, frequencies in zip(self.doc_lengths, self.frequencies):
            score = 0.0
            for term in tokenize(query):
                frequency = frequencies.get(term, 0)
                if frequency:
                    denominator = frequency + self.k1 * (1 - self.b + self.b * length / max(1, self.average_length))
                    score += self.idf.get(term, 0.0) * frequency * (self.k1 + 1) / denominator
            values.append(score)
        return values


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str, timeout_seconds: int):
        self.url = base_url.rstrip("/") + "/api/embed"
        self.model, self.timeout_seconds = model, timeout_seconds

    def embed(self, texts: list[str]) -> list[list[float]]:
        request = Request(self.url, data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except URLError as error:
            raise RuntimeError(f"Could not reach Ollama at {self.url}. Start Ollama and pull {self.model}.") from error
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("Ollama returned an unexpected embedding payload")
        return embeddings


def cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


class DenseRetriever:
    def __init__(self, chunks: list[Chunk], embedder: OllamaEmbedder, cache_path: Path, batch_size: int = 64):
        self.chunks, self.embedder, self.embeddings = chunks, embedder, []
        corpus_fingerprint = hashlib.sha256(
            "\n".join(f"{chunk.id}\t{chunk.text}" for chunk in chunks).encode("utf-8")
        ).hexdigest()
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if cached.get("model") == embedder.model and cached.get("fingerprint") == corpus_fingerprint:
                    vectors = cached.get("embeddings")
                    if isinstance(vectors, list) and len(vectors) == len(chunks):
                        self.embeddings = vectors
                        print(f"Loaded {len(chunks)} cached document embeddings.")
                        self.query_cache: dict[str, list[float]] = {}
                        return
            except (OSError, json.JSONDecodeError):
                pass
        for start in range(0, len(chunks), batch_size):
            self.embeddings.extend(embedder.embed([chunk.text for chunk in chunks[start:start + batch_size]]))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"model": embedder.model, "fingerprint": corpus_fingerprint, "embeddings": self.embeddings}), encoding="utf-8")
        self.query_cache: dict[str, list[float]] = {}

    def scores(self, query: str) -> list[float]:
        query_embedding = self.query_cache.get(query)
        if query_embedding is None:
            query_embedding = self.embedder.embed([query])[0]
            self.query_cache[query] = query_embedding
        return [cosine(query_embedding, embedding) for embedding in self.embeddings]


class EntityGraph:
    """A transparent chunk-entity graph used only by the offline hybrid baseline."""
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        occurrences: defaultdict[str, set[int]] = defaultdict(set)
        for index, chunk in enumerate(chunks):
            for token in set(tokenize(chunk.text)):
                occurrences[token].add(index)
        self.entities = {token: indexes for token, indexes in occurrences.items() if len(token) >= 4 and 1 < len(indexes) <= max(30, len(chunks) // 4)}

    def scores(self, query: str) -> list[float]:
        values = [0.0] * len(self.chunks)
        for entity in set(tokenize(query)).intersection(self.entities):
            rarity = 1 / math.sqrt(len(self.entities[entity]))
            for index in self.entities[entity]:
                values[index] += rarity
        return values


def ranks(scores: list[float]) -> list[int]:
    return sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)


def reciprocal_rank_fusion(rankings: list[list[int]], count: int, constant: int = 60) -> list[float]:
    values = [0.0] * count
    for ranking in rankings:
        for rank, index in enumerate(ranking, start=1):
            values[index] += 1 / (constant + rank)
    return values


def deduplicate_documents(ranking: list[int], chunks: list[Chunk], top_k: int) -> list[str]:
    selected: list[str] = []
    for index in ranking:
        document_id = chunks[index].document_id
        if document_id not in selected:
            selected.append(document_id)
        if len(selected) >= top_k:
            break
    return selected


def query_metrics(selected: list[str], relevant: set[str], cutoff: int) -> dict[str, float]:
    first_rank = next((rank for rank, doc_id in enumerate(selected, start=1) if doc_id in relevant), None)
    hits = sum(doc_id in relevant for doc_id in selected[:cutoff])
    return {f"recall@{cutoff}": 1.0 if hits else 0.0, f"source_precision@{cutoff}": hits / cutoff, "mrr": 1 / first_rank if first_rank else 0.0}


def mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 4) if values else 0.0


def evaluate_method(name: str, chunks: list[Chunk], questions: list[dict[str, object]], bm25: BM25Retriever, dense: DenseRetriever | None, graph: EntityGraph, cutoff: int) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for item in questions:
        question = str(item["question"])
        start = time.perf_counter()
        bm25_scores = bm25.scores(question)
        if name == "bm25":
            combined = bm25_scores
        elif name == "dense":
            if dense is None:
                raise RuntimeError("Dense retrieval was requested but Ollama embeddings are unavailable")
            combined = dense.scores(question)
        elif name == "hybrid_graph":
            if dense is None:
                raise RuntimeError("Hybrid graph retrieval requires Ollama embeddings")
            combined = reciprocal_rank_fusion([ranks(bm25_scores), ranks(dense.scores(question)), ranks(graph.scores(question))], len(chunks))
        else:
            raise ValueError(f"Unknown retrieval method: {name}")
        selected = deduplicate_documents(ranks(combined), chunks, cutoff)
        metrics = query_metrics(selected, set(item["relevant_documents"]), cutoff)
        rows.append({"id": item["id"], "question": question, "expected_documents": item["relevant_documents"], "selected_documents": selected, "latency_ms": round((time.perf_counter() - start) * 1_000, 2), **metrics})
    return {"method": name, "summary": {f"recall@{cutoff}": mean([row[f"recall@{cutoff}"] for row in rows]), f"source_precision@{cutoff}": mean([row[f"source_precision@{cutoff}"] for row in rows]), "mrr": mean([row["mrr"] for row in rows]), "mean_latency_ms": round(mean([row["latency_ms"] for row in rows]), 2)}, "queries": rows}


def markdown_report(result: dict[str, object]) -> str:
    configuration = result["configuration"]
    cutoff = configuration["cutoff"]
    lines = ["# MineMind Retrieval Benchmark", "", "This report measures retrieval and source selection, not LLM answer correctness.", "", "## Configuration", "", f"- Corpus: `{configuration['dataset_name']}` ({configuration['document_count']} documents, {configuration['chunk_count']} chunks)", f"- Chunking: {configuration['chunk_size']} words with {configuration['chunk_overlap']} words overlap", f"- Top-k source documents: {cutoff}", f"- Dense model: `{configuration['embedding_model']}`", f"- Created: {configuration['created_at']}", "", "## Aggregate results", "", "| Method | Recall@k | Source precision@k | MRR | Mean retrieval latency (ms) |", "| --- | ---: | ---: | ---: | ---: |"]
    for method in result["methods"]:
        summary = method["summary"]
        lines.append(f"| {method['method']} | {summary[f'recall@{cutoff}']:.3f} | {summary[f'source_precision@{cutoff}']:.3f} | {summary['mrr']:.3f} | {summary['mean_latency_ms']:.2f} |")
    lines.extend(["", "## Interpretation", "", "- `source_precision@k` is the fraction of selected source documents that match the manually labelled source for each question. It is a retrieval citation metric, not answer accuracy.", "- `hybrid_graph` uses reciprocal-rank fusion of BM25, Ollama dense vectors, and a transparent token-entity graph over chunks. It is an offline baseline and does not claim to reproduce Cognee Cloud internals.", "- Extend `corpus/questions.json` with double-checked labels before reporting results outside the project README.", "", "## Source provenance", "", "All PDFs are downloaded from DGMS landing pages recorded in `evaluation/corpus/sources.json`; raw PDFs and result files are excluded from git."])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methods", default="bm25,dense,hybrid_graph")
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--chunk-size", type=int, default=400)
    parser.add_argument("--chunk-overlap", type=int, default=80)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-model", default="nomic-embed-text")
    parser.add_argument("--ollama-timeout", type=int, default=120)
    args = parser.parse_args()
    if args.top_k < 1:
        raise ValueError("--top-k must be at least 1")
    documents = load_documents()
    chunks = chunks_for(documents, args.chunk_size, args.chunk_overlap)
    questions = load_json(QUESTIONS_PATH)
    if not isinstance(questions, list) or not questions:
        raise RuntimeError("questions.json must contain at least one labelled query")
    names = [name.strip() for name in args.methods.split(",") if name.strip()]
    invalid = sorted(set(names) - {"bm25", "dense", "hybrid_graph"})
    if invalid:
        raise ValueError(f"Unknown methods: {', '.join(invalid)}")
    bm25, graph = BM25Retriever(chunks), EntityGraph(chunks)
    dense = None
    if any(name in {"dense", "hybrid_graph"} for name in names):
        print(f"Embedding {len(chunks)} chunks with {args.embedding_model} via Ollama...")
        cache_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", args.embedding_model) + ".json"
        dense = DenseRetriever(chunks, OllamaEmbedder(args.ollama_base_url, args.embedding_model, args.ollama_timeout), CACHE_DIR / cache_name)
    source_payload = load_json(SOURCES_PATH)
    output = {"configuration": {"dataset_name": source_payload["dataset_name"], "document_count": len(documents), "chunk_count": len(chunks), "chunk_size": args.chunk_size, "chunk_overlap": args.chunk_overlap, "cutoff": args.top_k, "embedding_model": args.embedding_model, "created_at": datetime.now(UTC).isoformat()}, "methods": [evaluate_method(name, chunks, questions, bm25, dense, graph, args.top_k) for name in names]}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path, markdown_path = RESULTS_DIR / f"retrieval-benchmark-{stamp}.json", RESULTS_DIR / f"retrieval-benchmark-{stamp}.md"
    json_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(output), encoding="utf-8")
    print(f"Wrote {json_path.relative_to(ROOT.parent)}")
    print(f"Wrote {markdown_path.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
