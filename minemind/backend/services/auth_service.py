import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Depends, Header, HTTPException
import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor

from services.settings import AUTH_SECRET, IS_PRODUCTION, STORAGE_ROOT

TOKEN_TTL_SECONDS = 60 * 60 * 12
DOCUMENT_PAGE_SIZE_MAX = 100
LOCAL_DATABASE_PATH = Path(
    os.getenv("MINEMIND_SQLITE_PATH", str(STORAGE_ROOT / "minemind-local.db"))
).expanduser()


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required for MineMind auth storage. "
            "Create a Neon Postgres database, copy its connection string, "
            "and set DATABASE_URL in the backend environment."
        )
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    return urlunsplit(parsed._replace(query=urlencode(query)))


class PostgresConnection:
    is_sqlite = False

    def __init__(self):
        self.conn = psycopg2.connect(_database_url(), cursor_factory=RealDictCursor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def execute(self, query: str, params: tuple | list | None = None):
        cur = self.conn.cursor()
        cur.execute(query, params or ())
        return cur


class SQLiteCursor:
    """Return dictionary rows so local SQLite matches the PostgreSQL service API."""

    def __init__(self, cursor: sqlite3.Cursor):
        self.cursor = cursor

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def fetchone(self) -> dict[str, Any] | None:
        return self._row(self.cursor.fetchone())

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.cursor.fetchall()]


