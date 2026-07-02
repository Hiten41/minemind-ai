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
    mode = detect_agent_mode(request.question)
    chunks = hybrid_retrieve(user["id"], request.question, mode=mode, limit=8)
    citations = citations_from_chunks(chunks)
    if citations:
        answer = (
            "From your uploaded PDFs: "
            f"I found evidence for `{mode}` in {len(citations)} passage(s). "
            "Use the action plan below and open the cited sources for details."
        )
        reasoning = "The agent selected passages by hybrid keyword and mining-domain signal scoring."
    else:
        answer = (
            "I could not find this in your uploaded PDFs. General answer: "
            f"No stored document evidence matched `{mode}` strongly enough yet."
        )
        reasoning = "No uploaded-document evidence was found for this agent mode."
    return QueryResponse(
        answer=answer,
        reasoning=reasoning,
        sources=[citation.as_source() for citation in citations[:5]],
        related_memories=[],
        confidence=0.82 if citations else 0.45,
        mode=mode,
        action_plan=action_plan_for_mode(mode, citations),
        confidence_notes=confidence_notes(citations),
    )
