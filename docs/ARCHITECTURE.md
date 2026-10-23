# DocPilot — Overall Architecture and Project Flow

DocPilot is a voice-first, evidence-grounded document intelligence platform built on your existing RegionRAG retrieval engine. Users upload documents, ask questions using voice or text, receive answers generated from retrieved evidence, and navigate directly to the supporting passages in the original document.

The key design principle is to separate document processing, retrieval, answer generation, and evidence verification so that every answer can be traced back to its source.

## 1. High-level system architecture

## User Interface

React + TypeScript

Document upload · Voice input · Chat · PDF viewer · Citation highlights

### API and Application Layer

FastAPI

Authentication if needed · Uploads · Session management · Query orchestration

Document Processing

PDF parsing · OCR · Layout analysis · Text and region extraction

Output: chunks with page and region metadata

Voice Processing

Microphone · Speech recognition · Transcript editing · Query normalization

Output: text query

## RegionRAG Retrieval Engine

Embeddings → FAISS similarity search → optional reranking → top-k evidence

### Grounded Answer Engine

LLM generation · Evidence sufficiency check · Structured citations · Unsupported-answer handling

### Verified Response

Answer · Evidence snippets · Page numbers · Region highlights · Optional spoken response

The diagram shows the logical architecture. In implementation, document processing and voice processing are separate branches: document processing happens during ingestion, while voice processing happens when the user asks a question. Both feed into the same retrieval and answer-generation pipeline.

## 2. Two main workflows

DocPilot has two independent workflows that connect through the retrieval index.

### Flow A — Document ingestion

### 1

### Upload document

User uploads a PDF through the web interface.

### 2

### Extract content

Parse embedded text; use OCR for scanned pages.

### 3

### Analyze layout

Identify paragraphs, headings, tables, and regions where supported.

### 4

### Create chunks

Split content into meaningful passages while preserving page numbers and bounding boxes.

### 5

### Generate embeddings

Convert each chunk into a vector representation.

### 6

### Index and store

Save vectors in FAISS and retain the corresponding text and source metadata.

Important: Do not force every PDF through OCR. First check whether it contains extractable text, and use OCR when necessary. This reduces processing time and avoids introducing unnecessary recognition errors.

Each indexed chunk should retain its document ID, page number, chunk ID, text, and optional bounding-box coordinates. Those identifiers enable citations to point back to the correct source.

### Flow B — Voice question to grounded answer

### 1

### Capture the question

The user speaks into the microphone or types a question.

### 2

### Convert speech to text

An existing speech-recognition engine transcribes the audio; the user can correct the transcript.

### 3

### Retrieve evidence

Embed the question and search the document's FAISS index for relevant chunks.

### 4

### Rerank and assemble context

Optionally rerank candidates and construct a context containing the best passages and source IDs.

### 5

### Generate an answer

The LLM answers using the supplied evidence and returns structured references to source chunks.

### 6

### Validate and display

The backend checks citation IDs, returns source metadata, and flags insufficient evidence.

### 7

### Navigate to evidence

The frontend opens the cited page and highlights the passage or region when coordinates exist.

A critical detail: validating a citation is not the same as proving that it supports a claim. Checking that a source ID exists prevents fabricated references to nonexistent chunks, but semantic support still needs evaluation. For the MVP, make the source passage visible and use a conservative evidence-sufficiency check.

## 3. Data storage and component responsibilities

Keep the architecture simple enough to finish by October 30.

| Component              | Responsibility                                                           |
| ---------------------- | ------------------------------------------------------------------------ |
| React + TypeScript     | Upload UI, chat, microphone controls, PDF display, citation navigation   |
| FastAPI                | Upload endpoints, query orchestration, session handling, error responses |
| PDF parser + OCR       | Extract text and page information from documents                         |
| Layout analysis        | Preserve structural information and region coordinates where available   |
| Embedding model        | Encode document chunks and user questions                                |
| FAISS                  | Find semantically relevant chunks efficiently                            |
| LangChain              | Optionally orchestrate retrieval and LLM calls                           |
| LLM                    | Generate an answer grounded in the retrieved passages                    |
| SQLite / JSON metadata | Map chunk IDs to documents, pages, text, and coordinates                 |
| File storage           | Store uploaded PDFs and derived artifacts                                |

### How the data is connected

A useful source record might look like this:

```
{
  "document_id": "doc_001",
  "chunk_id": "chunk_042",
  "page_number": 7,
  "text": "The method has limitations under ...",
  "bbox": [120, 240, 520, 310]
}
```

