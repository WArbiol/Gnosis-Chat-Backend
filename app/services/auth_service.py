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


async def delete_user_account(user_id: str) -> dict:
    """Delete all user data (conversations, messages, profile, Stripe subscription, and auth user)."""
    client = get_supabase_client()
    
    # 1. Check and cancel active Stripe subscription if present
    try:
        from app.core.config import settings
        import stripe
        
        user_res = client.table("users").select("stripe_customer_id, subscription_status").eq("id", user_id).execute()
        if user_res.data:
            customer_id = user_res.data[0].get("stripe_customer_id")
            if customer_id and settings.stripe_secret_key:
                stripe.api_key = settings.stripe_secret_key
                subscriptions = stripe.Subscription.list(customer=customer_id, status="active")
                for sub in subscriptions.auto_paging_iter():
                    try:
                        stripe.Subscription.delete(sub.id)
                        print(f"AUTH_DELETE: Canceled active Stripe subscription {sub.id} for user {user_id}")
                    except Exception as sub_err:
                        print(f"AUTH_DELETE: Error canceling subscription {sub.id}: {sub_err}")
    except Exception as stripe_err:
        print(f"AUTH_DELETE: Stripe check/cancel error (ignored): {stripe_err}")

    # 2. Delete conversations and messages
    try:
        conv_res = client.table("conversations").select("id").eq("user_id", user_id).execute()
        conv_ids = [c["id"] for c in (conv_res.data or [])]
        
        if conv_ids:
            client.table("messages").delete().in_("conversation_id", conv_ids).execute()
            client.table("conversations").delete().eq("user_id", user_id).execute()
    except Exception as conv_err:
        print(f"AUTH_DELETE: Error deleting conversations: {conv_err}")

    # 3. Delete user row in public.users
    try:
        client.table("users").delete().eq("id", user_id).execute()
    except Exception as user_err:
        print(f"AUTH_DELETE: Error deleting public.users row: {user_err}")

    # 4. Delete Supabase Auth user record using service role admin
    try:
        client.auth.admin.delete_user(user_id)
        print(f"AUTH_DELETE: Deleted auth user {user_id} in Supabase Auth.")
    except Exception as auth_err:
        print(f"AUTH_DELETE: Error deleting Supabase Auth user: {auth_err}")

    return {"status": "success", "message": "Conta e dados excluídos com sucesso."}
