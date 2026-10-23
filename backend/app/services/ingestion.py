"""Document ingestion pipeline: validate -> extract -> chunk -> embed -> index."""

import json
import threading
import uuid
from pathlib import Path

import numpy as np

from .. import config
from ..db import db
from .chunking import chunk_pages
from .extraction import ExtractionError, extract_pdf
from .mistral_client import MistralClient, MistralError
from .vector_index import DocumentIndex, index_path, l2_normalize

PDF_MAGIC = b"%PDF-"


def validate_pdf(data: bytes, filename: str) -> str | None:
    """Return an error message, or None when the upload is acceptable."""
    if not filename.lower().endswith(".pdf"):
        return "Only PDF files are supported."
    if not data.startswith(PDF_MAGIC):
        return "File does not look like a valid PDF (missing %PDF header)."
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        return f"File exceeds the {config.MAX_UPLOAD_MB} MB limit."
    if len(data) < 128:
        return "File is too small to be a valid PDF."
    return None


def create_document(filename: str, data: bytes) -> str:
    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    path = config.UPLOAD_DIR / f"{document_id}.pdf"
    path.write_bytes(data)
    with db() as conn:
        conn.execute(
            "INSERT INTO documents (document_id, filename, storage_path, status) "
            "VALUES (?, ?, ?, 'uploaded')",
            (document_id, filename, str(path)),
        )
    return document_id


def set_status(document_id: str, status: str, error: str | None = None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE documents SET status = ?, error = ? WHERE document_id = ?",
            (status, error, document_id),
        )


def schedule_ingestion(document_id: str) -> None:
    """Run ingestion on a daemon thread (tests may patch this)."""
    worker = threading.Thread(target=run_ingestion, args=(document_id,), daemon=True)
    worker.start()


def claim_for_ingestion(document_id: str) -> bool:
    """Atomically move a document back into the queue.

    Returns False when it does not exist or is not in a retryable state
    (failed / uploaded), preventing double retries and racing uploads.
    """
    with db() as conn:
        cur = conn.execute(
            "UPDATE documents SET status = 'uploaded', error = NULL "
            "WHERE document_id = ? AND status IN ('failed', 'uploaded')",
            (document_id,),
        )
        return cur.rowcount == 1


def recover_interrupted_documents() -> int:
    """After a restart, re-queue uploads that never finished processing."""
    with db() as conn:
        rows = conn.execute(
            "SELECT document_id, storage_path FROM documents "
            "WHERE status IN ('uploaded', 'processing')"
        ).fetchall()
    recovered = 0
    for row in rows:
        if Path(row["storage_path"]).exists():
            set_status(row["document_id"], "uploaded")
            schedule_ingestion(row["document_id"])
            recovered += 1
        else:
            set_status(
                row["document_id"],
                "failed",
                "Original file is missing after restart; please upload again.",
            )
    return recovered


def run_ingestion(document_id: str) -> None:
    """Background worker: converts an uploaded PDF into a queryable index."""
    with db() as conn:
        row = conn.execute(
            "SELECT storage_path FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
    if row is None:
        return
    path = Path(row["storage_path"])

    try:
        set_status(document_id, "processing")
        pages = extract_pdf(path)
        chunks = chunk_pages(pages)
        if not chunks:
            raise ExtractionError("No text could be chunked from this document.")

        client = MistralClient()
        vectors = client.embed([c.text for c in chunks])

        matrix = l2_normalize(np.asarray(vectors, dtype=np.float32))
        index = DocumentIndex(dim=matrix.shape[1])
        chunk_ids = [f"{document_id}:p{c.page_number}:{c.seq}" for c in chunks]
        index.build(chunk_ids, vectors)
        index.save(index_path(document_id))

        with db() as conn:
            conn.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            conn.executemany(
                "INSERT INTO pages (document_id, page_number, width, height) "
                "VALUES (?, ?, ?, ?)",
                [(document_id, p.number, p.width, p.height) for p in pages],
            )
            conn.executemany(
                "INSERT INTO chunks "
                "(chunk_id, document_id, page_number, seq, text, bbox_json, word_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        cid,
                        document_id,
                        c.page_number,
                        c.seq,
                        c.text,
                        json.dumps(c.bbox) if c.bbox else None,
                        c.word_count,
                    )
                    for cid, c in zip(chunk_ids, chunks)
                ],
            )
            conn.execute(
                "UPDATE documents SET status = 'ready', error = NULL, "
                "page_count = ?, chunk_count = ? WHERE document_id = ?",
                (len(pages), len(chunks), document_id),
            )
        from .retrieval import invalidate_document

        invalidate_document(document_id)
    except (ExtractionError, MistralError, OSError) as exc:
        set_status(document_id, "failed", str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        set_status(document_id, "failed", f"Unexpected error: {exc}")


def delete_document(document_id: str) -> bool:
    from .retrieval import invalidate_document
    from .vector_index import delete_index

    with db() as conn:
        row = conn.execute(
            "SELECT storage_path FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
    path = Path(row["storage_path"])
    if path.exists():
        path.unlink()
    delete_index(document_id)
    invalidate_document(document_id)
    return True
