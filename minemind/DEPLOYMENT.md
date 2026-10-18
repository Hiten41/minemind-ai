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
- Ephemeral working storage at `/tmp/minemind`; uploaded-document records and content are stored in PostgreSQL
- CORS regex for Vercel preview/production domains

You still need to add these secret values in Render:

```dotenv
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
GROQ_API_KEY=replace-with-your-groq-key
COGNEE_BASE_URL=https://your-cognee-tenant.aws.cognee.ai
COGNEE_API_KEY=replace-with-your-cognee-cloud-key
```

Set these environment variables on the backend host:

```dotenv
APP_ENV=production
FRONTEND_ORIGINS=https://your-frontend-domain.com
AUTH_SECRET=replace-with-a-long-random-secret
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
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

On the included Render free plan, `/tmp/minemind` is ephemeral. PostgreSQL stores user accounts, chats, document metadata, extracted text, and original uploaded file content, so these remain available after a redeploy. Cognee Cloud stores the long-term memory graph when configured.

If you deploy with local embedded Cognee instead of Cognee Cloud, use a paid host plan with a persistent disk and set `MINEMIND_STORAGE_DIR` to that mount. Render free services may cold-start after inactivity; use a paid plan if low first-request latency is required.

## Cognee Memory

For a CV/LinkedIn demo, the recommended setup is Cognee Cloud:

```dotenv
COGNEE_BASE_URL=https://your-cognee-tenant.aws.cognee.ai
COGNEE_API_KEY=your-cognee-api-key
```

When both variables are present, MineMind uses Cognee Cloud for document ingestion, recall, graph data, improve, and forget operations. This avoids relying on a laptop-local `.cognee` directory after deployment.

If you leave `COGNEE_BASE_URL` or `COGNEE_API_KEY` empty, MineMind falls back to embedded local Cognee on the backend host.

Query retrieval combines local lexical candidates with authorized semantic candidates. Provider outages are reported explicitly; dedicated temporal filtering is not implemented.

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

Production CORS requires exact owned `FRONTEND_ORIGINS`; origin regexes are ignored in production. Read `backend/MIGRATIONS.md` before rollout.
