from datetime import datetime
import re

from fastapi import APIRouter, Depends

from models.schemas import AnalyticsData
from services.auth_service import current_user, list_documents
from services.advanced_ai import build_document_intelligence, document_text, risk_signals
from services.document_search import repair_document_node_counts

router = APIRouter()


INCIDENT_MARKERS = {
    "accident",
    "fatal",
    "fatality",
    "fatalities",
    "explosion",
    "inundation",
    "roof fall",
    "firedamp",
    "fire damp",
    "gas explosion",
    "colliery",
}


def derived_document_type(doc: dict) -> str:
    stored_type = str(doc.get("type") or "regulation").lower()
    if stored_type == "incident":
        return stored_type

    name = str(doc.get("name") or "").lower()
    text = document_text(doc).lower()
    sample = text[:50000]

    if "accident" in name or "incident" in name:
        return "incident"
    if len(re.findall(r"\|\s*(?:fire|gas|coal|roof|inundation|blasting|methane).{0,80}\|\s*\d+\s*fatal", sample)) >= 2:
        return "incident"
    if len(re.findall(r"\b\d{2}/\d{2}/\d{4}\b", sample)) >= 5 and sum(marker in sample for marker in INCIDENT_MARKERS) >= 4:
        return "incident"

    return stored_type


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
