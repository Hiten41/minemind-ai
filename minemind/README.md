# MineMind AI

MineMind AI is a full-stack mining operations assistant. Engineers upload mining documents, ask grounded questions, and inspect recalled memory, source citations, analytics, and a knowledge graph.

## Backend

```powershell
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Health check:

```powershell
curl http://localhost:8001/health
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.
If port `3000` is already busy, Next.js will use the next open port. This local checkout is currently using:

```text
http://localhost:3001
```

## Environment

Backend settings live in `backend/.env`. MineMind uses Groq for LLM responses and Ollama only for embeddings:

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your_groq_key_here

EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_ENDPOINT=http://localhost:11434/api/embed
EMBEDDING_DIMENSIONS=768
COGNEE_GRAPH_DB_PROVIDER=kuzu
```

Pull the embedding model once with `ollama pull nomic-embed-text`.

## OCR for scanned PDFs

MineMind reads selectable PDF text directly. If a PDF has little/no text, the backend falls back to OCR.

Install the Python OCR wrapper with backend requirements:

```powershell
pip install -r requirements.txt
```

Install the native Tesseract OCR engine for Windows, then either add `tesseract.exe` to `PATH` or set this in `backend/.env`:

```dotenv
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Without the native Tesseract engine, scanned PDFs will return a clear upload error instead of being silently remembered as empty text.

## Deployment

See `DEPLOYMENT.md` for production environment variables, persistent storage requirements, and frontend/backend start commands. Use `backend/.env.example` and `frontend/.env.example` as templates.
