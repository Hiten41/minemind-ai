from datetime import datetime

from fastapi import APIRouter, Depends

from models.schemas import AnalyticsData
from services.auth_service import current_user, active_documents as list_documents, _connect
from services.advanced_ai import build_document_intelligence, classify_document_type, document_text, risk_signals
from services.document_search import estimate_node_count

router = APIRouter()


def derived_document_type(doc: dict) -> str:
    return classify_document_type(doc)


def has_equipment_signals(doc: dict, intelligence_doc: dict | None) -> bool:
    signals = (intelligence_doc or {}).get("signals") or {}
    if signals.get("equipment"):
        return True
    text = document_text(doc).lower()
    return any(term in text for term in ("machinery", "equipment", "fan", "ventilator", "pump", "winder", "conveyor"))


@router.get("/api/analytics",
            response_model=AnalyticsData)
async def get_analytics(user: dict[str, str] = Depends(current_user)):
    uploaded_documents = list_documents(user["id"], include_text=True)
    intelligence = build_document_intelligence(user["id"], uploaded_documents)
    intelligence_by_id = {
        str(item.get("id")): item
        for item in intelligence.get("documents", [])
        if isinstance(item, dict)
    }
    type_counts: dict[str, int] = {}
    month_counts: dict[str, int] = {}
    incident_month_counts: dict[str, int] = {}
    memory_nodes = 0
    incidents_count = 0
    equipment_count = 0
    for doc in uploaded_documents:
        t = derived_document_type(doc)
        type_counts[t] = type_counts.get(t, 0) + 1
        memory_nodes += estimate_node_count(document_text(doc))
        try:
            month = datetime.fromisoformat(str(doc.get("uploaded_at", ""))).strftime("%b %Y")
        except ValueError:
            month = "Unknown"
        month_counts[month] = month_counts.get(month, 0) + 1
        if t == "incident":
            incidents_count += 1
            incident_month_counts[month] = incident_month_counts.get(month, 0) + 1
        if has_equipment_signals(doc, intelligence_by_id.get(str(doc.get("id")))):
            equipment_count += 1

    with _connect() as conn:
        query_count = conn.execute("SELECT COUNT(*) AS count FROM chat_messages WHERE user_id=%s AND role='user'", (user["id"],)).fetchone()["count"]
    return AnalyticsData(
        total_documents=len(uploaded_documents),
        total_queries=query_count,
        incidents_count=0,
        incident_document_count=incidents_count,
        equipment_count=equipment_count,
        memory_nodes=memory_nodes,
        recent_activity=[],
        incidents_per_month=[],
        document_uploads_per_month=[
            {"month": month, "count": count}
            for month, count in month_counts.items()
        ],
        document_types=[
            {"name": k, "value": v}
            for k, v in type_counts.items()
        ],
        risk_signals=risk_signals(user["id"], uploaded_documents),
        top_entities=intelligence["top_entities"],
    )
