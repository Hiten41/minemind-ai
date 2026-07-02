import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}


def _csv_env(name: str) -> list[str]:
    return [
        item.strip().rstrip("/")
        for item in os.getenv(name, "").split(",")
        if item.strip()
    ]


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set for production deployment")
    return value


STORAGE_ROOT = Path(
    os.getenv("MINEMIND_STORAGE_DIR", str(BACKEND_DIR / ".cognee"))
).expanduser()
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

AUTH_SECRET = (
    _required_env("AUTH_SECRET")
    if IS_PRODUCTION
    else os.getenv("AUTH_SECRET", "minemind-local-dev-secret")
)

FRONTEND_ORIGINS = _csv_env("FRONTEND_ORIGINS")
FRONTEND_ORIGIN_REGEX = os.getenv("FRONTEND_ORIGIN_REGEX", "").strip()
if IS_PRODUCTION and not FRONTEND_ORIGINS and not FRONTEND_ORIGIN_REGEX:
    raise RuntimeError("FRONTEND_ORIGINS or FRONTEND_ORIGIN_REGEX must be set for production deployment")

CORS_LOCALHOST_REGEX = r"http://(localhost|127\.0\.0\.1):\d+"
