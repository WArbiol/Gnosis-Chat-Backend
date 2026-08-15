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
async def test_invalid_jwt_token_returns_401(client: AsyncClient):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.string"}
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_valid_jwt_token_decodes_correctly(client: AsyncClient):
    import jwt
    from app.core.config import settings

    secret = "test-jwt-secret-key-12345678901234567890"
    original_secret = settings.supabase_jwt_secret
    original_env = settings.app_env
    
    settings.supabase_jwt_secret = secret
    settings.app_env = "production"
    
    user_uuid = "11111111-2222-3333-4444-555555555555"
    user_email = "jwt_test@gnosis.chat"
    
    try:
        payload = {
            "sub": user_uuid,
            "email": user_email,
            "aud": "authenticated",
            "iss": f"{settings.supabase_url}/auth/v1" if settings.supabase_url else "http://test/auth/v1"
        }
        token = jwt.encode(payload, secret, algorithm="HS256")
        
        mock_profile = UserProfile(
            id=user_uuid,
            email=user_email,
            plan=PlanEnum.FREE
        )
        
        with patch("app.core.security._get_or_create_profile", return_value=mock_profile), \
             patch("app.services.auth_service.get_user_profile", return_value=mock_profile):
            
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == user_uuid
            assert data["email"] == user_email
    finally:
        settings.supabase_jwt_secret = original_secret
        settings.app_env = original_env

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


@pytest.mark.asyncio
async def test_delete_account_unauthenticated(client: AsyncClient):
    response = await client.post("/api/v1/auth/delete-account")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_account_authenticated(client: AsyncClient, mock_user):
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("app.services.auth_service.delete_user_account", return_value={"status": "success", "message": "Conta e dados excluídos com sucesso."}):
        response = await client.post("/api/v1/auth/delete-account")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    app.dependency_overrides.clear()
