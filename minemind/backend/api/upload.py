from datetime import datetime
import mimetypes
import os
import tempfile
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from models.schemas import UploadResponse
from services.auth_service import (
    current_user,
    list_documents,
    list_documents_page,
    save_document,
    update_document_ingest_status,
)
from services.cognee_service import ingest_document
from services.advanced_ai import scan_text_for_risk_alert
from services.document_search import estimate_node_count, repair_document_node_counts, store_document_text
from services.parser import parse_file
from services.settings import STORAGE_ROOT

router = APIRouter()
USER_FILE_ROOT = STORAGE_ROOT / "user_files"


def store_original_file(user_id: str, doc_id: str, filename: str, content: bytes) -> str:
    user_dir = USER_FILE_ROOT / user_id / doc_id
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(filename or "document").name or "document"
    file_path = user_dir / safe_filename
    file_path.write_bytes(content)
    return str(file_path)


async def index_document_in_background(
    user_id: str,
    doc_id: str,
    text: str,
    dataset_name: str,
    safe_name: str,
) -> None:
    try:
        node_count = await ingest_document(text, dataset_name, safe_name)
        node_count = max(int(node_count or 0), estimate_node_count(text))
        update_document_ingest_status(user_id, doc_id, "ingested", node_count)
    except Exception as exc:
        print(f"Background ingest error: {exc}")


@router.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: str = Form(default="regulation"),
    user: dict[str, str] = Depends(current_user)
):
    doc_id = str(uuid.uuid4())
    safe_name = file.filename or "document.txt"
    tmp_path = os.path.join(tempfile.gettempdir(), f"{doc_id}_{safe_name}")

    async with aiofiles.open(tmp_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    try:
        text = parse_file(tmp_path, safe_name)
    except RuntimeError as exc:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text.strip():
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(
            status_code=400,
            detail="No readable text found in this file. If it is scanned, OCR must be installed."
        )
    dataset_name = f"user_{user['id'][:8]}_{doc_type}_{doc_id[:8]}"
    text_path = store_document_text(user["id"], doc_id, text)
    file_path = store_original_file(user["id"], doc_id, safe_name, content)
    node_count = estimate_node_count(text)
    risk_alert = scan_text_for_risk_alert(text)
    status = "stored"

    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    doc = {
        "id": doc_id,
        "name": safe_name,
        "type": doc_type,
        "status": status,
        "node_count": node_count,
        "uploaded_at": datetime.now().isoformat(),
        "dataset_name": dataset_name,
        "text_path": text_path,
        "file_path": file_path,
        "risk_signals": risk_alert["risk_signals"],
        "risk_level": risk_alert["risk_level"],
    }
    save_document(user["id"], doc)
    background_tasks.add_task(
        index_document_in_background,
        user["id"],
        doc_id,
        text,
        dataset_name,
        safe_name,
    )
    return UploadResponse(**doc)


@router.get("/api/documents")
async def get_documents(user: dict[str, str] = Depends(current_user)):
    repair_document_node_counts(user["id"])
    return list_documents(user["id"])


@router.get("/api/documents/page")
async def get_documents_page(
    limit: int = 50,
    offset: int = 0,
    doc_type: str | None = None,
    user: dict[str, str] = Depends(current_user),
):
    repair_document_node_counts(user["id"])
    return list_documents_page(user["id"], limit=limit, offset=offset, doc_type=doc_type)


@router.get("/api/documents/{doc_id}/file")
async def get_document_file(
    doc_id: str,
    user: dict[str, str] = Depends(current_user),
):
    doc = next(
        (item for item in list_documents(user["id"]) if str(item["id"]) == doc_id),
        None,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = doc.get("file_path")
    if not file_path:
        raise HTTPException(
            status_code=404,
            detail="Original file is not available for this older upload. Please re-upload it to enable PDF preview.",
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
