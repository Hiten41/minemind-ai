from datetime import datetime, timezone
import asyncio
import hashlib
import re
import sqlite3
from psycopg2.errors import UniqueViolation
from urllib.parse import quote
import mimetypes
import os
import tempfile
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, Header
from fastapi.responses import FileResponse, Response

from models.schemas import UploadResponse
from services.auth_service import (
    current_user,
    _connect,
    _document_row,
    get_document_for_user,
    document_state,
    set_document_state,
    get_document_file_for_user,
    list_documents,
    list_documents_page,
    save_document,
    update_document_type,
    update_document_ingest_status,
)
from services.cognee_service import ingest_document
from services.advanced_ai import classify_document_type, extract_document_signals, scan_text_for_risk_alert
from services.document_search import estimate_node_count, repair_document_node_counts, store_document_text
from services.parser import parse_file
from services.settings import STORAGE_ROOT

router = APIRouter()
USER_FILE_ROOT = STORAGE_ROOT / "user_files"


def repair_document_types(
    user_id: str,
    documents: list[dict] | None = None,
) -> None:
    for doc in documents if documents is not None else list_documents(user_id):
        detected_type = classify_document_type(doc)
        if detected_type != str(doc.get("type") or "").lower():
            update_document_type(user_id, str(doc["id"]), detected_type)
            doc["type"] = detected_type


def store_original_file(user_id: str, doc_id: str, filename: str, content: bytes) -> str:
    user_dir = USER_FILE_ROOT / user_id / doc_id
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = 'original' + Path(filename or 'document.txt').suffix.lower()
    file_path = user_dir / safe_filename
    file_path.write_bytes(content)
    return str(file_path)


async def index_document_in_background(user_id: str, doc_id: str, *_unused) -> None:
    from services.document_lifecycle import process_document
    await process_document(user_id, doc_id)


@router.post('/api/upload',response_model=UploadResponse)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile=File(...),
                          doc_type: str=Form(default='auto'),
                          idempotency_key: str | None=Header(default=None),
                          user: dict[str,str]=Depends(current_user)):
    if doc_type not in {'auto','regulation','manual','incident','maintenance','shift'}:
        raise HTTPException(422,'Unknown document type')
    if idempotency_key and (len(idempotency_key)>100 or not re.fullmatch(r'[A-Za-z0-9_-]+',idempotency_key)):
        raise HTTPException(422,'Invalid idempotency key')
    safe_name=re.sub(r'[\x00-\x1f\x7f]','', (file.filename or 'document.txt').replace('\\','/').split('/')[-1])[:180]
    suffix=Path(safe_name).suffix.lower()
    if suffix not in {'.pdf','.docx','.txt'}:
        raise HTTPException(415,'Supported formats are PDF, DOCX and UTF-8 TXT')
    doc_id=str(uuid.uuid4())
    tmp_path=''
    try:
        with tempfile.NamedTemporaryFile(delete=False,suffix=suffix) as temp:
            tmp_path=temp.name
            size=0
            while block:=await file.read(1024*1024):
                size+=len(block)
                if size>20*1024*1024:
                    raise HTTPException(413,'Upload exceeds the 20 MB limit')
                temp.write(block)
        content=await asyncio.to_thread(Path(tmp_path).read_bytes)
        digest=hashlib.sha256(content).hexdigest()
        if idempotency_key:
            with _connect() as conn:
                previous=conn.execute('SELECT * FROM documents WHERE user_id=%s AND request_key=%s',(user['id'],idempotency_key)).fetchone()
            if previous:
                if previous['content_hash']!=digest or previous['status'] in {'deleted','delete_pending','delete_failed'}:
                    raise HTTPException(409,'Idempotency key already used; start a new upload')
                return UploadResponse(**_document_row(previous))
        with _connect() as conn:
            usage=conn.execute("SELECT COUNT(*) AS count, COALESCE(SUM(LENGTH(file_content)),0) AS bytes FROM documents WHERE user_id=%s AND status <> 'deleted'",(user['id'],)).fetchone()
        if usage['count']>=200 or usage['bytes']+size>100*1024*1024:
            raise HTTPException(413,'Account document quota reached (200 documents / 100 MB)')
        try:
            text=await asyncio.to_thread(parse_file,tmp_path,safe_name)
        except (RuntimeError,ValueError,OSError,UnicodeError) as exc:
            raise HTTPException(400,str(exc)) from exc
        if not text.strip():
            raise HTTPException(400,'No readable text found in the document')
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        await file.close()
    detected_type=classify_document_type({'name':safe_name,'type':doc_type},text)
    dataset_name=f'user_{user["id"]}_{doc_id}'
    text_path=store_document_text(user['id'],doc_id,text)
    file_path=store_original_file(user['id'],doc_id,safe_name,content)
    signal=scan_text_for_risk_alert(text,detected_type)
    doc=dict(content_hash=digest,request_key=idempotency_key,id=doc_id,name=safe_name,type=detected_type,status='queued',node_count=estimate_node_count(text),
             uploaded_at=datetime.now(timezone.utc).isoformat(),dataset_name=dataset_name,text_path=text_path,
             extracted_text=text,file_path=file_path,file_content=content,file_mime_type=mimetypes.guess_type(safe_name)[0],
             risk_signals=signal['risk_signals'],risk_level=signal['risk_level'],intelligence_signals=extract_document_signals(text))
    try:
        save_document(user['id'],doc)
    except (sqlite3.IntegrityError, UniqueViolation):
        Path(text_path).unlink(missing_ok=True)
        Path(file_path).unlink(missing_ok=True)
        if idempotency_key:
            with _connect() as conn:
                previous = conn.execute('SELECT * FROM documents WHERE user_id=%s AND request_key=%s', (user['id'], idempotency_key)).fetchone()
            if previous and previous['content_hash'] == digest and previous['status'] not in {'deleted', 'delete_pending', 'delete_failed'}:
                return UploadResponse(**_document_row(previous))
            if previous:
                raise HTTPException(409, 'Idempotency key already used; start a new upload')
        raise
    except Exception:
        # Preserve the original database error; clean only files created by this attempt.
        Path(text_path).unlink(missing_ok=True); Path(file_path).unlink(missing_ok=True)
        raise
    background_tasks.add_task(index_document_in_background,user['id'],doc_id)
    return UploadResponse(**doc)


