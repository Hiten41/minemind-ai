from fastapi import APIRouter, Depends

from models.schemas import QueryRequest, QueryResponse
from services.advanced_ai import (
    action_plan_for_mode,
    build_document_intelligence,
    citations_from_chunks,
    confidence_notes,
    detect_agent_mode,
    hybrid_retrieve,
    risk_signals,
    user_memory_profile,
)
from services.auth_service import current_user

router = APIRouter()


@router.get("/api/intelligence/documents")
async def get_document_intelligence(user: dict[str, str] = Depends(current_user)):
    return build_document_intelligence(user["id"])


@router.get("/api/intelligence/risk")
async def get_risk_intelligence(user: dict[str, str] = Depends(current_user)):
    return {"risk_signals": risk_signals(user["id"])}


@router.get("/api/intelligence/profile")
async def get_memory_profile(user: dict[str, str] = Depends(current_user)):
    return user_memory_profile(user["id"])


@router.post("/api/agents/run", response_model=QueryResponse)
async def run_agent(request: QueryRequest, user: dict[str, str] = Depends(current_user)):
    from api.query import query_ai
    return await query_ai(request, user)
