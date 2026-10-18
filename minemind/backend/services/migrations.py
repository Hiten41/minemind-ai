"""Additive, idempotent SQLite/PostgreSQL migration 20261007.

Run by init_auth_store before serving. No original rows are deleted. A backup is
recommended before production rollout; see MIGRATIONS.md.
"""


def add_columns(conn, table, columns):
    if conn.is_sqlite:
        existing = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    else:
        for name, definition in columns.items():
            conn.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {definition}')


def migrate(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)')
    # PostgreSQL serializes startup migrations across multiple API workers.
    if not conn.is_sqlite:
        conn.execute('SELECT pg_advisory_xact_lock(20261007)')
    if conn.execute('SELECT version FROM schema_migrations WHERE version=%s',('20261007',)).fetchone():
        return
    add_columns(conn,'documents',{
        'failure_reason':'TEXT', 'content_hash':"TEXT NOT NULL DEFAULT ''",
        'indexed_at':'TEXT', 'ingest_attempts':'INTEGER NOT NULL DEFAULT 0',
        'request_key':'TEXT', 'version':'INTEGER NOT NULL DEFAULT 1',
    })
    add_columns(conn,'users',{'chat_sequence':'BIGINT NOT NULL DEFAULT 0'})
    add_columns(conn,'chat_messages',{'sequence':'BIGINT NOT NULL DEFAULT 0','payload':"TEXT NOT NULL DEFAULT '{}'"})
    # Historical equal-timestamp ordering was not recorded. Preserve all rows,
    # give ties a stable ID order and document that original order is unknowable.
    users = conn.execute('SELECT id FROM users').fetchall()
    for user in users:
        rows = conn.execute('SELECT id FROM chat_messages WHERE user_id=%s ORDER BY created_at, id',(user['id'],)).fetchall()
        for index,row in enumerate(rows,1):
            conn.execute('UPDATE chat_messages SET sequence=%s WHERE id=%s',(index,row['id']))
        conn.execute('UPDATE users SET chat_sequence=%s WHERE id=%s',(len(rows),user['id']))
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_sequence ON chat_messages(user_id, sequence)')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_document_request ON documents(user_id, request_key)')
    conn.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires BIGINT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))')
    conn.execute("UPDATE documents SET status='queued' WHERE status='stored'")
    conn.execute('INSERT INTO schema_migrations(version) VALUES (%s)',('20261007',))
