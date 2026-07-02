import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from typing import Any

from fastapi import Depends, Header, HTTPException

from services.settings import AUTH_SECRET, BACKEND_DIR, STORAGE_ROOT

DB_PATH = STORAGE_ROOT / "minemind.sqlite"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30
DOCUMENT_PAGE_SIZE_MAX = 100


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_store() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                mobile TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                node_count INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL,
                dataset_name TEXT NOT NULL UNIQUE,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                reasoning TEXT,
                sources TEXT,
                related_memories TEXT,
                confidence REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_documents_user_uploaded
            ON documents(user_id, uploaded_at DESC);

            CREATE INDEX IF NOT EXISTS idx_documents_user_type_uploaded
            ON documents(user_id, type, uploaded_at DESC);

            CREATE INDEX IF NOT EXISTS idx_chat_user_created
            ON chat_messages(user_id, created_at DESC);
            """
        )
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
        if "text_path" not in columns:
            conn.execute("ALTER TABLE documents ADD COLUMN text_path TEXT")
        if "risk_signals" not in columns:
            conn.execute("ALTER TABLE documents ADD COLUMN risk_signals TEXT NOT NULL DEFAULT '{}'")
        if "risk_level" not in columns:
            conn.execute("ALTER TABLE documents ADD COLUMN risk_level TEXT NOT NULL DEFAULT 'none'")


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        150_000,
    ).hex()
    return f"{salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, _digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_hash_password(password, salt), stored)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256)
    return f"{body}.{_b64(sig.digest())}"


def verify_token(token: str) -> str:
    try:
        body, supplied_sig = token.split(".", 1)
        expected = hmac.new(
            AUTH_SECRET.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        )
        if not hmac.compare_digest(_b64(expected.digest()), supplied_sig):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return str(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc


def public_user(row: sqlite3.Row) -> dict[str, str]:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "mobile": row["mobile"],
    }


def create_user(name: str, email: str, mobile: str, password: str) -> dict[str, str]:
    email = email.strip().lower()
    mobile = mobile.strip()
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    user_id = secrets.token_hex(16)
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, name, email, mobile, password_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, name.strip() or "MineMind User", email, mobile, _hash_password(password)),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email or mobile already registered") from exc
    return public_user(row)


def authenticate_user(identifier: str, password: str) -> dict[str, str]:
    ident = identifier.strip().lower()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email) = ? OR mobile = ?",
            (ident, identifier.strip()),
        ).fetchone()
    if not row or not _verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return public_user(row)


def get_user_by_id(user_id: str) -> dict[str, str]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return public_user(row)


async def current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    return get_user_by_id(verify_token(authorization.split(" ", 1)[1]))


def save_document(user_id: str, doc: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO documents
            (id, user_id, name, type, status, node_count, uploaded_at, dataset_name, text_path, risk_signals, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc["id"],
                user_id,
                doc["name"],
                doc["type"],
                doc["status"],
                int(doc["node_count"]),
                doc["uploaded_at"],
                doc["dataset_name"],
                doc.get("text_path"),
                json.dumps(doc.get("risk_signals") or {}),
                doc.get("risk_level", "none"),
            ),
        )


def update_document_ingest_status(
    user_id: str,
    doc_id: str,
    status: str,
    node_count: int,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE documents
            SET status = ?, node_count = ?
            WHERE user_id = ? AND id = ?
            """,
            (status, int(node_count), user_id, doc_id),
        )


def list_documents(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, type, status, node_count, uploaded_at, dataset_name, text_path, risk_signals, risk_level
            FROM documents
            WHERE user_id = ?
            ORDER BY uploaded_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_document_row(row) for row in rows]


