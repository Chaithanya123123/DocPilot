from typing import Literal, Optional

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    document_id: str
    filename: str
    status: str
    error: Optional[str] = None
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    created_at: str


class UploadOut(BaseModel):
    document_id: str
    filename: str
    status: str


class StatusOut(BaseModel):
    document_id: str
    filename: str
    status: str
    error: Optional[str] = None
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None


class CitationOut(BaseModel):
    citation_id: str
    chunk_id: str
    page_number: int
    excerpt: str
    bbox: Optional[list[float]] = None


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = None


class QuestionResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    grounded: bool
    citations: list[CitationOut]


class MessageOut(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    grounded: Optional[bool] = None
    citations: list[CitationOut] = []
    created_at: str


class ConversationOut(BaseModel):
    conversation_id: str
    document_id: str
    messages: list[MessageOut]


class PageChunkOut(BaseModel):
    chunk_id: str
    page_number: int
    text: str
    bbox: Optional[list[float]] = None


class PageOut(BaseModel):
    document_id: str
    page_number: int
    width: float
    height: float
    chunks: list[PageChunkOut]
