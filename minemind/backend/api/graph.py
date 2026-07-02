from fastapi import APIRouter, Depends

from models.schemas import GraphData
from services.auth_service import current_user, user_dataset_names
from services.advanced_ai import build_mining_knowledge_graph
from services.cognee_service import get_graph_data
from services.document_search import build_uploaded_text_graph

router = APIRouter()


@router.get("/api/graph", response_model=GraphData)
async def get_graph(user: dict[str, str] = Depends(current_user)):
    data = await get_graph_data(user_dataset_names(user["id"]))
    if not data.get("nodes"):
        data = build_mining_knowledge_graph(user["id"])
    if not data.get("nodes"):
        data = build_uploaded_text_graph(user["id"])
    return GraphData(**data)
