from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import alerts, analytics, auth, forget, graph, improve, intelligence, query, upload
from services.auth_service import init_auth_store
from services.cognee_service import initialize_cognee
from services.settings import CORS_LOCALHOST_REGEX, FRONTEND_ORIGINS, FRONTEND_ORIGIN_REGEX, IS_PRODUCTION

APP_VERSION = "equipment-context-v8"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_auth_store()
    await initialize_cognee()
    yield


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
elif FRONTEND_ORIGIN_REGEX:
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
