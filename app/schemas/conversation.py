from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TimestampedModel(BaseModel):
    created_at: datetime
    updated_at: datetime | None = None


# Messages
class MessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class CitationResponse(BaseModel):
    id: UUID
    message_id: UUID
    pdf_name: str
    page: int
    snippet: str = ""
    chunk_id: str | None = None
    sort_order: int = 0


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    route: str | None = None
    token_count: int | None = 0
    created_at: datetime
    citations: list[CitationResponse] = []
    suggested_followups: list[str] = []


# Conversations
class ConversationCreate(BaseModel):
    title: str | None = "Nova conversa"


class ConversationUpdate(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None


class ConversationResponse(TimestampedModel):
    id: UUID
    user_id: UUID
    title: str
    is_pinned: bool = False


class ConversationDetail(ConversationResponse):
    messages: list[MessageResponse] = []


# Pagination generic models
class Pagination(BaseModel):
    has_more: bool
    next_cursor: str | None


class PaginatedResponse[T](BaseModel):
    data: list[T]
    pagination: Pagination
