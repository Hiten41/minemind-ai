from datetime import datetime
import os
import tempfile
import uuid

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

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

router = APIRouter()


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
