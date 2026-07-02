# MineMind AI

> The operating brain for a mine. An AI-powered mining operations assistant that permanently remembers uploaded documents and answers safety questions with evidence.

Built for the WeMakeDevs x Cognee Hackathon 2026 by Hiten Arora.

[![GitHub](https://img.shields.io/badge/GitHub-minemind--ai-black?logo=github)](https://github.com/Hiten41/minemind-ai)

---

## The Problem

Mining engineers and safety officers work with a flood of documentation: DGMS regulations, equipment manuals, incident reports, inspection notes, and maintenance logs. When they need a safety answer, they usually search through PDFs manually or rely on someone else's memory.

A normal AI chatbot is not enough for this workflow. It forgets context when the session ends. A simple RAG system can retrieve chunks, but it usually misses the deeper connections between incidents, regulations, equipment, and time.

MineMind AI is built for that gap. It ingests a mine's document history and gives it persistent memory, so engineers can ask operational and safety questions across uploaded documents with source-backed answers.

---

## Demo

Upload a DGMS regulation PDF and an incident report. Ask:

> Which regulations were violated in the June incident?

MineMind reasons across the uploaded documents, returns a grounded answer with cited sources, confidence score, and reasoning, then preserves that memory for future sessions.

Live demo: coming soon.

---

## Features

### Core Memory

- Permanent document memory across sessions.
- Cognee-powered graph and vector retrieval.
- Cognee Cloud support for deployed memory.
- Local Cognee fallback for development.
- Per-user dataset isolation.
- Memory enrichment through Cognee processing.
- Surgical document deletion with memory cleanup.

### Document Intelligence

- Upload PDF, DOCX, and TXT files.
- OCR fallback for scanned or image-only PDFs with Tesseract.
- Automatic mining-domain signal extraction.
- Hazard, equipment, regulation, and action term detection.
- Dynamic chat suggestions generated from uploaded documents.
- Node count tracking per document.

### Grounded AI Chat

- Answers grounded in uploaded documents.
- Source citations with real filenames.
- Reasoning toggle for each answer.
- Confidence score on responses.
- Temporal query detection with a visual badge.
- Temporal memory search where available, with Cloud fallback to chunk search.
- Small-talk handling so greetings do not trigger PDF fallback.
- Chat history persisted per user.

### Real-Time Risk Alerts

- Automatic risk scanning after uploads.
- Detects safety violations, equipment failures, and hazard keywords.
- Risk levels: high, medium, low, none.
- Dashboard alert cards with document-specific risk counts.
- "Ask MineMind about this" action from each alert.
- Proactive risk surfacing before the user asks a question.

### Agent Modes

- Incident analysis.
- Compliance check.
- Risk audit.
- Equipment troubleshooting.
- Document summary.
- Safety training.

### Analytics And Operations Views

- Real document counts.
- Real memory node counts.
- Monthly incident trends from uploaded data.
- Document type distribution.
- Incidents page with case details.
- Equipment page derived from memory graph or document intelligence.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, React, TypeScript, Tailwind CSS, Lucide React |
| Backend | Python, FastAPI, Uvicorn |
| Memory Layer | Cognee SDK locally, Cognee Cloud for deployment |
| LLM | Groq API, llama-3.1-8b-instant |
| Local Embeddings | Ollama, nomic-embed-text |
| Local Vector Store | LanceDB |
| Local Graph Store | Kuzu |
| Document Parsing | PyMuPDF, python-docx |
| OCR | Tesseract, pytesseract |
| Auth | Bearer-token authentication |
| Metadata Storage | SQLite and local filesystem |

---

## How Cognee Powers MineMind

MineMind supports both local Cognee and Cognee Cloud.

In local development, the backend can use Cognee's SDK lifecycle:

```python
# Ingest document memory
await cognee.remember(document_text, dataset_name=dataset_name)

# Recall memory
results = await cognee.recall(query_text=question, datasets=user_datasets)

# Enrich memory
await cognee.improve()

# Forget a deleted document
await cognee.forget(dataset=dataset_name)
```

For deployed demos, MineMind uses Cognee Cloud through API calls. Text is added to a dataset, cognified into memory, searched for grounded answers, and deleted when a document is forgotten.

Temporal questions are detected automatically:

```python
temporal_keywords = ["before", "after", "between", "since", "timeline"]
```

When a question looks time-aware, MineMind routes it to temporal memory search where available. If Cognee Cloud returns a provider-side temporal error, MineMind falls back to Cloud chunk search so users still receive memory-backed answers.

The key idea is that the mine's documents are no longer treated as isolated PDFs. Regulations, incidents, equipment, and corrective actions become part of a persistent memory layer that the assistant can retrieve from across sessions.

---

## Setup And Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- Ollama, for local embedded Cognee mode
- Tesseract OCR, for scanned PDFs
- Groq API key
- Optional: Cognee Cloud tenant and API key

### 1. Clone The Repository

```bash
git clone https://github.com/Hiten41/minemind-ai
cd minemind-ai/minemind
```

### 2. Backend Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8001
```

Health check:

```bash
curl http://localhost:8001/health
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

### 4. Pull Ollama Model For Local Mode

```bash
ollama pull nomic-embed-text
```

### 5. Environment Variables

Backend settings live in `backend/.env`:

```dotenv
APP_ENV=development
AUTH_SECRET=replace-with-a-long-random-secret

LLM_PROVIDER=groq
LLM_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your_groq_key

# Optional: Cognee Cloud for deployment
COGNEE_BASE_URL=https://your-cognee-tenant.aws.cognee.ai
COGNEE_API_KEY=your_cognee_api_key

# Local Cognee fallback
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_ENDPOINT=http://localhost:11434/api/embed
EMBEDDING_DIMENSIONS=768
COGNEE_VECTOR_DB_PROVIDER=lancedb
COGNEE_GRAPH_DB_PROVIDER=kuzu

# OCR on Windows
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Frontend settings live in `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
```

---

## Demo Flow

1. Register an account at `http://localhost:3000/login`.
2. Go to Files and upload a DGMS safety regulation PDF.
3. Upload an equipment maintenance report or incident report.
4. Go to Ask and type: `What are the ventilation requirements for underground mines?`
5. Review the grounded answer, cited sources, and confidence score.
6. Toggle Show Reasoning to inspect how the answer was formed.
7. Ask: `What happened before the last recorded incident?`
8. Confirm the temporal query badge appears.
9. Go to Dashboard and review automatic risk alerts.
10. Click Optimize Memory to enrich the memory graph.
11. Delete a document and confirm MineMind removes that document's memory.

---

## Project Structure

```text
minemind/
  frontend/          Next.js 14 app
    app/             Pages: dashboard, chat, documents, analytics, incidents, equipment
    components/      UI components
    lib/             API client
  backend/           FastAPI server
    api/             Routes: upload, query, alerts, analytics, auth, intelligence
    services/        Cognee, AI, parser, search, auth, and settings services
    models/          Pydantic schemas
  scripts/           Deployment environment helper
  DEPLOYMENT.md      Deployment guide
```

---

## What Makes MineMind Different

| Feature | Standard RAG Chatbot | MineMind AI |
|---|---|---|
| Memory | Often session-bound | Persistent document memory |
| Search | Chunk similarity | Graph and vector memory retrieval |
| Time queries | Usually unsupported | Temporal query routing |
| Risk awareness | Reactive only | Proactive risk alerts |
| Sources | Often generic chunks | Real uploaded filenames |
| Domain | Generic | Mining operations and safety |

---

## Deployment

The repository includes deployment configuration:

- `render.yaml` for the FastAPI backend on Render.
- `frontend/vercel.json` for the Next.js frontend on Vercel.
- `DEPLOYMENT.md` with environment variables and provider setup steps.

For production, keep secrets in hosting provider environment variables only. Do not commit `.env`, `.env.local`, `.cognee`, `deploy-env`, `.next`, or `node_modules`.

---

## Built By

Hiten Arora  
3rd Year B.Tech, Mining Machinery Engineering  
IIT (ISM) Dhanbad

Applying AI to mining safety, operations, and industrial decision support.

---

## Hackathon

Built for the WeMakeDevs x Cognee Hackathon, June 29 to July 5, 2026.

Theme: Give your AI a memory. Build AI that does not wake up with amnesia.
