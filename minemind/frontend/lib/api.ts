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
const AUTH_TIMEOUT_MS = 30000
const SESSION_TIMEOUT_MS = 15000
const QUERY_TIMEOUT_MS = 210000
const STANDARD_REQUEST_TIMEOUT_MS = 20000
const UPLOAD_TIMEOUT_MS = 120000
const AUTH_TIMEOUT_MESSAGE = 'MineMind could not reach the sign-in service in 30 seconds. Please try again.'
const SESSION_TIMEOUT_MESSAGE = 'MineMind could not restore your session. Please sign in again.'
const QUERY_TIMEOUT_MESSAGE = 'MineMind is still reading your document memory. Please try a narrower question or ask again in a moment.'

type ChatHistoryItem = {
  role: string
  content: string
}

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function parseJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    let detail = fallback
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail)
        ? body.detail.map((issue: { msg?: string; loc?: (string | number)[]; type?: string; ctx?: { min_length?: number } }) => {
          const field = issue.loc?.at(-1)
          if (field === 'password' && issue.type === 'string_too_short') {
            return `Password must be at least ${issue.ctx?.min_length ?? 6} characters long.`
          }
          const label = typeof field === 'string' ? `${field.charAt(0).toUpperCase()}${field.slice(1)}: ` : ''
          return `${label}${issue.msg || 'Invalid input'}`
        }).join('; ')
        : fallback
    } catch {
      detail = fallback
    }
    throw new ApiError(detail, res.status)
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
  timeoutMs: number,
  timeoutMessage: string
): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(timeoutMessage)
    }
    if (error instanceof TypeError) {
      throw new Error('Cannot reach MineMind right now. Check your connection and try again.')
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

export async function logoutUser(): Promise<void> {
  const res = await fetchWithTimeout(apiUrl('/api/auth/logout'), {
    method: 'POST', headers: authHeaders()
  }, SESSION_TIMEOUT_MS, 'Sign-out could not be confirmed. Please retry.')
  await parseJson<{ status: string }>(res, 'Sign-out failed')
  clearAuthToken()
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
  }, AUTH_TIMEOUT_MS, AUTH_TIMEOUT_MESSAGE)
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
  }, AUTH_TIMEOUT_MS, AUTH_TIMEOUT_MESSAGE)
  const auth = await parseJson<AuthResponse>(res, 'Login failed')
  setAuthToken(auth.token)
  return auth
}

export async function getCurrentUser(): Promise<User> {
  const res = await fetchWithTimeout(apiUrl('/api/auth/me'), {
    headers: authHeaders()
  }, SESSION_TIMEOUT_MS, SESSION_TIMEOUT_MESSAGE)
  return parseJson<User>(res, 'Session expired')
}

export async function uploadDocument(
  file: File,
  type: string,
  requestKey: string = crypto.randomUUID()
): Promise<Document> {
  const form = new FormData()
  form.append('file', file)
  form.append('doc_type', type)
  const res = await fetchWithTimeout(apiUrl('/api/upload'), {
    method: 'POST',
    headers: { ...authHeaders(), 'Idempotency-Key': requestKey },
    body: form
  }, UPLOAD_TIMEOUT_MS, 'The upload is taking longer than two minutes. Check the file and try again.')
  return parseJson<Document>(res, 'Upload failed')
}

export async function retryDocument(documentId: string): Promise<{ status: string }> {
  const res = await fetchWithTimeout(apiUrl(`/api/documents/${documentId}/retry`), {
    method: 'POST', headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'Retry request timed out; check the document status.')
  return parseJson<{ status: string }>(res, 'Indexing retry failed')
}

export async function queryAI(
  question: string,
  history: ChatHistoryItem[],
  documentIds: string[] = []
): Promise<QueryResponse> {
  const res = await fetchWithTimeout(apiUrl('/api/query'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      question,
      chat_history: history,
      scope_mode: documentIds.length ? 'selected' : 'all',
      document_ids: documentIds
    })
  }, QUERY_TIMEOUT_MS, QUERY_TIMEOUT_MESSAGE)
  return parseJson<QueryResponse>(res, 'Query failed')
}

export async function getChatHistory(): Promise<ChatMessage[]> {
  const res = await fetchWithTimeout(apiUrl('/api/chat/history'), {
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'Chat history is taking too long to load. Refresh to try again.')
  return parseJson<ChatMessage[]>(res, 'Failed to fetch chat history')
}

export async function getDocuments(): Promise<Document[]> {
  const res = await fetchWithTimeout(apiUrl('/api/documents'), {
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'Your documents are taking too long to load. Please retry.')
  return parseJson<Document[]>(res, 'Failed to fetch docs')
}

export async function getDocumentIntelligence(): Promise<DocumentIntelligence> {
  const res = await fetchWithTimeout(apiUrl('/api/intelligence/documents'), {
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'Document insights are taking too long to load. Please refresh.')
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
  const res = await fetchWithTimeout(apiUrl(`/api/documents/page?${params.toString()}`), {
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'Your documents are taking too long to load. Please retry.')
  return parseJson<DocumentPage>(res, 'Failed to fetch docs')
}

export async function getDocumentFile(documentId: string): Promise<Blob> {
  const res = await fetchWithTimeout(apiUrl(`/api/documents/${documentId}/file`), {
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'The document preview is taking too long to load. Please try again.')
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
  const res = await fetchWithTimeout(apiUrl('/api/improve'), {
    method: 'POST',
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'Memory improvement is taking too long. Please try again.')
  return parseJson<{ status: string; message: string }>(res, 'Improve failed')
}

export async function forgetDataset(name: string): Promise<{ status: string }> {
  const res = await fetchWithTimeout(
    apiUrl(`/api/forget/${name}`),
    { method: 'DELETE', headers: authHeaders() },
    STANDARD_REQUEST_TIMEOUT_MS,
    'Removing the document is taking too long. Please try again.'
  )
  return parseJson<{ status: string }>(res, 'Forget failed')
}

export async function getGraphData(): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> {
  const res = await fetchWithTimeout(apiUrl('/api/graph'), {
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'The knowledge graph is taking too long to load. Please refresh.')
  return parseJson<{ nodes: GraphNode[]; edges: GraphEdge[] }>(res, 'Graph fetch failed')
}

export async function getAnalytics(): Promise<AnalyticsData> {
  const res = await fetchWithTimeout(apiUrl('/api/analytics'), {
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'Analytics are taking too long to load. Please refresh.')
  return parseJson<AnalyticsData>(res, 'Analytics failed')
}

export async function getAlerts(): Promise<RiskAlert[]> {
  const res = await fetchWithTimeout(apiUrl('/api/alerts'), {
    headers: authHeaders()
  }, STANDARD_REQUEST_TIMEOUT_MS, 'Alerts are taking too long to load. Please refresh.')
  return parseJson<RiskAlert[]>(res, 'Alerts failed')
}