The `bbox` is optional and should use a documented coordinate system consistent with your PDF viewer.

FAISS stores the vectors and their IDs; it does not replace the metadata store. Your application must maintain a reliable mapping between a retrieved vector and its original document passage.

For the challenge MVP, you can use a local FAISS index and SQLite metadata. Avoid adding a separate vector database unless your existing RegionRAG implementation already depends on one.

## 4. Recommended API design

Keep the API small. These endpoints are enough for the first release.

| Method   | Endpoint                                | Purpose                                   |
| -------- | --------------------------------------- | ----------------------------------------- |
| `POST`   | `/api/documents`                        | Upload and process a document             |
| `GET`    | `/api/documents/{id}`                   | Get document status and metadata          |
| `POST`   | `/api/documents/{id}/query`             | Ask a question about a document           |
| `GET`    | `/api/documents/{id}/pages/{page}`      | Retrieve page metadata if needed          |
| `GET`    | `/api/documents/{id}/chunks/{chunk_id}` | Retrieve a source chunk and its location  |
| `DELETE` | `/api/documents/{id}`                   | Delete a document and its associated data |

For voice input, the browser can handle transcription initially. That means the query endpoint receives the transcript as ordinary text, so you don't need to build a separate speech-processing service just to ship the MVP.

A query request might be:

```
{
  "question": "What limitations does the paper identify?",
  "top_k": 5
}
```

A response could look like:

```
{
  "answer": "The paper identifies ...",
  "insufficient_evidence": false,
  "citations": [
    {
      "chunk_id": "chunk_042",
      "page_number": 7,
      "text": "The method has limitations under ...",
      "bbox": [120, 240, 520, 310]
    }
  ]
}
```

These are proposed API contracts, not existing endpoints. Adapt them to the code you already have.

## 5. How your existing RegionRAG project fits in

This is the most important implementation decision: DocPilot should be a product layer on top of RegionRAG, not a replacement for it.

Reuse

Existing RegionRAG components

- OCR and document text extraction
- Layout-aware or region-aware document representations
- FAISS retrieval and embeddings
- Existing retrieval and question-answering logic
- Page and region metadata, if already available

Build for DocPilot

New product capabilities

- Voice-enabled question input
- Document upload and processing status
- A polished document-and-chat interface
- Structured, validated citations
- Click-to-navigate source highlighting
- An evidence evaluation and failure-handling layer

You can reuse the RegionRAG retrieval engine without requiring LayoutLMv3 to process every user query. Layout analysis is principally an ingestion concern; retrieval can search the resulting index directly.

## 6. Suggested repository structure

```
docpilot/
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── DocumentUpload.tsx
│       │   ├── VoiceInput.tsx
│       │   ├── ChatPanel.tsx
│       │   ├── CitationCard.tsx
│       │   └── PdfViewer.tsx
│       └── App.tsx
│
├── backend/
│   └── app/
│       ├── main.py
│       ├── api/
│       │   ├── documents.py
│       │   └── query.py
│       ├── services/
│       │   ├── document_processor.py
│       │   ├── retrieval.py
│       │   ├── answer_generator.py
│       │   └── citation_validator.py
│       ├── models/
│       └── storage/
│
├── regionrag/
│   └── existing retrieval and layout code
│
├── tests/
│   ├── test_retrieval.py
│   ├── test_citations.py
│   └── test_abstention.py
│
├── README.md
└── requirements.txt
```

Treat this as a target structure. Keep your existing filenames and imports if restructuring would introduce unnecessary risk.

## 7. What to prioritize for the challenge

P0 — Essential

PDF upload, retrieval, grounded answers, working citations, voice or text questions, and a deployed demo.

P1 — High-value differentiators

Clickable evidence highlighting, unsupported-question handling, and an evaluation dashboard showing actual test results.

P2 — Only if time remains

Multi-document comparison, spoken answers, document collections, user accounts, and advanced analytics.

One further consideration: use only documents you are permitted to upload, avoid logging sensitive document contents, and provide a clear deletion path for uploaded files.

## 8. The complete project flow in one line

## DocPilot

Upload document → Extract text and layout → Chunk and embed → Index in FAISS → Ask by voice or text → Retrieve evidence → Generate grounded answer → Validate citations → Highlight source

My recommendation: get the entire path working with one research paper before generalizing to multiple document types. Once that works reliably, demonstrate it with a research paper, a technical manual, and a report to substantiate DocPilot's broader positioning.

The next practical step is to inspect your existing RegionRAG repository and map its actual modules to this architecture before writing new code. That will show exactly what can be reused and what you need to implement for the challenge.