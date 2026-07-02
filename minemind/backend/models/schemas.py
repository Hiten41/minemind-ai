from enum import Enum
from typing import Any

from pydantic import BaseModel


class DocumentType(str, Enum):
    regulation = "regulation"
    manual = "manual"
    incident = "incident"
    maintenance = "maintenance"
    shift = "shift"


class UploadResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    node_count: int
    uploaded_at: str
    dataset_name: str
    risk_signals: dict[str, int] = {}
    risk_level: str = "none"


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    mobile: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    mobile: str
    password: str


class AuthRequest(BaseModel):
    identifier: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class ChatMessage(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str
    chat_history: list[ChatMessage]


class Source(BaseModel):
    title: str
    excerpt: str
    relevance: float
    page: int | None = None
    section: str | None = None


class RelatedMemory(BaseModel):
    title: str
    summary: str


class QueryResponse(BaseModel):
    answer: str
    reasoning: str
    sources: list[Source]
    related_memories: list[RelatedMemory]
    confidence: float
    mode: str = "general"
    action_plan: list[str] = []
    confidence_notes: str = ""
    query_type: str = "semantic"


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    data: dict[str, Any]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class AnalyticsData(BaseModel):
    total_documents: int
    total_queries: int
    incidents_count: int
    equipment_count: int
    memory_nodes: int
    recent_activity: list[dict[str, Any]]
    incidents_per_month: list[dict[str, Any]]
    document_types: list[dict[str, Any]]
    risk_signals: list[dict[str, Any]] = []
    top_entities: list[dict[str, Any]] = []
