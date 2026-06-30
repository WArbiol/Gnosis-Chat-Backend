from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import get_current_user
from app.schemas.user import UserProfile
from app.services import auth_service

router = APIRouter()

class ProfileUpdate(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None

@router.get("/me", response_model=UserProfile)
async def get_me(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
    """Return the profile of the currently authenticated user."""
    # current_user from get_current_user only has ID and Email from the JWT token.
    # We fetch the full profile from the database here.
    return await auth_service.get_user_profile(current_user.id)

@router.patch("/me", response_model=UserProfile)
async def update_me(
    update_data: ProfileUpdate,
    current_user: UserProfile = Depends(get_current_user)
) -> UserProfile:
    """Update user profile fields."""
    from app.core.dependencies import get_supabase_client
    
    client = get_supabase_client()
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if update_dict:
        client.table("users").update(update_dict).eq("id", current_user.id).execute()
        
    return await auth_service.get_user_profile(current_user.id)
