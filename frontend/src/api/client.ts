import type { DocumentItem, QuestionResponse } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body)
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
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

  fileUrl: (id: string) => `/api/documents/${id}/file`,

  health: () =>
    request<{ status: string; api_key_configured: boolean; chat_model: string }>(
      '/api/health',
    ),
}
