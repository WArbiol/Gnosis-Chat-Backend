from app.core.dependencies import get_supabase_client
from app.infrastructure.supabase.supabase_database import SupabaseDatabase
from app.schemas.user import UserProfile, PlanEnum


async def get_user_profile(user_id: str) -> UserProfile:
    """Fetch user profile from Supabase public.users table with fail-safe exception handling."""
    client = get_supabase_client()
    db = SupabaseDatabase(client)
    try:
        return await db.get_user_profile(user_id)
    except Exception as e:
        print(f"WARNING: Transient error fetching profile for {user_id}: {e}. Returning fallback basic profile.")
        return UserProfile(
            id=user_id,
            email=f"{user_id}@gnosis.chat",
            plan=PlanEnum.BASIC,
            chamber_level=1,
            question_count=0
        )