def list_documents_page(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    doc_type: str | None = None,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), DOCUMENT_PAGE_SIZE_MAX))
    safe_offset = max(0, int(offset))
    filters = ["user_id = ?"]
    params: list[Any] = [user_id]
    if doc_type:
        filters.append("type = ?")
        params.append(doc_type)
    where_clause = " AND ".join(filters)

    with _connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM documents WHERE {where_clause}",
            params,
        ).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT id, name, type, status, node_count, uploaded_at, dataset_name, text_path, risk_signals, risk_level
            FROM documents
            WHERE {where_clause}
            ORDER BY uploaded_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        ).fetchall()
    return {
        "items": [_document_row(row) for row in rows],
        "total": int(total),
        "limit": safe_limit,
        "offset": safe_offset,
        "has_more": safe_offset + safe_limit < int(total),
    }


def get_document_for_user(user_id: str, dataset_name: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE user_id = ? AND dataset_name = ?",
            (user_id, dataset_name),
        ).fetchone()
    return _document_row(row) if row else None


def _document_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["risk_signals"] = json.loads(item.get("risk_signals") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["risk_signals"] = {}
    item["risk_level"] = item.get("risk_level") or "none"
    return item


def list_alert_documents(user_id: str) -> list[dict[str, Any]]:
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    alerts = [
        doc for doc in list_documents(user_id)
        if doc.get("risk_level") != "none"
    ]
    return sorted(
        alerts,
        key=lambda doc: (
            severity_rank.get(str(doc.get("risk_level")), 0),
            str(doc.get("uploaded_at", "")),
        ),
        reverse=True,
    )


def delete_document(user_id: str, dataset_name: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM documents WHERE user_id = ? AND dataset_name = ?",
            (user_id, dataset_name),
        )


def user_dataset_names(user_id: str) -> list[str]:
    return [doc["dataset_name"] for doc in list_documents(user_id)]


def dataset_names_for_documents(user_id: str, docs: list[dict[str, Any]]) -> list[str]:
    allowed = {str(doc["dataset_name"]) for doc in docs}
    return [
        doc["dataset_name"]
        for doc in list_documents(user_id)
        if doc["dataset_name"] in allowed
    ]


def save_chat_message(
    user_id: str,
    role: str,
    content: str,
    reasoning: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    related_memories: list[dict[str, Any]] | None = None,
    confidence: float | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages
            (id, user_id, role, content, reasoning, sources, related_memories, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                secrets.token_hex(16),
                user_id,
                role,
                content,
                reasoning,
                json.dumps(sources or []),
                json.dumps(related_memories or []),
                confidence,
            ),
        )


def list_chat_messages(user_id: str, limit: int = 60) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content, reasoning, sources, related_memories, confidence
            FROM chat_messages
            WHERE user_id = ?
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    messages: list[dict[str, Any]] = []
    for row in reversed(rows):
        item = dict(row)
        item["sources"] = json.loads(item["sources"] or "[]")
        item["related_memories"] = json.loads(item["related_memories"] or "[]")
        messages.append(item)
    return messages


CHAT_STOP_WORDS = {
    "about",
    "again",
    "from",
    "have",
    "name",
    "pdf",
    "pdfs",
    "show",
    "summarise",
    "summarize",
    "that",
    "the",
    "this",
    "tools",
    "what",
    "which",
    "with",
    "your",
}


def _chat_terms(query: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) > 2 and term not in CHAT_STOP_WORDS
    ][:12]


def search_chat_messages(user_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]:
    terms = _chat_terms(query)
    if not terms:
        return []

    candidates: list[tuple[int, int, dict[str, Any]]] = []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content, reasoning, sources, related_memories, confidence, rowid
            FROM chat_messages
            WHERE user_id = ?
            ORDER BY rowid DESC
            LIMIT 300
            """,
            (user_id,),
        ).fetchall()

    for row in rows:
        content = str(row["content"] or "")
        lowered = content.lower()
        score = sum(1 for term in terms if term in lowered)
        if score <= 0:
            continue
        item = dict(row)
        item["sources"] = json.loads(item["sources"] or "[]")
        item["related_memories"] = json.loads(item["related_memories"] or "[]")
        candidates.append((score, int(row["rowid"]), item))

    return [
        item
        for _score, _rowid, item in sorted(candidates, key=lambda value: (value[0], value[1]), reverse=True)[:limit]
    ]
