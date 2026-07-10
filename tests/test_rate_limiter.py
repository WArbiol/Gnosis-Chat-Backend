import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from app.core.exceptions import register_exception_handlers


@pytest.mark.asyncio
async def test_rate_limiter_triggers_429():
    """
    Tests that the RateLimitExceeded exception handler correctly formats
    the response with HTTP 429 and the custom Portuguese message.
    """
    # Create an isolated FastAPI instance
    test_app = FastAPI()
    
    # Create a limiter with a strict limit of 1 request per minute
    test_limiter = Limiter(key_func=get_remote_address, default_limits=["1/minute"])
    test_app.state.limiter = test_limiter
    test_app.add_middleware(SlowAPIMiddleware)
    
    # Register exception handlers (including RateLimitExceeded)
    register_exception_handlers(test_app)
    
    @test_app.get("/test-limited")
    async def test_limited(request: Request):
        return {"status": "ok"}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First request should succeed
        resp1 = await client.get("/test-limited")
        assert resp1.status_code == 200
        assert resp1.json() == {"status": "ok"}
        
        # Second request within the same minute should be rate limited (429)
        resp2 = await client.get("/test-limited")
        assert resp2.status_code == 429
        
        data = resp2.json()
        assert data["code"] == "TOO_MANY_REQUESTS"
        assert "Muitas requisições" in data["message"]
