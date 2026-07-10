import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from app.main import app
from app.core.security import get_current_user
from app.schemas.user import UserProfile, PlanEnum

@pytest.mark.asyncio
async def test_verify_second_chamber_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/auth/second-chamber/verify", json={"passcode": "Paz Inverencial"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_verify_second_chamber_incorrect(client: AsyncClient, mock_user):
    # Override authentication dependency
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Mock the LLM to return invalid
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = AsyncMock()
    mock_llm.generate_json.return_value.valid = False
    mock_llm.generate_json.return_value.reason = "Não corresponde à saudação."

    with patch("app.agents.nodes.utils.get_llm", return_value=mock_llm):
        response = await client.post(
            "/api/v1/auth/second-chamber/verify", 
            json={"passcode": "errado"}
        )
        
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "Passe incorreto. Tente novamente." in data["reason"]

    # Clean up overrides
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_verify_second_chamber_correct(client: AsyncClient, mock_user):
    # Override authentication dependency
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Mock LLM to return valid
    mock_llm = AsyncMock()
    mock_llm.generate_json.return_value = AsyncMock()
    mock_llm.generate_json.return_value.valid = True
    mock_llm.generate_json.return_value.reason = "Correto."

    # Mock Supabase update and get_user_profile
    from unittest.mock import MagicMock
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    
    updated_profile = UserProfile(
        id=mock_user.id,
        email=mock_user.email,
        plan=mock_user.plan,
        chamber_level=2,
        question_count=0
    )

    with patch("app.agents.nodes.utils.get_llm", return_value=mock_llm), \
         patch("app.core.dependencies.get_supabase_client", return_value=mock_supabase), \
         patch("app.services.auth_service.get_user_profile", return_value=updated_profile):
         
        response = await client.post(
            "/api/v1/auth/second-chamber/verify", 
            json={"passcode": "Paz Inverencial, Jachin Boaz"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["user"]["chamber_level"] == 2

    # Clean up overrides
    app.dependency_overrides.clear()
