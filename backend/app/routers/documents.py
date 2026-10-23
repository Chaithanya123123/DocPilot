import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..db import db
from ..schemas import DocumentOut, PageChunkOut, PageOut, StatusOut, UploadOut
from ..services.ingestion import (
    claim_for_ingestion,
    create_document,
    delete_document,
    schedule_ingestion,
    set_status,
    validate_pdf,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", response_model=UploadOut)
async def upload_document(file: UploadFile):
    data = await file.read()
    filename = file.filename or "document.pdf"
    error = validate_pdf(data, filename)
    if error:
        raise HTTPException(status_code=400, detail=error)
    document_id = create_document(filename, data)
    schedule_ingestion(document_id)
    with db() as conn:
        row = conn.execute(
            "SELECT document_id, filename, status FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
    return UploadOut(**dict(row))


@router.get("", response_model=list[DocumentOut])
def list_documents():
    with db() as conn:
        rows = conn.execute(
            "SELECT document_id, filename, status, error, page_count, chunk_count, "
            "created_at FROM documents ORDER BY created_at DESC"
        ).fetchall()
    return [DocumentOut(**dict(r)) for r in rows]


@router.get("/{document_id}/status", response_model=StatusOut)
def document_status(document_id: str):
    with db() as conn:
        row = conn.execute(
            "SELECT document_id, filename, status, error, page_count, chunk_count "
            "FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return StatusOut(**dict(row))


@router.get("/{document_id}/file")
def document_file(document_id: str):
    with db() as conn:
        row = conn.execute(
            "SELECT storage_path, filename FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = Path(row["storage_path"])
    if not path.exists():
        raise HTTPException(status_code=410, detail="Stored file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=row["filename"])


@router.get("/{document_id}/pages/{page_number}", response_model=PageOut)
def get_page(document_id: str, page_number: int):
    with db() as conn:
        page = conn.execute(
            "SELECT page_number, width, height FROM pages "
            "WHERE document_id = ? AND page_number = ?",
            (document_id, page_number),
        ).fetchone()
        if page is None:
            raise HTTPException(status_code=404, detail="Page not found.")
        chunks = conn.execute(
            "SELECT chunk_id, page_number, text, bbox_json FROM chunks "
            "WHERE document_id = ? AND page_number = ? ORDER BY seq",
            (document_id, page_number),
        ).fetchall()
    return PageOut(
        document_id=document_id,
        page_number=page["page_number"],
        width=page["width"],
        height=page["height"],
        chunks=[
            PageChunkOut(
                chunk_id=c["chunk_id"],
                page_number=c["page_number"],
                text=c["text"],
                bbox=json.loads(c["bbox_json"]) if c["bbox_json"] else None,
            )
            for c in chunks
        ],
    )


@router.post("/{document_id}/retry", response_model=StatusOut)
def retry_document(document_id: str):
    """Re-queue a failed (or stuck) document for ingestion."""
    if not claim_for_ingestion(document_id):
        with db() as conn:
            row = conn.execute(
                "SELECT document_id, status FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        raise HTTPException(
            status_code=409,
            detail=f"Document cannot be retried while status is '{row['status']}'.",
        )
    with db() as conn:
        stored = conn.execute(
            "SELECT storage_path FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
    if stored is None or not Path(stored["storage_path"]).exists():
        set_status(document_id, "failed", "Original file is missing; upload again.")
        raise HTTPException(status_code=410, detail="Original file is missing.")
    schedule_ingestion(document_id)
    return document_status(document_id)


@router.delete("/{document_id}")
def remove_document(document_id: str):
    if not delete_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"deleted": document_id}
