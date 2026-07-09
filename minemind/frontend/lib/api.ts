import type {
  AnalyticsData,
  Document,
  DocumentIntelligence,
  DocumentPage,
  GraphEdge,
  GraphNode,
  QueryResponse,
  AuthResponse,
  RiskAlert,
  User,
  ChatMessage
} from '@/types'

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, '')
const BASE = configuredApiBase || (
  process.env.NODE_ENV === 'production' ? '' : 'http://127.0.0.1:8001'
)
const TOKEN_KEY = 'minemind_token'
const AUTH_TIMEOUT_MS = 15000
const QUERY_TIMEOUT_MS = 120000

type ChatHistoryItem = {
  role: string
  content: string
}

async function parseJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    let detail = fallback
    try {
      const body = await res.json()
      detail = body.detail ?? fallback
    } catch {
      detail = fallback
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

function apiUrl(path: string): string {
  if (!BASE) {
    throw new Error('NEXT_PUBLIC_API_BASE_URL is required in production')
  }
  if (
    process.env.NODE_ENV === 'production' &&
    /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?($|\/)/i.test(BASE)
  ) {
    throw new Error('Production API URL is set to localhost. Set NEXT_PUBLIC_API_BASE_URL to the deployed backend URL and redeploy.')
  }
  return `${BASE}${path}`
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('MineMind is still reading your document memory. Please try a narrower question or ask again in a moment.')
    }
    throw error
  } finally {
    window.clearTimeout(timer)
  }
}

export function getAuthToken(): string {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setAuthToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearAuthToken() {
  window.localStorage.removeItem(TOKEN_KEY)
}

function authHeaders(): HeadersInit {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function registerUser(payload: {
  name: string
  email: string
  mobile: string
  password: string
}): Promise<AuthResponse> {
  const res = await fetchWithTimeout(apiUrl('/api/auth/register'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }, AUTH_TIMEOUT_MS)
  const auth = await parseJson<AuthResponse>(res, 'Registration failed')
  setAuthToken(auth.token)
  return auth
}

export async function loginUser(payload: {
  identifier: string
  password: string
}): Promise<AuthResponse> {
  const res = await fetchWithTimeout(apiUrl('/api/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }, AUTH_TIMEOUT_MS)
  const auth = await parseJson<AuthResponse>(res, 'Login failed')
  setAuthToken(auth.token)
  return auth
}

export async function getCurrentUser(): Promise<User> {
  const res = await fetch(apiUrl('/api/auth/me'), {
    headers: authHeaders()
  })
  return parseJson<User>(res, 'Session expired')
}

export async function uploadDocument(
  file: File,
  type: string
): Promise<Document> {
  const form = new FormData()
  form.append('file', file)
  form.append('doc_type', type)
  const res = await fetch(apiUrl('/api/upload'), {
    method: 'POST',
    headers: authHeaders(),
    body: form
  })
  return parseJson<Document>(res, 'Upload failed')
}

export async function queryAI(
  question: string,
  history: ChatHistoryItem[]
): Promise<QueryResponse> {
  const res = await fetchWithTimeout(apiUrl('/api/query'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      question,
      chat_history: history
    })
  }, QUERY_TIMEOUT_MS)
  return parseJson<QueryResponse>(res, 'Query failed')
}

export async function getChatHistory(): Promise<ChatMessage[]> {
  const res = await fetch(apiUrl('/api/chat/history'), {
    headers: authHeaders()
  })
  return parseJson<ChatMessage[]>(res, 'Failed to fetch chat history')
}

export async function getDocuments(): Promise<Document[]> {
  const res = await fetch(apiUrl('/api/documents'), {
    headers: authHeaders()
  })
  return parseJson<Document[]>(res, 'Failed to fetch docs')
}

export async function getDocumentIntelligence(): Promise<DocumentIntelligence> {
  const res = await fetch(apiUrl('/api/intelligence/documents'), {
    headers: authHeaders()
  })
  return parseJson<DocumentIntelligence>(res, 'Failed to fetch document intelligence')
}

export async function getDocumentsPage(options: {
  limit?: number
  offset?: number
  type?: string
} = {}): Promise<DocumentPage> {
  const params = new URLSearchParams()
  params.set('limit', String(options.limit ?? 50))
  params.set('offset', String(options.offset ?? 0))
  if (options.type) params.set('doc_type', options.type)
  const res = await fetch(apiUrl(`/api/documents/page?${params.toString()}`), {
    headers: authHeaders()
  })
  return parseJson<DocumentPage>(res, 'Failed to fetch docs')
}

export async function getDocumentFile(documentId: string): Promise<Blob> {
  const res = await fetch(apiUrl(`/api/documents/${documentId}/file`), {
    headers: authHeaders()
  })
  if (!res.ok) {
    let detail = 'Original file is not available for preview'
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // File endpoints can also return non-JSON errors.
    }
    throw new Error(detail)
  }
  return res.blob()
}

export async function improveMemory(): Promise<{ status: string; message: string }> {
  const res = await fetch(apiUrl('/api/improve'), {
    method: 'POST',
    headers: authHeaders()
  })
  return parseJson<{ status: string; message: string }>(res, 'Improve failed')
}

export async function forgetDataset(name: string): Promise<{ status: string }> {
  const res = await fetch(
    apiUrl(`/api/forget/${name}`),
    { method: 'DELETE', headers: authHeaders() }
  )
  return parseJson<{ status: string }>(res, 'Forget failed')
}

export async function getGraphData(): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const res = await fetch(apiUrl('/api/graph'), {
    headers: authHeaders()
  })
  return parseJson<{ nodes: GraphNode[]; edges: GraphEdge[] }>(res, 'Graph fetch failed')
}

export async function getAnalytics(): Promise<AnalyticsData> {
  const res = await fetch(apiUrl('/api/analytics'), {
    headers: authHeaders()
  })
  return parseJson<AnalyticsData>(res, 'Analytics failed')
}

export async function getAlerts(): Promise<RiskAlert[]> {
  const res = await fetch(apiUrl('/api/alerts'), {
    headers: authHeaders()
  })
  return parseJson<RiskAlert[]>(res, 'Alerts failed')
}
