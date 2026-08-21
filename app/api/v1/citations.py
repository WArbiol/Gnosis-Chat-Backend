from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_supabase_client
from app.core.security import get_current_user
from app.schemas.user import UserProfile
from app.services.conversation_service import ConversationService


router = APIRouter()


class CitationSnippetResponse(BaseModel):
    id: UUID
    snippet: str


def get_conversation_service() -> ConversationService:
    return ConversationService(get_supabase_client())


@router.get("/{citation_id}", response_model=CitationSnippetResponse)
def get_citation_snippet(
    citation_id: UUID,
    current_user: UserProfile = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
):
    """Retrieve the book snippet for a specific citation on-demand."""
    snippet = service.get_citation_snippet(str(citation_id))
    if snippet is None:
        raise HTTPException(status_code=404, detail="Citation not found")
    return CitationSnippetResponse(id=citation_id, snippet=snippet)
