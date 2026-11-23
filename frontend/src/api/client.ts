import type { ChatMessage, DocumentItem, QuestionResponse } from './types'

// Empty means same origin (Vite proxy in development, FastAPI in single-command mode).
const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new ApiError('Cannot reach the DocPilot backend. Check that it is running.', 0)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body)
    } catch {
      /* keep statusText */
    }
    throw new ApiError(detail, res.status)
  }
  return res.json() as Promise<T>
}

export const api = {
  listDocuments: () => request<DocumentItem[]>('/api/documents'),

  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ document_id: string; filename: string; status: string }>(
      '/api/documents',
      { method: 'POST', body: form },
    )
  },

  removeDocument: (id: string) =>
    request<{ deleted: string }>(`/api/documents/${id}`, { method: 'DELETE' }),

  retryDocument: (id: string) =>
    request<{ document_id: string; status: string }>(
      `/api/documents/${id}/retry`,
      { method: 'POST' },
    ),

  ask: (id: string, question: string, conversationId?: string) =>
    request<QuestionResponse>(`/api/documents/${id}/questions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
    }),

  conversation: (id: string) =>
    request<{ conversation_id: string; messages: ChatMessage[] }>(`/api/conversations/${id}`),

  fileUrl: (id: string) => `${API_BASE}/api/documents/${id}/file`,

  health: () =>
    request<{ status: string; api_key_configured: boolean; chat_model: string }>(
      '/api/health',
    ),
}
