# DocPilot

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![FAISS](https://img.shields.io/badge/Vector%20Search-FAISS-1081C2)
![Mistral](https://img.shields.io/badge/LLM-Mistral-FA520F)
![License](https://img.shields.io/badge/License-MIT-green)

**Voice-first, evidence-grounded document intelligence.** Upload a PDF, ask
questions by voice or text, and get answers linked to the exact supporting
passages — click a citation to jump to the page and see the source region
highlighted in the PDF viewer.

> Built with [Wispr Flow](https://wispr.flow) — every requirement, follow-up,
> and line of this codebase was dictated, not typed.
> `#NoHandsChallenge`

## Table of contents

- [Demo](#demo)
- [Architecture](#architecture)
- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [API](#api)
- [Configuration](#configuration-backendenv)
- [Evaluation](#evaluation)
- [Tests](#tests)
- [Storage layout](#storage-layout)
- [Project layout](#project-layout)
- [Voice input](#voice-input)
- [Security notes](#security-notes)
- [Known limitations](#known-limitations)
- [Design document](#design-document)

## Demo

🔗 **Video demo:** _link coming soon_ (≤2 minutes)

Watch for three things:

1. **Ask by voice** → grounded answer with numbered citations, each card
   showing the page and the source excerpt.
2. **Click a citation** → the PDF viewer scrolls to the exact page and draws a
   pulsing highlight over the supporting passage's real bounding box.
3. **Unsupported question** → DocPilot abstains instead of hallucinating.

## Architecture

```
┌──────────────────────────  User  ──────────────────────────┐
│   Upload PDF · Speak or type questions · Click citations   │
└──────────────────────────────┬─────────────────────────────┘
                               ▼
┌────────────────────  React + TypeScript  ──────────────────┐
│  Document library · PDF.js viewer · Web Speech · Chat      │
└──────────────────────────────┬─────────────────────────────┘
                               ▼
┌──────────────────────  FastAPI backend  ───────────────────┐
│  Uploads · Sessions · Status · Query orchestration         │
│                                                            │
│  ┌─ Ingestion ────────┐  ┌─ Retrieval ─────────────────┐   │
│  │ pdfplumber + bbox  │  │ mistral-embed + FAISS       │   │
│  │ page-scoped chunks │  │ BM25 + reciprocal-rank fuse │   │
│  └─────────┬──────────┘  └──────────────┬──────────────┘   │
│            ▼                            ▼                  │
│  ┌─ Generation ───────────────┐  ┌─ Validation ────────┐   │
│  │ Mistral JSON answers       │  │ server-side citation│   │
│  │ grounded-only prompting    │  │ ID + bbox resolver  │   │
│  └────────────────────────────┘  └─────────────────────┘   │
└──────────────────────────────┬─────────────────────────────┘
                               ▼
      SQLite metadata · FAISS indexes · Original PDFs
```

The full design document (flows, storage schema, failure handling) lives in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## How it works

**Ingestion** — `POST /api/documents` validates the PDF (magic bytes, size),
stores the original file, extracts text with per-word bounding boxes
(pdfplumber), chunks each page with overlap (chunks never span pages, so every
citation maps to one highlight rectangle), embeds chunks with `mistral-embed`,
and builds a per-document FAISS index. Status is polled at
`GET /api/documents/{id}/status`.

**Asking** — voice (browser Web Speech API) and text converge on the same
endpoint. The query is embedded with the same model, searched against FAISS
(dense cosine) and a BM25 index (lexical), and fused with reciprocal rank
fusion. If the best cosine is below `SUFFICIENCY_THRESHOLD`, DocPilot abstains
without calling the model. Otherwise the LLM answers from evidence blocks
only, naming chunk IDs — the server validates those IDs against what was
actually retrieved and resolves pages/bounding boxes from stored chunk
metadata. The model can never invent a page number or coordinate.

**Citations** — each citation stores `chunk_id`, `page_number`, an excerpt,
and the chunk bbox. The frontend scrolls the PDF viewer to the page and draws
the highlight rect scaled by the rendered page viewport.

**Failure handling** — failed ingestion marks the document with an error and
offers a **Retry** button (safe against double retries via an atomic status
claim); interrupted uploads are re-queued automatically on server restart;
invalid uploads are rejected; LLM 429/5xx triggers a fast failover to an
*extractive mode* (closest passages quoted verbatim, still cited) behind a
rate-limit cooldown circuit breaker; retrieval below threshold returns an
abstention answer; delete removes the file, index, chunks, and conversations.

## Quick start

Requires Python 3.11+, Node 18+, and a Mistral API key.

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
copy .env.example .env      # then put your MISTRAL_API_KEY in .env
python -m uvicorn app.main:app --reload --port 8000

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Or use the helper scripts from the repo root:

```powershell
.\start-backend.ps1         # terminal 1
.\start-frontend.ps1        # terminal 2
```

Try it: upload `samples/sample_report.pdf`, wait for **Ready**, then ask
"What limitations does the authors' method have?" and click a citation card.

Generate a fresh sample document any time:

```bash
python backend/scripts/make_sample_pdf.py
```

### Single-command mode

After `npm run build` in `frontend/`, FastAPI serves the built UI itself —
one process, one port:

```bash
cd frontend && npm run build
cd ../backend && python -m uvicorn app.main:app --port 8000
# open http://127.0.0.1:8000
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/documents` | Upload + register a PDF |
| GET | `/api/documents` | List documents |
| GET | `/api/documents/{id}/status` | Ingestion progress |
| GET | `/api/documents/{id}/file` | Original PDF (for the viewer) |
| GET | `/api/documents/{id}/pages/{n}` | Page dimensions + chunk metadata |
| POST | `/api/documents/{id}/questions` | Ask (text or transcribed voice) |
| POST | `/api/documents/{id}/retry` | Re-queue a failed document |
| GET | `/api/conversations/{id}` | Restore conversation history |
| DELETE | `/api/documents/{id}` | Delete document + index + metadata |
| GET | `/api/health` | Config/model check |

Example question response:

```json
{
  "answer": "The method has limitations in...",
  "grounded": true,
  "citations": [
    {
      "citation_id": "cite_01",
      "chunk_id": "doc_abc:p8:0",
      "page_number": 8,
      "excerpt": "The original source passage...",
      "bbox": [72.0, 61.7, 537.7, 310.2]
    }
  ]
}
```

Bounding boxes are real coordinates extracted from the PDF text layer.

## Configuration (`backend/.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `MISTRAL_API_KEY` | — | required |
| `MISTRAL_CHAT_MODEL` | `mistral-small-latest` | answer generation |
| `MISTRAL_EMBED_MODEL` | `mistral-embed` | chunks + queries |
| `SUFFICIENCY_THRESHOLD` | `0.45` | coarse cosine floor before calling the LLM |
| `TOP_K_EVIDENCE` | `6` | evidence blocks sent to the model |
| `CHUNK_WORDS` / `CHUNK_OVERLAP_WORDS` | `220` / `40` | page-scoped chunking |
| `MAX_UPLOAD_MB` | `50` | upload limit |

Note on abstention: the numeric threshold only filters clearly unrelated
queries; cosine scores alone do not prove relevance (on a small document,
off-topic queries can still score ~0.6). The primary sufficiency guard is the
model's instruction to set `grounded: false` when evidence is missing — such
answers are returned with no citations and flagged in the UI. Calibrate the
threshold per deployment with the eval script.

## Evaluation

```bash
cd backend
# retrieval quality (no server needed)
python evaluate/evaluate.py --doc <document_id> --json report.json

# full pipeline against a running server: latency, grounding, citation resolution
python evaluate/evaluate.py --doc <document_id> --live http://127.0.0.1:8000
```

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q
```

24 tests cover upload validation, page-scoped chunking and bounding boxes,
server-side citation validation (invented IDs are dropped), threshold
abstention, chat-failure extractive fallback, retry semantics, restart
recovery, conversation restore, and the delete cascade. Mistral is mocked —
the suite runs offline and never spends API quota.

## Storage layout

```
backend/storage/
  docpilot.db          # documents, pages, chunks, conversations, messages, citations
  uploads/<doc>.pdf    # original files
  indexes/<doc>.index.npy + .ids.json   # per-document FAISS/numpy index + id map
```

SQLite keeps documents, chunk text with page numbers and bounding boxes, and
conversation history with stable IDs so citations still resolve after a
restart. The original PDF is stored separately from the vector index — a
vector alone cannot tell the UI where evidence appears.

## Project layout

```
backend/app/
  main.py              FastAPI app, CORS, startup recovery, static UI mount
  db.py                SQLite schema + connections
  routers/             documents, questions, conversations
  services/
    extraction.py      pdfplumber text + bboxes
    chunking.py        page-scoped overlapping chunks
    mistral_client.py  embeddings + JSON chat, retries, cooldown
    vector_index.py    per-document FAISS index (numpy fallback)
    bm25.py            lexical index
    retrieval.py       hybrid dense + BM25 with RRF
    generation.py      grounded answers + citation validation + extractive fallback
    ingestion.py       upload validation → extract → chunk → embed → index
frontend/src/
  App.tsx              3-pane layout, polling, conversation restore
  components/          DocumentSidebar, PdfViewer, ChatPanel, VoiceInput
backend/evaluate/      retrieval/grounding/latency evaluation (offline + --live)
backend/tests/         pytest suite (mocked Mistral, runs offline)
samples/               generated demo PDF
docs/ARCHITECTURE.md   full design document
```

## Voice input

Uses the browser Web Speech API (Chrome/Edge). Speech is transcribed in the
browser and edited in the same textarea as typed input, then sent to the same
question endpoint — there is no separate voice backend. System-wide dictation
tools (e.g. Wispr Flow) also work: focus the chat textarea and dictate.

## Security notes

- Only `%PDF-` files under the size limit are accepted.
- The API has no authentication; bind it to localhost, and add auth plus
  document-level authorization before multi-user deployment.
- Sent to Mistral: retrieved chunk text and the question — nothing else.

## Known limitations

- Text-layer PDFs only; scanned/image-only PDFs are rejected (no OCR fallback
  in this build).
- Bounding boxes come from the PDF text layer; complex tables/columns may
  produce fragmented chunks.
- If Mistral chat is rate-limited (free-tier keys can hit `429` with
  `x-ratelimit-limit-req-minute: 0`), DocPilot automatically serves extractive
  cited answers and recovers to LLM answers within ~2 minutes of the limit
  lifting. Embeddings are typically unaffected. In extractive mode, answers
  present closest passages rather than judging sufficiency, so unanswerable
  questions still show passages (clearly labeled) instead of abstaining —
  the model's abstention behavior returns once chat access is restored.

## Design document

The full architecture spec — ingestion flow, question flow, citation flow,
storage schema, and failure handling — is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## License

[MIT](LICENSE) © DocPilot contributors

---

Built with [Wispr Flow](https://wispr.flow) for the **No Hands Challenge**
`#NoHandsChallenge` · @WeMakeDevs
