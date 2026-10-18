from enum import Enum
from typing import Any, Literal
import re

from pydantic import BaseModel, Field, field_validator, model_validator


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
    failure_reason: str | None = None
    node_count_kind: str = "estimated"


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    mobile: str


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=254)
    mobile: str = Field(max_length=20)
    password: str = Field(min_length=6, max_length=128)

    @field_validator('name', 'email', 'mobile')
    @classmethod
    def validate_identity(cls, value: str, info):
        value = value.strip()
        if not value:
            raise ValueError('This field is required')
        if info.field_name == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+', value):
            raise ValueError('Enter a valid email address')
        if info.field_name == 'mobile' and not re.fullmatch(r'\+?[1-9]\d{7,14}', value):
            raise ValueError('Use 8–15 digits, optionally prefixed with +')
        return value.lower() if info.field_name == 'email' else value


class AuthRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(max_length=12000)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    chat_history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    scope_mode: Literal['all', 'selected', 'auto'] = 'all'

    @model_validator(mode='after')
    def valid_scope(self):
        if not self.question.strip():
            raise ValueError('Question cannot be blank')
        # Compatibility for old clients supplying IDs without the new mode.
        if 'scope_mode' not in self.model_fields_set and self.document_ids:
            self.scope_mode = 'selected'
        if self.scope_mode == 'selected' and not self.document_ids:
            raise ValueError('Selected scope needs document IDs')
        if self.scope_mode != 'selected' and self.document_ids:
            raise ValueError('Document IDs require selected scope')
        return self


class Source(BaseModel):
    title: str
    excerpt: str
    relevance: float = Field(default=0, ge=0, le=1, description='Retrieval rank, not calibrated probability')
    page: int | None = None
    section: str | None = None
    document_id: str
    chunk_id: str
    source_id: str
    document_version: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    available: bool = True


class RelatedMemory(BaseModel):
    title: str
    summary: str


class ContentPart(BaseModel):
    text: str
    source_ids: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    content_parts: list[ContentPart] = Field(default_factory=list)
    reasoning: str
    sources: list[Source]
    related_memories: list[RelatedMemory]
    confidence: float | None = Field(default=None, ge=0, le=1, deprecated=True)
    mode: str = "general"
    action_plan: list[str] = []
    confidence_notes: str = ""
    query_type: str = "semantic"
    evidence_status: Literal['source_excerpts', 'partial', 'conflicting', 'unsupported', 'not_required'] = 'unsupported'
    scope_mode: str = 'all'
    effective_document_ids: list[str] = Field(default_factory=list)
    retrieval_diagnostics: dict[str, Any] = Field(default_factory=dict)


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
    document_uploads_per_month: list[dict[str, Any]] = []
    incident_document_count: int = 0
    metrics_note: str = 'Document signals are unreviewed; node counts are estimates. Verified incidents are not tracked.'
