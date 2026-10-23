export interface DocumentItem {
  document_id: string
  filename: string
  status: string
  error?: string | null
  page_count?: number | null
  chunk_count?: number | null
  created_at: string
}

export interface Citation {
  citation_id: string
  chunk_id: string
  page_number: number
  excerpt: string
  bbox?: number[] | null
}

export interface QuestionResponse {
  conversation_id: string
  message_id: string
  answer: string
  grounded: boolean
  citations: Citation[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  grounded?: boolean
  citations?: Citation[]
  failed?: boolean
}

export interface Highlight {
  chunkId: string
  page: number
  bbox?: number[] | null
}