class SQLiteConnection:
    """Development-only persistent store used when DATABASE_URL is not configured."""

    is_sqlite = True

    def __init__(self):
        LOCAL_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(LOCAL_DATABASE_PATH, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def execute(self, query: str, params: tuple | list | None = None) -> SQLiteCursor:
        # The service queries use psycopg parameter placeholders. SQLite uses ?.
        sqlite_query = query.replace("%s", "?").replace("BYTEA", "BLOB")
        cursor = self.conn.cursor()
        cursor.execute(sqlite_query, params or ())
        return SQLiteCursor(cursor)


def _connect() -> PostgresConnection | SQLiteConnection:
    if os.getenv("DATABASE_URL", "").strip():
        return PostgresConnection()
    if IS_PRODUCTION:
        # Keep the deployed service fail-closed: local SQLite is only for development.
        _database_url()
    return SQLiteConnection()


def init_auth_store() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                mobile TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                node_count INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL,
                dataset_name TEXT NOT NULL UNIQUE,
                text_path TEXT,
                extracted_text TEXT,
                file_path TEXT,
                risk_signals TEXT NOT NULL DEFAULT '{}',
                risk_level TEXT NOT NULL DEFAULT 'none',
                intelligence_signals TEXT NOT NULL DEFAULT '{}',
                file_content BYTEA,
                file_mime_type TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                reasoning TEXT,
                sources TEXT,
                related_memories TEXT,
                confidence DOUBLE PRECISION,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_documents_user_uploaded
            ON documents(user_id, uploaded_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_documents_user_type_uploaded
            ON documents(user_id, type, uploaded_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_user_created
            ON chat_messages(user_id, created_at DESC)
            """
        )
        document_columns = {
            "text_path": "TEXT",
            "extracted_text": "TEXT",
            "file_path": "TEXT",
            "risk_signals": "TEXT NOT NULL DEFAULT '{}'",
            "risk_level": "TEXT NOT NULL DEFAULT 'none'",
            "intelligence_signals": "TEXT NOT NULL DEFAULT '{}'",
            "file_content": "BLOB" if conn.is_sqlite else "BYTEA",
            "file_mime_type": "TEXT",
        }
        if conn.is_sqlite:
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(documents)").fetchall()
            }
            for column, definition in document_columns.items():
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {definition}")
        else:
            for column, definition in document_columns.items():
                conn.execute(
                    f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {column} {definition}"
                )

    from services.migrations import migrate
    with _connect() as conn:
        migrate(conn)


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
        "sid": secrets.token_hex(16),
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256)
    token = f"{body}.{_b64(sig.digest())}"
    with _connect() as conn:
        conn.execute('DELETE FROM sessions WHERE expires < %s',(int(time.time()),))
        conn.execute('INSERT INTO sessions(token_hash,user_id,expires) VALUES (%s,%s,%s)',(hashlib.sha256(token.encode()).hexdigest(),user_id,payload['exp']))
    return token


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
        with _connect() as conn:
            session = conn.execute('SELECT user_id FROM sessions WHERE token_hash=%s AND expires >= %s',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        if not session or session['user_id'] != payload['sub']:
            raise ValueError('revoked session')
        return str(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc


def public_user(row: dict[str, Any]) -> dict[str, str]:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "mobile": row["mobile"],
    }


def create_user(name: str, email: str, mobile: str, password: str) -> dict[str, str]:
    email = email.strip().lower()
    mobile = mobile.strip()
    from models.schemas import RegisterRequest
    from pydantic import ValidationError
    try:
        validated = RegisterRequest(name=name,email=email,mobile=mobile,password=password)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail='Invalid registration fields; use a valid email, phone and password of at least 6 characters') from exc
    name, email, mobile = validated.name, validated.email, validated.mobile
    user_id = secrets.token_hex(16)
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users (id, name, email, mobile, password_hash)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, name.strip() or "MineMind User", email, mobile, _hash_password(password)),
            )
            row = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    except (errors.UniqueViolation, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=409, detail="Email or mobile already registered") from exc
    return public_user(row)


def authenticate_user(identifier: str, password: str) -> dict[str, str]:
    ident = identifier.strip().lower()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email) = %s OR mobile = %s",
            (ident, identifier.strip()),
        ).fetchone()
    if not row or not _verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return public_user(row)


def get_user_by_id(user_id: str) -> dict[str, str]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return public_user(row)


def current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    return get_user_by_id(verify_token(authorization.split(" ", 1)[1]))


def save_document(user_id: str, doc: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            """
                INSERT INTO documents
                (id, user_id, name, type, status, node_count, uploaded_at, dataset_name, text_path, extracted_text, file_path, risk_signals, risk_level, intelligence_signals, file_content, file_mime_type, content_hash, request_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                doc.get("extracted_text"),
                doc.get("file_path"),
                json.dumps(doc.get("risk_signals") or {}),
                doc.get("risk_level", "none"),
                json.dumps(doc.get("intelligence_signals") or {}),
                doc["file_content"] if doc.get("file_content") else None,
                doc.get("file_mime_type"),
                doc.get("content_hash", ""),
                doc.get("request_key"),
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
            SET status = %s, node_count = %s
            WHERE user_id = %s AND id = %s
            """,
            (status, int(node_count), user_id, doc_id),
        )


def update_document_type(user_id: str, doc_id: str, doc_type: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE documents
            SET type = %s
            WHERE user_id = %s AND id = %s
            """,
            (doc_type, user_id, doc_id),
        )


def _recover_extracted_text(name: str, content: bytes) -> str:
    from services.parser import parse_file

    suffix = Path(name or "document.txt").suffix or ".txt"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        return parse_file(temp_path, name)
    except (OSError, RuntimeError):
        return ""
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def list_documents(
    user_id: str,
    include_text: bool = False,
) -> list[dict[str, Any]]:
    text_columns = """
        , extracted_text
        , CASE WHEN extracted_text IS NULL THEN file_content ELSE NULL END AS recovery_file_content
        , file_mime_type
    """ if include_text else ""
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, name, type, status, node_count, uploaded_at, dataset_name, text_path, file_path, risk_signals, risk_level, intelligence_signals, failure_reason, content_hash, version, indexed_at
            {text_columns}
            FROM documents
            WHERE user_id = %s AND status <> 'deleted'
            ORDER BY uploaded_at DESC
            """,
            (user_id,),
        ).fetchall()
        if include_text:
            for row in rows:
                if row.get("extracted_text") or not row.get("recovery_file_content"):
                    continue
                recovered_text = _recover_extracted_text(
                    str(row.get("name") or "document.txt"),
                    bytes(row["recovery_file_content"]),
                )
                if not recovered_text:
                    continue
                conn.execute(
                    "UPDATE documents SET extracted_text = %s WHERE user_id = %s AND id = %s",
                    (recovered_text, user_id, row["id"]),
                )
                row["extracted_text"] = recovered_text
    return [_document_row(row) for row in rows]


def list_documents_page(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    doc_type: str | None = None,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), DOCUMENT_PAGE_SIZE_MAX))
    safe_offset = max(0, int(offset))
    filters = ["user_id = %s", "status <> 'deleted'"]
    params: list[Any] = [user_id]
    if doc_type:
        filters.append("type = %s")
        params.append(doc_type)
    where_clause = " AND ".join(filters)

    with _connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM documents WHERE {where_clause}",
            params,
        ).fetchone()["count"]
        rows = conn.execute(
            f"""
            SELECT id, name, type, status, node_count, uploaded_at, dataset_name, text_path, file_path, risk_signals, risk_level, intelligence_signals, failure_reason, content_hash, version, indexed_at
            FROM documents
            WHERE {where_clause}
            ORDER BY uploaded_at DESC
            LIMIT %s OFFSET %s
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
            "SELECT * FROM documents WHERE user_id = %s AND dataset_name = %s",
            (user_id, dataset_name),
        ).fetchone()
    return _document_row(row) if row else None


def get_document_file_for_user(user_id: str, doc_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, file_path, file_content, file_mime_type
            FROM documents
            WHERE user_id = %s AND id = %s AND status NOT IN ('deleted','delete_pending','delete_failed')
            """,
            (user_id, doc_id),
        ).fetchone()
    return dict(row) if row else None


def _document_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("file_content", None)
    item.pop("recovery_file_content", None)
    try:
        item["risk_signals"] = json.loads(item.get("risk_signals") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["risk_signals"] = {}
    try:
        item["intelligence_signals"] = json.loads(item.get("intelligence_signals") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["intelligence_signals"] = {}
    item["risk_level"] = item.get("risk_level") or "none"
    return item


def list_alert_documents(user_id: str) -> list[dict[str, Any]]:
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    alerts = [
        doc for doc in active_documents(user_id, include_text=False)
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
            "DELETE FROM documents WHERE user_id = %s AND dataset_name = %s",
            (user_id, dataset_name),
        )


def user_dataset_names(user_id: str) -> list[str]:
    return [doc["dataset_name"] for doc in active_documents(user_id, include_text=False)]


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
        sequence = conn.execute('UPDATE users SET chat_sequence=chat_sequence+1 WHERE id=%s RETURNING chat_sequence',(user_id,)).fetchone()['chat_sequence']
        conn.execute(
            """
            INSERT INTO chat_messages
            (id, user_id, role, content, reasoning, sources, related_memories, confidence, sequence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                secrets.token_hex(16),
                user_id,
                role,
                content,
                reasoning,
                json.dumps([
                    s.dict() if hasattr(s, "dict") else s
                    for s in (sources or [])
                ]),
                json.dumps([
                    m.dict() if hasattr(m, "dict") else m
                    for m in (related_memories or [])
                ]),
                confidence,
                sequence,
            ),
        )


def list_chat_messages(user_id: str, limit: int = 60) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content, reasoning, sources, related_memories, confidence, payload
            FROM chat_messages
            WHERE user_id = %s
            ORDER BY sequence DESC
            LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
    active_ids = {d["id"] for d in list_documents(user_id) if d["status"] not in {"delete_pending","delete_failed","deleted"}}
    messages: list[dict[str, Any]] = []
    for row in reversed(rows):
        item = dict(row)
        item["sources"] = json.loads(item["sources"] or "[]")
        item["related_memories"] = json.loads(item["related_memories"] or "[]")
        payload = json.loads(item.pop('payload', '{}') or '{}')
        item.update(payload)
        item['confidence'] = None  # legacy numbers were never calibrated
        for source in item.get('sources') or []:
            document_id = source.get('document_id')
            source['available'] = bool(document_id and document_id in active_ids)
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


def revoke_token(token: str) -> None:
    with _connect() as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))


