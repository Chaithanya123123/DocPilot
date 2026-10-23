import { useEffect, useRef, useState } from 'react'
import type { ChatMessage, Citation } from '../api/types'
import { VoiceInput } from './VoiceInput'

interface Props {
  documentId: string | null
  documentReady: boolean
  messages: ChatMessage[]
  busy: boolean
  onSend: (question: string) => void
  onCitationClick: (citation: Citation) => void
  onNewConversation: () => void
}

export function ChatPanel({
  documentId,
  documentReady,
  messages,
  busy,
  onSend,
  onCitationClick,
  onNewConversation,
}: Props) {
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  const submit = () => {
    const question = input.trim()
    if (!question || busy || !documentReady) return
    setInput('')
    onSend(question)
  }

  return (
    <div className="chat">
      <div className="chat-header">
        <span>Ask this document</span>
        <button type="button" className="ghost-btn" onClick={onNewConversation}>
          New conversation
        </button>
      </div>

      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat-empty">
            Ask a question about the selected document — by voice or text.
            Every answer cites the exact passages it came from.
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`bubble-row ${msg.role}`}>
            <div className={`bubble ${msg.role} ${msg.failed ? 'failed' : ''}`}>
              <div className="bubble-text">{msg.content}</div>
              {msg.role === 'assistant' && msg.grounded === false && !msg.failed && (
                <div className="grounded-note">⚠ Not grounded in document evidence</div>
              )}
              {msg.citations && msg.citations.length > 0 && (
                <div className="citations">
                  {msg.citations.map((c, i) => (
                    <button
                      key={c.citation_id}
                      type="button"
                      className="citation-card"
                      onClick={() => onCitationClick(c)}
                      title="Open source in the PDF viewer"
                    >
                      <span className="citation-index">[{i + 1}]</span>
                      <span className="citation-page">p. {c.page_number}</span>
                      <span className="citation-excerpt">“{c.excerpt.slice(0, 140)}…”</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="bubble-row assistant">
            <div className="bubble assistant thinking">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
              Retrieving evidence…
            </div>
          </div>
        )}
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          rows={2}
          value={input}
          placeholder={
            documentReady
              ? 'Ask a question… (or press the mic)'
              : documentId
                ? 'Document is not ready yet'
                : 'Select a document first'
          }
          disabled={!documentReady}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
        />
        <div className="chat-actions">
          <VoiceInput
            disabled={!documentReady}
            onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))}
          />
          <button
            type="button"
            className="send-btn"
            onClick={submit}
            disabled={!documentReady || busy || !input.trim()}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
