from datetime import datetime

from fastapi import APIRouter, Depends

from models.schemas import AnalyticsData
from services.auth_service import current_user, list_documents
from services.advanced_ai import build_document_intelligence, risk_signals
from services.document_search import repair_document_node_counts

router = APIRouter()


@router.get("/api/analytics",
            response_model=AnalyticsData)
async def get_analytics(user: dict[str, str] = Depends(current_user)):
    repair_document_node_counts(user["id"])
    uploaded_documents = list_documents(user["id"])
    intelligence = build_document_intelligence(user["id"])
    type_counts: dict[str, int] = {}
    month_counts: dict[str, int] = {}
    memory_nodes = 0
    for doc in uploaded_documents:
        t = str(doc["type"])
        type_counts[t] = type_counts.get(t, 0) + 1
        memory_nodes += int(doc.get("node_count") or 0)
        try:
            month = datetime.fromisoformat(str(doc.get("uploaded_at", ""))).strftime("%b %Y")
        except ValueError:
            month = "Unknown"
        month_counts[month] = month_counts.get(month, 0) + 1

    return AnalyticsData(
        total_documents=len(uploaded_documents),
        total_queries=0,
        incidents_count=type_counts.get("incident", 0),
        equipment_count=type_counts.get("manual", 0),
        memory_nodes=memory_nodes,
        recent_activity=[],
        incidents_per_month=[
            {"month": month, "count": count}
            for month, count in month_counts.items()
        ],
        document_types=[
            {"name": k, "value": v}
            for k, v in type_counts.items()
        ],
        risk_signals=risk_signals(user["id"]),
        top_entities=intelligence["top_entities"],
    )
