from collections.abc import AsyncGenerator
from functools import lru_cache

from qdrant_client import AsyncQdrantClient

from app.core.config import Settings, settings


@lru_cache
def get_settings() -> Settings:
    return settings


async def get_qdrant_client() -> AsyncGenerator[AsyncQdrantClient]:
    """Yield an async Qdrant client. Cleanup on request end."""
    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )
    try:
        yield client
    finally:
        await client.close()


from supabase import Client, create_client

def get_supabase_client() -> Client:
    """Return a Supabase client configured with the service role key."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ValueError("Supabase configuration missing in environment variables.")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
