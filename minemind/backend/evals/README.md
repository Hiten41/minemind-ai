# Public mining PDF conversations

`mining_corpus.json` records source download URLs, independently checked pages,
37 conversational questions, expected facts, and facts the documents do not support.
The corpus covers an accident investigation, an industry audit, an energy-isolation
guideline, an equipment checklist, a ventilation technical guide, and a coal-mining
regulation. Five PDFs are official publications; the regulation is an explicitly
attributed IELRC reproduction. These documents
are evaluation evidence, not advice about current mining requirements.

Download the PDFs under the filenames in the manifest into a separate corpus directory.
The runner never changes the application's database, user uploads, or Cognee datasets.
It uses the real parser, retrieval, HTTP query handler, and (with `--live`) configured
answer provider. Semantic retrieval is disabled in this isolated evaluation because
these test documents are not indexed in the user's memory service.

```powershell
$env:MINEMIND_CORPUS_DIR='C:\path\to\corpus'
python -m pytest -q
python evals/run_mining_corpus.py --corpus $env:MINEMIND_CORPUS_DIR --output retrieval.json
python evals/run_mining_corpus.py --corpus $env:MINEMIND_CORPUS_DIR --output live.json --live
```

Live mode reads the backend `.env` and uses provider quota. The default 60-second
interval reduces rate-limit interference. `--only` accepts comma-separated chain IDs
such as `nsw-ventilation-technical-guide.pdf:0` or `cross:1`.

Review answer correctness, relevance, conditions, exceptions, population/metric,
table-row mapping, and every citation against the original page. Successful retrieval,
HTTP 200, or exact offsets alone do not constitute a passing answer. Provider failures
must be recorded separately. The expected facts are not fed to the answer model.

An optional `derived-scan-haulage-page-2.pdf` fixture can be made by rasterizing page 2
of the checklist at 220 dpi into an image-only PDF. It is a derived OCR test, not an
independently sourced scan. The OCR test skips if that fixture is absent.

Table extraction affects newly parsed PDFs. Existing stored extraction is preserved;
re-upload a document to rebuild its text with table rows. No silent rewrite of user
documents or stored citation offsets is performed.

## Current verification limits

The regression suite currently passes 159 tests with this corpus and the derived
OCR fixture enabled. The 37-question corpus exercises successive chapter/section
navigation, copied references, short explanations, incident causes, procedures,
table roles, metric/population comparisons, conflicting values, and unsupported
questions. Expected answers are never supplied to the answer provider.

Live replays found and drove fixes for document/section pairing, navigation across
numbering gaps, lost follow-up subjects, table-row extraction, citation validation,
and recommendations being strengthened into obligations. These checks do not
establish full semantic correctness: a model can still omit a condition or attach
a related but insufficient citation. The final live replays encountered provider
token quota limits, including during the single correction attempt. Record those
as provider failures, not as absent evidence or passing answers. A complete fresh
live run and source review are still needed once quota is available.

`ANSWER_REPAIR_LLM_MODEL` optionally selects a model for the one bounded correction
attempt; by default it is the same as `ANSWER_LLM_MODEL`. Both must be available
through the configured provider. Changing it does not add another verification
stage or permit facts outside the retrieved passages.

Set `ANSWER_MAX_TOKENS` to fit the provider account's output allowance. The local
Qwen evaluation uses 1000; the generic default remains 3000 for providers/models
with larger allowances or reasoning-token overhead. A quota retry waits at most
15 seconds once, within the request deadline; longer or unspecified quota blocks
return the service-limit response without a retry loop.
