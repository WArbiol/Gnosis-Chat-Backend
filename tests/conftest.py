import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_user():
    """A mock UserProfile for testing authenticated routes."""
    from app.schemas.user import PlanEnum, UserProfile

    return UserProfile(
        id="test-user-123",
        email="test@gnosis.chat",
        plan=PlanEnum.BASIC,
        chamber_level=1,
        question_count=0,
    )
