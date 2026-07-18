import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from services.auth_service import current_user, delete_document, get_document_for_user
from services.cognee_service import delete_dataset

router = APIRouter()


@router.delete("/api/forget/{dataset_name}")
async def forget_dataset(dataset_name: str, user: dict[str, str] = Depends(current_user)):
    doc = get_document_for_user(user["id"], dataset_name)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    success = await delete_dataset(dataset_name)
    file_path = doc.get("file_path")
    if file_path:
        try:
            path = Path(str(file_path))
            shutil.rmtree(path.parent, ignore_errors=True)
        except OSError:
            pass
    delete_document(user["id"], dataset_name)
    return {
        "status": "success" if success else "failed"
    }
