from unittest.mock import MagicMock
import pytest
from httpx import AsyncClient

from app.api.v1.conversations import get_conversation_service
from app.core.security import get_current_user
from app.main import app
from app.schemas.user import UserProfile


@pytest.mark.asyncio
async def test_create_conversation_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/conversations", json={"title": "Test Auth"})
    assert response.status_code == 401 # Missing token -> 401 Unauthorized


@pytest.mark.asyncio
async def test_get_conversations_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/conversations")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_conversation_idempotent_when_already_deleted(client: AsyncClient, mock_user: UserProfile):
    """Deleting a non-existent or already-deleted conversation should return 204 without 500 error."""
    mock_service = MagicMock()
    mock_service.get_conversation.return_value = None

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    try:
        response = await client.delete("/api/v1/conversations/a5acce16-c56d-44cf-8344-0cbde874d1e5")
        assert response.status_code == 204
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_own_conversation_success(client: AsyncClient, mock_user: UserProfile):
    """Deleting own conversation succeeds with 204."""
    mock_service = MagicMock()
    mock_conv = MagicMock()
    mock_conv.id = "a5acce16-c56d-44cf-8344-0cbde874d1e5"
    mock_conv.user_id = mock_user.id
    mock_service.get_conversation.return_value = mock_conv

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    try:
        response = await client.delete("/api/v1/conversations/a5acce16-c56d-44cf-8344-0cbde874d1e5")
        assert response.status_code == 204
        mock_service.delete_conversation.assert_called_once_with("a5acce16-c56d-44cf-8344-0cbde874d1e5")
    finally:
        app.dependency_overrides.clear()
