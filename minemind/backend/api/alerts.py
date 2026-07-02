from fastapi import APIRouter, Depends

from services.auth_service import current_user, list_alert_documents

router = APIRouter()


@router.get("/api/alerts")
async def get_alerts(user: dict[str, str] = Depends(current_user)):
    return [
        {
            "id": doc["id"],
            "name": doc["name"],
            "risk_level": doc["risk_level"],
            "risk_signals": doc["risk_signals"],
            "date": doc["uploaded_at"],
            "dataset_name": doc["dataset_name"],
        }
        for doc in list_alert_documents(user["id"])
    ]
