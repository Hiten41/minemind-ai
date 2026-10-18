export interface Document {
  id: string
  name: string
  type: string
  status: string
  node_count: number
  uploaded_at: string
  dataset_name: string
  failure_reason?: string | null
  risk_signals?: RiskSignals
  risk_level?: RiskLevel
}

export type RiskLevel = 'high' | 'medium' | 'low' | 'none'

export interface RiskSignals {
  violations: number
  equipment: number
  hazards: number
}

export interface RiskAlert {
  id: string
  name: string
  risk_level: Exclude<RiskLevel, 'none'>
  risk_signals: RiskSignals
  date: string
  dataset_name: string
}

export interface DocumentIntelligenceItem {
  id: string
  name: string
  type: string
  status: string
  node_count: number
  signals: {
    hazards: string[]
    actions: string[]
    equipment: string[]
  }
  summary: string
}

export interface EntityCount {
  name: string
  count: number
}

export interface DocumentIntelligence {
  documents: DocumentIntelligenceItem[]
  top_entities: EntityCount[]
}

export interface DocumentPage {
  items: Document[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface ContentPart {
  text: string
  source_ids: string[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  content_parts?: ContentPart[]
  reasoning?: string
  sources?: Source[]
  related_memories?: RelatedMemory[]
  confidence?: number | null
  query_type?: string
  evidence_status?: 'source_excerpts' | 'partial' | 'conflicting' | 'unsupported' | 'not_required'
  scope_mode?: 'all' | 'selected' | 'auto'
  effective_document_ids?: string[]
  retrieval_diagnostics?: Record<string, unknown>
}

export interface User {
  id: string
  name: string
  email: string
  mobile: string
}

export interface AuthResponse {
  token: string
  user: User
}

export interface Source {
  document_id: string
  chunk_id: string
  source_id: string
  document_version: string
  page?: number | null
  section?: string | null
  available?: boolean
  title: string
  excerpt: string
  relevance: number
}

export interface RelatedMemory {
  title: string
  summary: string
}

export interface GraphNode {
  id: string
  label: string
  type: string
  data: Record<string, string>
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
}

export interface AnalyticsData {
  total_documents: number
  total_queries: number
  incidents_count: number
  equipment_count: number
  memory_nodes: number
  recent_activity: Record<string, string>[]
  document_uploads_per_month?: { month: string; count: number }[]
  incident_document_count?: number
  incidents_per_month: { month: string; count: number }[]
  document_types: { name: string; value: number }[]
}

export interface QueryResponse {
  answer: string
  content_parts?: ContentPart[]
  reasoning: string
  sources: Source[]
  related_memories: RelatedMemory[]
  confidence: number | null
  query_type?: string
  evidence_status?: 'source_excerpts' | 'partial' | 'conflicting' | 'unsupported' | 'not_required'
  scope_mode?: 'all' | 'selected' | 'auto'
  effective_document_ids?: string[]
  retrieval_diagnostics?: Record<string, unknown>
}
