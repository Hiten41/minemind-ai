"""Durable jobs in document rows; lock ingest/delete across API workers.

SQLite uses an OS file lock, PostgreSQL a session advisory lock. Locks are
released by the OS/database on process death; processing rows are recoverable.
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import logging
import os
import errno

from services.auth_service import _connect, document_state, set_document_state
from services.settings import STORAGE_ROOT
from services.cognee_service import ingest_document, delete_dataset
from services.query_cache import answers

log=logging.getLogger(__name__)
DELETION_STATES={'delete_pending','delete_failed','deleted'}


@contextmanager
def document_lock(doc_id: str):
    key=int.from_bytes(hashlib.sha256(doc_id.encode()).digest()[:8],'big',signed=True)
    if os.getenv('DATABASE_URL','').strip():
        with _connect() as conn:
            acquired=conn.execute('SELECT pg_try_advisory_lock(%s) AS acquired',(key,)).fetchone()['acquired']
            try:
                yield acquired
            finally:
                if acquired:
                    conn.execute('SELECT pg_advisory_unlock(%s)',(key,))
    else:
        folder=STORAGE_ROOT/'locks'
        folder.mkdir(exist_ok=True,parents=True)
        with (folder/f'{key}.lock').open('a+b') as handle:
            handle.seek(0); handle.write(b'0'); handle.flush(); handle.seek(0)
            acquired=False
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                acquired=True
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                # Contention leaves the durable job pending for another pass.
            try:
                yield acquired
            finally:
                if acquired and os.name=='nt':
                    handle.seek(0); msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                elif acquired:
                    fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def owned_path(value: str, user_id: str, kind: str):
    from pathlib import Path
    path=Path(value).resolve()
    root=(STORAGE_ROOT/kind/user_id).resolve()
    if root not in path.parents:
        raise ValueError('Stored file path is outside its owner directory')
    return path


async def finish_delete(doc: dict) -> bool:
    if not await delete_dataset(doc['dataset_name']):
        set_document_state(doc['user_id'],doc['id'],'delete_failed','Memory provider deletion failed. Retry deletion.')
        return False
    try:
        for field,kind in [('file_path','user_files'),('text_path','user_text')]:
            if doc.get(field):
                owned_path(doc[field],doc['user_id'],kind).unlink(missing_ok=True)
    except (OSError,ValueError) as exc:
        log.warning('Local deletion failed for %s: %s',doc['id'],type(exc).__name__)
        set_document_state(doc['user_id'],doc['id'],'delete_failed','Local cleanup failed. Retry deletion or contact administrator.')
        return False
    with _connect() as conn:
        conn.execute("""UPDATE documents SET status='deleted', name='Deleted document', extracted_text=NULL,
            file_content=NULL, file_path=NULL, text_path=NULL, risk_signals='{}', intelligence_signals='{}',
            risk_level='none', node_count=0, failure_reason=NULL, version=version+1
            WHERE user_id=%s AND id=%s""",(doc['user_id'],doc['id']))
    answers.invalidate_user(doc['user_id'])
    return True


async def process_document(user_id: str, doc_id: str) -> None:
    with document_lock(doc_id) as acquired:
        if not acquired:
            return
        doc=document_state(user_id,doc_id)
        if not doc or doc['status']=='deleted':
            return
        if doc['status']=='delete_pending':
            await finish_delete(doc)
            return
        if doc['status'] not in {'queued','processing'}:
            return
        with _connect() as conn:
            changed=conn.execute("""UPDATE documents SET status='processing', ingest_attempts=ingest_attempts+1,
                failure_reason=NULL, version=version+1 WHERE user_id=%s AND id=%s AND status IN ('queued','processing') RETURNING id""",(user_id,doc_id)).fetchone()
        if not changed:
            return
        try:
            # Retrying uncertain/partial ingestion must first remove the old dataset.
            if doc['ingest_attempts'] and not await delete_dataset(doc['dataset_name']):
                raise RuntimeError('Unable to clean partial provider dataset before retry')
            await ingest_document(str(doc.get('extracted_text') or ''),doc['dataset_name'],doc['name'])
            with _connect() as conn:
                conn.execute("""UPDATE documents SET status='ingested', indexed_at=%s, failure_reason=NULL,version=version+1
                    WHERE user_id=%s AND id=%s AND status='processing'""",(datetime.now(timezone.utc).isoformat(),user_id,doc_id))
        except Exception as exc:
            # Job boundary records all SDK failures durably; does not report success.
            log.warning('Ingest job %s failed: %s',doc_id,type(exc).__name__)
            with _connect() as conn:
                conn.execute("""UPDATE documents SET status='failed', failure_reason=%s, version=version+1
                    WHERE user_id=%s AND id=%s AND status='processing'""",('Memory indexing failed. Local text is available; retry indexing.',user_id,doc_id))
        finally:
            answers.invalidate_user(user_id)
        latest=document_state(user_id,doc_id)
        if latest and latest['status']=='delete_pending':
            await finish_delete(latest)


async def worker_loop(stop: asyncio.Event):
    while not stop.is_set():
        try:
            with _connect() as conn:
                pending=conn.execute("SELECT id,user_id FROM documents WHERE status IN ('queued','processing','delete_pending') ORDER BY uploaded_at LIMIT 20").fetchall()
            for doc in pending:
                if stop.is_set():
                    break
                await process_document(doc['user_id'],doc['id'])
        except Exception:
            log.exception('Document worker iteration failed; durable jobs retained')
        try:
            await asyncio.wait_for(stop.wait(),timeout=3)
        except TimeoutError:
            continue
