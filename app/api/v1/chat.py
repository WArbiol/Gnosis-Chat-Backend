from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.chat import ChatRequest
from app.schemas.conversation import MessageResponse
from app.schemas.user import UserProfile
from app.services import chat_service

router = APIRouter()


@router.post("/ask", response_model=MessageResponse)
async def ask(
    request: ChatRequest,
    user: UserProfile = Depends(get_current_user),
) -> MessageResponse:
    return await chat_service.ask(request, user)
