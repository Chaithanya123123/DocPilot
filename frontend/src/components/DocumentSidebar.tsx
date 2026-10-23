import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { DocumentItem } from '../api/types'

interface Props {
  documents: DocumentItem[]
  selectedId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  onRetry: (id: string) => void
  onUploaded: () => void
}

const STATUS_LABEL: Record<string, string> = {
  uploaded: 'Queued',
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
}

export function DocumentSidebar({
  documents,
  selectedId,
  onSelect,
  onDelete,
  onRetry,
  onUploaded,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const handleFiles = async (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    setError('')
    setUploading(true)
    try {
      await api.upload(file)
      onUploaded()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="sidebar">
      <div
        className={`upload-zone ${dragging ? 'dragging' : ''} ${uploading ? 'busy' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFiles(e.dataTransfer.files)
        }}
      >
        <div className="upload-title">{uploading ? 'Uploading…' : '＋ Upload PDF'}</div>
        <div className="upload-hint">Drop a file here or click to browse</div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
      {error && <div className="error-banner">{error}</div>}

      <div className="doc-list">
        <div className="doc-list-title">Documents</div>
        {documents.length === 0 && <div className="empty-note">No documents yet.</div>}
        {documents.map((doc) => (
          <div
            key={doc.document_id}
            className={`doc-item ${selectedId === doc.document_id ? 'selected' : ''}`}
            onClick={() => onSelect(doc.document_id)}
          >
            <div className="doc-item-main">
              <div className="doc-name" title={doc.filename}>
                {doc.filename}
              </div>
              <div className="doc-meta">
                <span className={`status status-${doc.status}`}>
                  {STATUS_LABEL[doc.status] ?? doc.status}
                </span>
                {doc.status === 'ready' && doc.page_count != null && (
                  <span className="doc-sub">
                    {doc.page_count} pp · {doc.chunk_count} chunks
                  </span>
                )}
              </div>
              {doc.status === 'failed' && doc.error && (
                <>
                  <div className="doc-error">{doc.error}</div>
                  <button
                    type="button"
                    className="retry-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      onRetry(doc.document_id)
                    }}
                  >
                    Retry processing
                  </button>
                </>
              )}
            </div>
            <button
              type="button"
              className="icon-btn"
              title="Delete document and all its data"
              onClick={(e) => {
                e.stopPropagation()
                if (confirm(`Delete “${doc.filename}” and its index?`)) onDelete(doc.document_id)
              }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
