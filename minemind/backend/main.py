from contextlib import asynccontextmanager
import asyncio
import os
import sqlite3
import psycopg2

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import alerts, analytics, auth, forget, graph, improve, intelligence, query, upload
from services.auth_service import init_auth_store, _connect
from services.document_lifecycle import worker_loop
from services.settings import CORS_LOCALHOST_REGEX, FRONTEND_ORIGINS, FRONTEND_ORIGIN_REGEX, IS_PRODUCTION

APP_VERSION = "grounded-followups-v12"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(init_auth_store)
    stop = asyncio.Event()
    worker = None
    if os.getenv("MINEMIND_DISABLE_WORKER", "false").lower() != "true":
        worker = asyncio.create_task(worker_loop(stop))
    try:
        yield
    finally:
        stop.set()
        if worker:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass  # Durable processing rows are recovered on the next startup.


app = FastAPI(
    title="MineMind AI",
    lifespan=lifespan
)

cors_options = {
    "allow_origins": FRONTEND_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["*"],
}
if not IS_PRODUCTION and not FRONTEND_ORIGINS:
    cors_options["allow_origin_regex"] = CORS_LOCALHOST_REGEX
elif not IS_PRODUCTION and FRONTEND_ORIGIN_REGEX:
    cors_options["allow_origin_regex"] = FRONTEND_ORIGIN_REGEX

app.add_middleware(CORSMiddleware, **cors_options)

app.include_router(upload.router)
app.include_router(alerts.router)
app.include_router(auth.router)
app.include_router(query.router)
app.include_router(improve.router)
app.include_router(intelligence.router)
app.include_router(forget.router)
app.include_router(graph.router)
app.include_router(analytics.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "MineMind AI", "version": APP_VERSION}


@app.get("/ready")
async def readiness():
    from fastapi.responses import JSONResponse
    def database_available():
        with _connect() as conn:
            conn.execute("SELECT 1").fetchone()
    try:
        await asyncio.wait_for(asyncio.to_thread(database_available), timeout=5)
    except (TimeoutError, OSError, RuntimeError, sqlite3.Error, psycopg2.Error):
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unavailable"})
    return {"status": "ready", "database": "available",
            "providers": "Not probed by readiness; per-query retrieval_diagnostics reports availability.",
            "worker": "disabled" if os.getenv("MINEMIND_DISABLE_WORKER", "false").lower() == "true" else "enabled"}
