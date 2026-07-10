from datetime import datetime

from fastapi import APIRouter, Depends

from models.schemas import AnalyticsData
from services.auth_service import current_user, list_documents
from services.advanced_ai import build_document_intelligence, classify_document_type, document_text, risk_signals
from services.document_search import repair_document_node_counts

router = APIRouter()


def derived_document_type(doc: dict) -> str:
    return classify_document_type(doc)


def has_equipment_signals(doc: dict, intelligence_doc: dict | None) -> bool:
    if str(doc.get("type") or "").lower() == "manual":
        return True
    signals = (intelligence_doc or {}).get("signals") or {}
    if signals.get("equipment"):
        return True
    text = document_text(doc).lower()
    return any(term in text for term in ("machinery", "equipment", "fan", "ventilator", "pump", "winder", "conveyor"))


@router.get("/api/analytics",
            response_model=AnalyticsData)
async def get_analytics(user: dict[str, str] = Depends(current_user)):
    repair_document_node_counts(user["id"])
    uploaded_documents = list_documents(user["id"])
    intelligence = build_document_intelligence(user["id"])
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
        memory_nodes += int(doc.get("node_count") or 0)
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

    return AnalyticsData(
        total_documents=len(uploaded_documents),
        total_queries=0,
        incidents_count=incidents_count,
        equipment_count=equipment_count,
        memory_nodes=memory_nodes,
        recent_activity=[],
        incidents_per_month=[
            {"month": month, "count": count}
            for month, count in (incident_month_counts or month_counts).items()
        ],
        document_types=[
            {"name": k, "value": v}
            for k, v in type_counts.items()
        ],
        risk_signals=risk_signals(user["id"]),
        top_entities=intelligence["top_entities"],
    )
