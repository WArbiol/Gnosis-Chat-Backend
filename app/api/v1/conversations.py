from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.core.dependencies import get_supabase_client
from app.core.security import get_current_user
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
    PaginatedResponse,
)
from app.schemas.user import UserProfile
from app.services.conversation_service import ConversationService

router = APIRouter()


def get_conversation_service() -> ConversationService:
    # Service creates its own queries, using the Service Role Key for now
    # The actual RLS is bypassed by service role unless we explicitly configure user bindings,
    # but in our endpoints, we validate `user_id` ownership securely.
    # A rigorous implementation leverages supabase auth context for the queries directly,
    # but for simplicity we filter / restrict inside the service wrapper relying on the route logic.
    return ConversationService(get_supabase_client())


@router.get("", response_model=PaginatedResponse[ConversationResponse])
def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    current_user: UserProfile = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """Retrieve all conversations for the authenticated user, sorted by updated_at desc."""
    raw = service.list_conversations(limit, cursor)
    
    # Filter on our side for now to enforce RLS locally if service_role used
    filtered_data = [d for d in raw.data if str(d.user_id) == str(current_user.id)]
    raw.data = filtered_data
    return raw


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    data: ConversationCreate,
    current_user: UserProfile = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """Create a new conversation session."""
    title = data.title or "Nova conversa"
    return service.create_conversation(title, current_user.id)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: UUID,
    current_user: UserProfile = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """Get conversation details with its primary messages."""
    conv = service.get_conversation(str(conversation_id))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    if str(conv.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
        
    return conv


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID,
    current_user: UserProfile = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """Delete a conversation."""
    try:
        conv = service.get_conversation(str(conversation_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    if str(conv.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
        
    service.delete_conversation(str(conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: UUID,
    data: ConversationUpdate,
    current_user: UserProfile = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """Rename a conversation."""
    try:
        conv = service.get_conversation(str(conversation_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    if str(conv.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
        
    return service.update_conversation(str(conversation_id), data.title)


@router.get("/{conversation_id}/messages", response_model=PaginatedResponse[MessageResponse])
def list_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    current_user: UserProfile = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """List messages for a specific conversation."""
    try:
        conv = service.get_conversation(str(conversation_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    if str(conv.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
        
    return service.list_messages(str(conversation_id), limit, cursor)


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_message(
    conversation_id: UUID,
    data: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: UserProfile = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """Append a raw message to a conversation. (Usually backend handles this implicitly in /ask)."""
    try:
        conv = service.get_conversation(str(conversation_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    if str(conv.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
        
    msg = service.create_message(str(conversation_id), data.role, data.content)
    
    # If this is the FIRST message in a conversation titled 'Nova conversa', 
    # spawn background task to gen title
    if conv.title == "Nova conversa" and len(conv.messages) == 0 and data.role == "user":
        # Launch background title generation
        background_tasks.add_task(
            service.generate_title_async,
            str(conversation_id),
            data.content
        )
        
    return msg
