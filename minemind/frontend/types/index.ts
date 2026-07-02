export interface Document {
  id: string
  name: string
  type: string
  status: string
  node_count: number
  uploaded_at: string
  dataset_name: string
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

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  sources?: Source[]
  related_memories?: RelatedMemory[]
  confidence?: number
  query_type?: 'semantic' | 'temporal'
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
  incidents_per_month: { month: string; count: number }[]
  document_types: { name: string; value: number }[]
}

export interface QueryResponse {
  answer: string
  reasoning: string
  sources: Source[]
  related_memories: RelatedMemory[]
  confidence: number
  query_type?: 'semantic' | 'temporal'
}
