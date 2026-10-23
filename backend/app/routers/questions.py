import json
import uuid

from fastapi import APIRouter, HTTPException

from .. import config
from ..db import db
from ..schemas import CitationOut, QuestionRequest, QuestionResponse
from ..services.generation import ABSTAIN_ANSWER, extractive_answer, generate_answer
from ..services.mistral_client import MistralClient, MistralError
from ..services.retrieval import retrieve

router = APIRouter(prefix="/api/documents", tags=["questions"])


@router.post("/{document_id}/questions", response_model=QuestionResponse)
def ask_question(document_id: str, req: QuestionRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty.")

    with db() as conn:
        doc = conn.execute(
            "SELECT document_id, status FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        if doc["status"] != "ready":
            raise HTTPException(
                status_code=409,
                detail=f"Document is not ready (status: {doc['status']}).",
            )

        conversation_id = req.conversation_id
        if conversation_id:
            existing = conn.execute(
                "SELECT conversation_id FROM conversations WHERE conversation_id = ? "
                "AND document_id = ?",
                (conversation_id, document_id),
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
        else:
            conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO conversations (conversation_id, document_id) VALUES (?, ?)",
                (conversation_id, document_id),
            )

    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    user_message_id = f"msg_{uuid.uuid4().hex[:12]}"

    client: MistralClient | None = None
    try:
        client = MistralClient()
        evidence, best_cosine = retrieve(document_id, question, client=client)

        if not evidence or best_cosine < config.SUFFICIENCY_THRESHOLD:
            answer, grounded, used = ABSTAIN_ANSWER, False, []
        else:
            try:
                result = generate_answer(question, evidence, client=client)
            except MistralError:
                # Chat model unavailable: fall back to extractive answers that
                # still cite the exact retrieved passages.
                result = extractive_answer(evidence)
            answer, grounded, used = result.answer, result.grounded, result.cited_chunk_ids

        citations: list[CitationOut] = []
        by_id = {e.chunk_id: e for e in evidence}
        with db() as conn:
            conn.execute(
                "INSERT INTO messages (message_id, conversation_id, role, content) "
                "VALUES (?, ?, 'user', ?)",
                (user_message_id, conversation_id, question),
            )
            conn.execute(
                "INSERT INTO messages "
                "(message_id, conversation_id, role, content, grounded) "
                "VALUES (?, ?, 'assistant', ?, ?)",
                (message_id, conversation_id, answer, int(grounded)),
            )
            for position, chunk_id in enumerate(used, start=1):
                ev = by_id.get(chunk_id)
                if ev is None:
                    continue
                citation_id = f"cite_{uuid.uuid4().hex[:10]}"
                excerpt = ev.text[:500] + ("..." if len(ev.text) > 500 else "")
                conn.execute(
                    "INSERT INTO citations "
                    "(citation_id, message_id, chunk_id, page_number, excerpt, "
                    "bbox_json, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        citation_id,
                        message_id,
                        chunk_id,
                        ev.page_number,
                        excerpt,
                        json.dumps(ev.bbox) if ev.bbox else None,
                        position,
                    ),
                )
                citations.append(
                    CitationOut(
                        citation_id=citation_id,
                        chunk_id=chunk_id,
                        page_number=ev.page_number,
                        excerpt=excerpt,
                        bbox=ev.bbox,
                    )
                )
    except MistralError as exc:
        with db() as conn:
            conn.execute(
                "INSERT INTO messages (message_id, conversation_id, role, content) "
                "VALUES (?, ?, 'user', ?)",
                (user_message_id, conversation_id, question),
            )
            conn.execute(
                "INSERT INTO messages "
                "(message_id, conversation_id, role, content, grounded) "
                "VALUES (?, ?, 'assistant', ?, 0)",
                (
                    message_id,
                    conversation_id,
                    f"The language model is unavailable: {exc}. "
                    "Your question was preserved — please try again.",
                ),
            )
        raise HTTPException(
            status_code=502,
            detail=f"Model request failed: {exc}. Your question was preserved.",
        )
    finally:
        if client is not None:
            client.close()

    return QuestionResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        answer=answer,
        grounded=grounded,
        citations=citations,
    )
