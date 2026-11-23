import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api/client'
import type { ChatMessage, Citation, DocumentItem, Highlight } from './api/types'
import { ChatPanel } from './components/ChatPanel'
import { DocumentSidebar } from './components/DocumentSidebar'
import { PdfViewer } from './components/PdfViewer'

const convKey = (docId: string) => `docpilot:conversation:${docId}`

export default function App() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const [highlight, setHighlight] = useState<Highlight | null>(null)
  const [health, setHealth] = useState<{ api_key_configured: boolean; chat_model: string } | null>(null)
  const [offline, setOffline] = useState(false)
  const nextId = useRef(0)
  const selectedRef = useRef<string | null>(null)
  useEffect(() => {
    selectedRef.current = selectedId
  }, [selectedId])

  const refreshDocuments = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments())
      setOffline(false)
    } catch (err) {
      setOffline(err instanceof ApiError && (err.status === 0 || err.status >= 500))
    }
  }, [])

  useEffect(() => {
    void refreshDocuments()
  }, [refreshDocuments])

  // Load health on start and again whenever the backend comes back.
  useEffect(() => {
    if (offline) return
    void api.health().then(setHealth).catch(() => setHealth(null))
  }, [offline])

  const processing = documents.some((d) => d.status === 'uploaded' || d.status === 'processing')
  useEffect(() => {
    if (!processing && !offline) return
    const timer = setInterval(() => void refreshDocuments(), offline ? 5000 : 2000)
    return () => clearInterval(timer)
  }, [processing, offline, refreshDocuments])

  const selected = documents.find((d) => d.document_id === selectedId) ?? null

  useEffect(() => {
    setMessages([])
    setConversationId(undefined)
    setHighlight(null)
    if (!selectedId) return

    // Restore saved conversation history for this document, if any.
    const saved = localStorage.getItem(convKey(selectedId))
    if (!saved) return
    let stale = false
    api
      .conversation(saved)
      .then((data) => {
        if (stale) return
        setConversationId(data.conversation_id)
        setMessages(data.messages)
      })
      .catch((err) => {
        // Forget the saved conversation only if it is gone, not when the network fails.
        if (err instanceof ApiError && err.status === 404) {
          localStorage.removeItem(convKey(selectedId))
        }
      })
    return () => {
      stale = true
    }
  }, [selectedId])

  const handleSend = async (question: string) => {
    if (!selectedId) return
    const docId = selectedId
    const userId = `local-user-${nextId.current++}`
    setMessages((m) => [...m, { id: userId, role: 'user', content: question }])
    setBusy(true)
    try {
      const res = await api.ask(docId, question, conversationId)
      localStorage.setItem(convKey(docId), res.conversation_id)
      // The answer belongs to the document it was asked about, not the one now open.
      if (selectedRef.current !== docId) return
      setConversationId(res.conversation_id)
      setMessages((m) => [
        ...m,
        {
          id: res.message_id,
          role: 'assistant',
          content: res.answer,
          grounded: res.grounded,
          citations: res.citations,
        },
      ])
    } catch (err) {
      if (selectedRef.current !== docId) return
      setMessages((m) => [
        ...m,
        {
          id: `local-error-${nextId.current++}`,
          role: 'assistant',
          content:
            err instanceof Error
              ? err.message
              : 'Something went wrong. Your question was not lost — try again.',
          failed: true,
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  const handleCitationClick = (citation: Citation) => {
    setHighlight({
      chunkId: citation.chunk_id,
      page: citation.page_number,
      bbox: citation.bbox,
    })
  }

  const handleDelete = async (id: string) => {
    try {
      await api.removeDocument(id)
      if (selectedId === id) setSelectedId(null)
      await refreshDocuments()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Delete failed.')
    }
  }

  const handleRetry = async (id: string) => {
    try {
      await api.retryDocument(id)
      await refreshDocuments()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Retry failed.')
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">DP</span>
          <div>
            <div className="brand-name">DocPilot</div>
            <div className="brand-tag">Voice-first · Evidence-grounded document Q&amp;A</div>
          </div>
        </div>
        {health && (
          <div className={`health ${health.api_key_configured ? 'ok' : 'bad'}`}>
            {health.api_key_configured
              ? `Mistral · ${health.chat_model}`
              : 'MISTRAL_API_KEY missing — backend/.env'}
          </div>
        )}
      </header>

      {offline && (
        <div className="error-banner" role="status">
          Cannot reach the DocPilot backend. Retrying every few seconds…
        </div>
      )}

      <div className="workspace">
        <aside className="panel side-panel">
          <DocumentSidebar
            documents={documents}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onDelete={handleDelete}
            onRetry={handleRetry}
            onUploaded={refreshDocuments}
          />
        </aside>

        <main className="panel viewer-panel">
          <PdfViewer
            documentId={selectedId}
            pageCount={selected?.page_count ?? null}
            highlight={highlight}
          />
        </main>

        <section className="panel chat-panel">
          <ChatPanel
            documentId={selectedId}
            documentReady={selected?.status === 'ready'}
            messages={messages}
            busy={busy}
            onSend={handleSend}
            onCitationClick={handleCitationClick}
            onNewConversation={() => {
              setMessages([])
              setConversationId(undefined)
              if (selectedId) localStorage.removeItem(convKey(selectedId))
            }}
          />
        </section>
      </div>
    </div>
  )
}
