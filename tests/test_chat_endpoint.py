import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient

from app.core.security import get_current_user
from app.main import app
from app.schemas.user import PlanEnum, UserProfile
from app.domain.exceptions import QuotaExceededException
from app.api.v1.conversations import get_conversation_service
from app.api.v1.chat import get_ask_rag_use_case


@pytest.mark.asyncio
async def test_ask_endpoint_unauthenticated(client: AsyncClient):
    """Calling /chat/ask without token should return 401 Unauthorized."""
    response = await client.post("/api/v1/chat/ask", json={"query": "O que é Gnosis?"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ask_endpoint_quota_exceeded(client: AsyncClient):
    """Calling /chat/ask when user reached quota limit should stream PAYMENT_REQUIRED error and clean up conversation."""
    over_quota_user = UserProfile(
        id="user-over-quota",
        email="user@test.com",
        plan=PlanEnum.FREE,
        chamber_level=1,
        question_count=3, # Free limit is 3
    )

    mock_conv_service = MagicMock()
    mock_conv = MagicMock()
    mock_conv.id = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    mock_conv.title = "Nova conversa"
    mock_conv.messages = []
    mock_conv_service.get_conversation.return_value = mock_conv

    mock_use_case = MagicMock()
    async def mock_execute(**kwargs):
        raise QuotaExceededException("Limite de 3 perguntas atingido.", code="LIMIT_EXCEEDED")
        yield {} # make it an async generator
    mock_use_case.execute = mock_execute

    app.dependency_overrides[get_current_user] = lambda: over_quota_user
    app.dependency_overrides[get_conversation_service] = lambda: mock_conv_service
    app.dependency_overrides[get_ask_rag_use_case] = lambda: mock_use_case

    try:
        response = await client.post(
            "/api/v1/chat/ask",
            json={"query": "Como meditar?", "conversation_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"}
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        
        # Verify SSE output contains PAYMENT_REQUIRED
        body = response.text
        assert "PAYMENT_REQUIRED" in body
        assert "Limite de 3 perguntas atingido" in body

        # Verify empty conversation was deleted
        mock_conv_service.delete_conversation.assert_called_once_with("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ask_endpoint_success_stream(client: AsyncClient, mock_user: UserProfile):
    """Calling /chat/ask with valid user and quota streams agent and token events."""
    mock_conv_service = MagicMock()
    mock_conv = MagicMock()
    mock_conv.id = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380b22"
    mock_conv.title = "Conversa existente"
    mock_conv.messages = ["msg1"]
    mock_conv_service.get_conversation.return_value = mock_conv

    mock_use_case = MagicMock()
    async def mock_execute(**kwargs):
        yield {"event": "status", "agent": "orchestrator", "message": "Analisando..."}
        yield {"event": "token", "token": "A "}
        yield {"event": "token", "token": "Gnosis "}
        yield {"event": "token", "token": "é sabedoria."}
    mock_use_case.execute = mock_execute

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_conversation_service] = lambda: mock_conv_service
    app.dependency_overrides[get_ask_rag_use_case] = lambda: mock_use_case

    try:
        response = await client.post(
            "/api/v1/chat/ask",
            json={"query": "O que é Gnosis?", "conversation_id": "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380b22"}
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        
        body = response.text
        assert "Analisando..." in body
        assert "A " in body
        assert "Gnosis " in body
    finally:
        app.dependency_overrides.clear()
