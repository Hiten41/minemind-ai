# MineMind retrieval evaluation

This is a reproducible, labelled retrieval evaluation for MineMind's document-memory stack. It compares BM25 lexical retrieval, dense `nomic-embed-text` retrieval served by Ollama, and reciprocal-rank fusion of BM25, dense vectors, and a transparent chunk-entity graph. The default uses 400-word chunks with an 80-word overlap to keep the full public corpus practical on a laptop; use the CLI flags to study a smaller chunk size.

It reports Recall@k, MRR, mean retrieval latency, and **source-citation precision@k**. Source-citation precision only tests whether the selected document matches a manually labelled source; it must never be represented as LLM answer accuracy.

## Corpus and provenance

`corpus/sources.json` records five public documents published by the Directorate General of Mines Safety (DGMS), Government of India. The downloader fetches them directly from DGMS and leaves the PDFs in `corpus/raw/`, which is ignored by git. Check the host's terms and applicable use restrictions before redistribution.

`corpus/questions.json` is a small initial labelled set. Expand it with independently checked questions and source labels before making comparative claims in a report, paper, or interview.

## Run locally

From `minemind/`:

```powershell
python -m pip install -r evaluation/requirements.txt
python evaluation/download_corpus.py
ollama pull nomic-embed-text
python evaluation/run_benchmark.py --methods bm25,dense,hybrid_graph
```

The default evaluates the top selected source document, which makes source-citation precision directly interpretable. Pass `--top-k 3` when you want to evaluate a broader retrieved context. The first dense run caches local document embeddings in `evaluation/cache/`; later runs reuse them when the corpus, chunk settings, and embedding model match. Both the cache and the timestamped JSON/Markdown reports in `evaluation/results/` are ignored by git. For the no-model baseline:

```powershell
python evaluation/run_benchmark.py --methods bm25
```

## Run with Docker

From the repository root:

```powershell
docker compose -f minemind/evaluation/docker-compose.evaluation.yml run --rm evaluation python evaluation/download_corpus.py
docker compose -f minemind/evaluation/docker-compose.evaluation.yml up -d ollama
docker compose -f minemind/evaluation/docker-compose.evaluation.yml exec ollama ollama pull nomic-embed-text
docker compose -f minemind/evaluation/docker-compose.evaluation.yml run --rm evaluation
```

The raw corpus and result folders remain local and are not committed.

## Method note

This does **not** benchmark Cognee Cloud directly. Cognee is MineMind's production memory layer; this harness is a transparent, local baseline that makes retrieval trade-offs and source-selection quality inspectable without sending the public corpus to another provider. A future Cognee adapter should use the same questions and report separately labelled results, provider/model versions, and API latency.
