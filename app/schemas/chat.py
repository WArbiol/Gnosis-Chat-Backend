from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.conversation import CitationResponse, MessageResponse

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: UUID | None = None
