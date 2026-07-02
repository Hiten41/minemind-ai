# MineMind Deployment Checklist

MineMind is ready to deploy as two services: a Next.js frontend and a FastAPI backend.

## Recommended Hosting

- Backend: Render Blueprint using the root `render.yaml`.
- Frontend: Vercel project with root directory `minemind/frontend`.

Deploy the backend first so you can copy its public URL into the Vercel frontend environment.

## Frontend

Set this environment variable on the frontend host:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.com
```

Build command:

```bash
npm ci
npm run build
```

Start command:

```bash
npm run start
```

## Backend

If using Render Blueprint, create a new Blueprint from this GitHub repo. The root `render.yaml` already sets:

- Backend root directory: `minemind/backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Persistent disk at `/data/minemind`
- CORS regex for Vercel preview/production domains

You still need to add these secret values in Render:

```dotenv
GROQ_API_KEY=replace-with-your-groq-key
COGNEE_BASE_URL=https://your-cognee-tenant.aws.cognee.ai
COGNEE_API_KEY=replace-with-your-cognee-cloud-key
```

Set these environment variables on the backend host:

```dotenv
APP_ENV=production
FRONTEND_ORIGINS=https://your-frontend-domain.com
AUTH_SECRET=replace-with-a-long-random-secret
MINEMIND_STORAGE_DIR=/data/minemind

LLM_PROVIDER=groq
LLM_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=replace-with-your-groq-key

COGNEE_BASE_URL=https://your-cognee-tenant.aws.cognee.ai
COGNEE_API_KEY=replace-with-your-cognee-cloud-key

# Local embedded Cognee fallback only. These are ignored when Cognee Cloud is set.
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_ENDPOINT=http://your-ollama-host:11434/api/embed
EMBEDDING_DIMENSIONS=768

COGNEE_VECTOR_DB_PROVIDER=lancedb
COGNEE_GRAPH_DB_PROVIDER=kuzu
COGNEE_SKIP_CONNECTION_TEST=true
```

Install/start commands:

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port $PORT
```

If your host does not set `PORT`, use a fixed port such as `8001`.

## Persistent Storage

`MINEMIND_STORAGE_DIR` must point to persistent disk storage. MineMind stores:

- SQLite auth/session/document records
- extracted uploaded document text
- local Cognee graph/vector data, only if `COGNEE_BASE_URL` is not set

Without persistent storage, user accounts and uploaded document metadata can disappear after redeploys. If Cognee Cloud is enabled, the long-term memory graph is stored in Cognee Cloud, but MineMind still needs persistent backend storage for users, chats, document records, risk alerts, and extracted text fallback search.

## Cognee Memory

For a CV/LinkedIn demo, the recommended setup is Cognee Cloud:

```dotenv
COGNEE_BASE_URL=https://your-cognee-tenant.aws.cognee.ai
COGNEE_API_KEY=your-cognee-api-key
```

When both variables are present, MineMind uses Cognee Cloud for document ingestion, recall, temporal recall, graph data, improve, and forget operations. This avoids relying on a laptop-local `.cognee` directory after deployment.

If you leave `COGNEE_BASE_URL` or `COGNEE_API_KEY` empty, MineMind falls back to embedded local Cognee on the backend host.

Note: Cognee Cloud accepted normal chunk recall in verification. If the Cloud temporal endpoint returns a provider-side error, MineMind automatically falls back to Cloud chunk recall for that temporal question so users still get memory-backed answers instead of empty context.

## Local Cognee Embeddings

The local fallback uses Ollama embeddings. That means `EMBEDDING_ENDPOINT` must point to a reachable Ollama service with:

```bash
ollama pull nomic-embed-text
```

If you deploy with Cognee Cloud, these local embedding variables are not used by MineMind's Cognee memory path.

## Security Notes

- Rotate any API keys used during local testing before public deployment.
- Keep `backend/.env` and `frontend/.env.local` out of git.
- Use HTTPS domains in both `NEXT_PUBLIC_API_BASE_URL` and `FRONTEND_ORIGINS`.

## Generate Provider Env Values

After you know your deployed frontend URL, backend URL, Groq key, and embedding endpoint, run:

```powershell
.\scripts\make-deploy-env.ps1 `
  -FrontendUrl "https://your-frontend-domain.com" `
  -BackendUrl "https://your-backend-domain.com" `
  -GroqApiKey "your-new-groq-key" `
  -CogneeBaseUrl "https://your-cognee-tenant.aws.cognee.ai" `
  -CogneeApiKey "your-new-cognee-key" `
  -StorageDir "/data/minemind" `
  -EmbeddingEndpoint "http://your-ollama-host:11434/api/embed"
```

This creates ignored files under `deploy-env/` with the exact variables to paste into your hosting dashboards. It also generates a strong `AUTH_SECRET` automatically.