@router.post('/api/documents/{doc_id}/retry')
async def retry_document(doc_id: str,background_tasks: BackgroundTasks,user: dict[str,str]=Depends(current_user)):
    doc=document_state(user['id'],doc_id)
    if not doc:
        raise HTTPException(404,'Document not found')
    if doc['status']!='failed':
        raise HTTPException(409,'Only failed indexing can be retried')
    with _connect() as conn:
        changed = conn.execute("UPDATE documents SET status='queued', failure_reason=NULL, version=version+1 WHERE user_id=%s AND id=%s AND status='failed' RETURNING id", (user['id'], doc_id)).fetchone()
    if not changed:
        raise HTTPException(409, 'Document state changed; refresh before retrying')
    background_tasks.add_task(index_document_in_background,user['id'],doc_id)
    return {'status':'queued'}


@router.get("/api/documents")
async def get_documents(user: dict[str, str] = Depends(current_user)):
    documents = list_documents(user["id"])
    return documents


@router.get("/api/documents/page")
async def get_documents_page(
    limit: int = 50,
    offset: int = 0,
    doc_type: str | None = None,
    user: dict[str, str] = Depends(current_user),
):
    page = list_documents_page(user["id"], limit=limit, offset=offset, doc_type=doc_type)
    return page


@router.get("/api/documents/{doc_id}/file")
async def get_document_file(
    doc_id: str,
    user: dict[str, str] = Depends(current_user),
):
    doc = get_document_file_for_user(user["id"], doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_content = doc.get("file_content")
    if file_content:
        content = bytes(file_content)
        media_type = str(doc.get("file_mime_type") or "application/pdf")
        filename = str(doc.get("name") or "document.pdf")
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": "inline; filename*=UTF-8\'\'" + quote(filename,safe="")},
        )

    file_path = doc.get("file_path")
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail="Original file is not available for this older upload. Please re-upload it to enable file preview.",
        )

    path = Path(str(file_path)).resolve()
    allowed_root = (USER_FILE_ROOT / user["id"]).resolve()
    if allowed_root not in path.parents or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Original file is not available")

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        filename=str(doc.get("name") or path.name),
    )
