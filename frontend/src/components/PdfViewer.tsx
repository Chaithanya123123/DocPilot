import { useEffect, useRef, useState } from 'react'
import * as pdfjs from 'pdfjs-dist'
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import { api } from '../api/client'
import type { Highlight } from '../api/types'

pdfjs.GlobalWorkerOptions.workerPort = new PdfWorker()

const BASE_WIDTH = 720

interface Props {
  documentId: string | null
  pageCount: number | null
  highlight: Highlight | null
}

interface PageMeta {
  scale: number
  width: number
  height: number
}

export function PdfViewer({ documentId, pageCount, highlight }: Props) {
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map())
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map())
  const [pageMeta, setPageMeta] = useState<Map<number, PageMeta>>(new Map())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setPageMeta(new Map())
    canvasRefs.current.clear()
    pageRefs.current.clear()
    setError('')
    if (!documentId) return

    const renderAll = async () => {
      setLoading(true)
      let pdf: PDFDocumentProxy | null = null
      try {
        pdf = await pdfjs.getDocument(api.fileUrl(documentId)).promise
        const meta = new Map<number, PageMeta>()
        for (let n = 1; n <= pdf.numPages; n++) {
          if (cancelled) return
          const page = await pdf.getPage(n)
          const base = page.getViewport({ scale: 1 })
          const scale = BASE_WIDTH / base.width
          const viewport = page.getViewport({ scale })
          const canvas = canvasRefs.current.get(n)
          if (canvas) {
            const dpr = window.devicePixelRatio || 1
            canvas.width = Math.floor(viewport.width * dpr)
            canvas.height = Math.floor(viewport.height * dpr)
            canvas.style.width = `${viewport.width}px`
            canvas.style.height = `${viewport.height}px`
            const ctx = canvas.getContext('2d')
            if (ctx) {
              await page.render({
                canvasContext: ctx,
                viewport,
                transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
              }).promise
            }
          }
          meta.set(n, {
            scale,
            width: viewport.width,
            height: viewport.height,
          })
        }
        if (!cancelled) setPageMeta(meta)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load PDF.')
        }
      } finally {
        if (!cancelled) setLoading(false)
        await pdf?.destroy().catch(() => undefined)
      }
    }
    void renderAll()
    return () => {
      cancelled = true
    }
  }, [documentId])

  useEffect(() => {
    if (!highlight) return
    const el = pageRefs.current.get(highlight.page)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [highlight])

  if (!documentId) {
    return (
      <div className="viewer viewer-empty">
        <div className="viewer-empty-inner">
          <div className="viewer-empty-icon">📄</div>
          <div>Select or upload a document to begin.</div>
        </div>
      </div>
    )
  }

  const pages = pageCount && pageCount > 0 ? Array.from({ length: pageCount }, (_, i) => i + 1) : []

  return (
    <div className="viewer">
      {loading && <div className="viewer-banner">Rendering pages…</div>}
      {error && <div className="error-banner viewer-banner">{error}</div>}
      <div className="viewer-scroll">
        {pages.map((n) => {
          const meta = pageMeta.get(n)
          const isHighlighted = highlight?.page === n
          return (
            <div
              key={n}
              className="page-wrap"
              ref={(el) => {
                if (el) pageRefs.current.set(n, el)
                else pageRefs.current.delete(n)
              }}
            >
              <div
                className={`page-canvas-wrap ${isHighlighted ? 'flash' : ''}`}
                style={meta ? { width: meta.width, height: meta.height } : undefined}
              >
                <canvas
                  ref={(el) => {
                    if (el) canvasRefs.current.set(n, el)
                    else canvasRefs.current.delete(n)
                  }}
                />
                {isHighlighted && highlight?.bbox && meta && (
                  <div
                    className="highlight-rect"
                    style={{
                      left: highlight.bbox[0] * meta.scale,
                      top: highlight.bbox[1] * meta.scale,
                      width: (highlight.bbox[2] - highlight.bbox[0]) * meta.scale,
                      height: (highlight.bbox[3] - highlight.bbox[1]) * meta.scale,
                    }}
                  />
                )}
              </div>
              <div className="page-label">Page {n}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
