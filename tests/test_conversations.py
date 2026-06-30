import pytest
from httpx import AsyncClient

# Note: These tests assume a mocking approach or specific database state if running real DB
# For this sprint, we'll verify the router is registered and auth protects it.

@pytest.mark.asyncio
async def test_create_conversation_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/conversations", json={"title": "Test Auth"})
    assert response.status_code == 401 # Missing token -> 401 Unauthorized

@pytest.mark.asyncio
async def test_get_conversations_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/conversations")
    assert response.status_code == 401
