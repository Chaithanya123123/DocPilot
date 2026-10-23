import json

from fastapi import APIRouter, HTTPException

from ..db import db
from ..schemas import CitationOut, ConversationOut, MessageOut

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: str):
    with db() as conn:
        conv = conn.execute(
            "SELECT conversation_id, document_id FROM conversations "
            "WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        messages = conn.execute(
            "SELECT message_id, role, content, grounded, created_at FROM messages "
            "WHERE conversation_id = ? ORDER BY created_at, rowid",
            (conversation_id,),
        ).fetchall()
        citations = conn.execute(
            "SELECT c.citation_id, c.message_id, c.chunk_id, c.page_number, "
            "c.excerpt, c.bbox_json FROM citations c "
            "JOIN messages m ON m.message_id = c.message_id "
            "WHERE m.conversation_id = ? ORDER BY c.position",
            (conversation_id,),
        ).fetchall()

    by_message: dict[str, list[CitationOut]] = {}
    for c in citations:
        by_message.setdefault(c["message_id"], []).append(
            CitationOut(
                citation_id=c["citation_id"],
                chunk_id=c["chunk_id"],
                page_number=c["page_number"],
                excerpt=c["excerpt"],
                bbox=json.loads(c["bbox_json"]) if c["bbox_json"] else None,
            )
        )

    return ConversationOut(
        conversation_id=conv["conversation_id"],
        document_id=conv["document_id"],
        messages=[
            MessageOut(
                message_id=m["message_id"],
                role=m["role"],
                content=m["content"],
                grounded=m["grounded"],
                citations=by_message.get(m["message_id"], []),
                created_at=m["created_at"],
            )
            for m in messages
        ],
    )