def save_chat_turn(user_id: str, question: str, response: dict) -> None:
    """Allocate adjacent sequence numbers and commit both messages together."""
    with _connect() as conn:
        last = conn.execute('UPDATE users SET chat_sequence=chat_sequence+2 WHERE id=%s RETURNING chat_sequence',(user_id,)).fetchone()['chat_sequence']
        for sequence, role, content, payload in [
            (last-1,'user',question,{}), (last,'assistant',response['answer'],response),
        ]:
            conn.execute('''INSERT INTO chat_messages
                (id,user_id,role,content,reasoning,sources,related_memories,confidence,sequence,payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (secrets.token_hex(16),user_id,role,content,payload.get('reasoning'),json.dumps(payload.get('sources',[])),
                 '[]',None,sequence,json.dumps(payload)))


def document_state(user_id: str, doc_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute('SELECT * FROM documents WHERE user_id=%s AND id=%s',(user_id,doc_id)).fetchone()
    return dict(row) if row else None


def set_document_state(user_id: str, doc_id: str, status: str, failure_reason: str | None = None) -> None:
    with _connect() as conn:
        conn.execute('UPDATE documents SET status=%s, failure_reason=%s, version=version+1 WHERE user_id=%s AND id=%s',
                     (status,failure_reason,user_id,doc_id))


def active_documents(user_id: str, include_text: bool = True) -> list[dict]:
    return [d for d in list_documents(user_id,include_text=include_text)
            if d['status'] not in {'delete_pending','delete_failed','deleted'}]


def search_chat_messages(user_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]:
    terms = _chat_terms(query)
    if not terms:
        return []

    candidates: list[tuple[int, int, dict[str, Any]]] = []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content, reasoning, sources, related_memories, confidence, created_at
            FROM chat_messages
            WHERE user_id = %s
            ORDER BY sequence DESC
            LIMIT 300
            """,
            (user_id,),
        ).fetchall()

    for order_index, row in enumerate(rows):
        content = str(row["content"] or "")
        lowered = content.lower()
        score = sum(1 for term in terms if term in lowered)
        if score <= 0:
            continue
        item = dict(row)
        item["sources"] = json.loads(item["sources"] or "[]")
        item["related_memories"] = json.loads(item["related_memories"] or "[]")
        candidates.append((score, -order_index, item))

    return [
        item
        for _score, _recency, item in sorted(candidates, key=lambda value: (value[0], value[1]), reverse=True)[:limit]
    ]
