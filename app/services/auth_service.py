from app.core.dependencies import get_supabase_client
from app.schemas.user import UserProfile


async def get_user_profile(user_id: str) -> UserProfile:
    """Fetch user profile from Supabase public.users table."""
    client = get_supabase_client()
    
    response = client.table("users").select("*").eq("id", user_id).single().execute()
    data = response.data
    
    if not data:
        raise ValueError(f"User profile not found for id: {user_id}")
        
    from datetime import datetime
    last_reset_str = data.get("last_reset_at")
    last_reset = None
    if last_reset_str:
        try:
            last_reset = datetime.fromisoformat(last_reset_str.replace("Z", "+00:00"))
        except Exception:
            pass

    return UserProfile(
        id=data["id"],
        email=data["email"],
        avatar_url=data.get("avatar_url"),
        plan=data.get("plan", "free"),
        chamber_level=data.get("chamber_level", 1),
        question_count=data.get("question_count", 0),
        last_reset_at=last_reset
    )
