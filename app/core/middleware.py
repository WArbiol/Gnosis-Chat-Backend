from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.schemas.user import PlanEnum, PlanLimits


class QuotaMiddleware(BaseHTTPMiddleware):
    """Validates chamber_level access and plan quota before RAG operations."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Note: In FastAPI, middleware runs before routing dependencies,
        # so we don't have access to `Depends(get_current_user)` here directly.
        # For simplicity in this MVP, we'll let the endpoint dependencies handle auth,
        # and we can enforce quotas inside the specific endpoint or via a dependency.
        
        # We will keep this middleware as a pass-through for now, and implement 
        # `check_plan_quota` and `check_chamber_access` directly in the endpoints
        # that need them (e.g. the `/ask` endpoint).
        return await call_next(request)


def check_chamber_access(user_chamber_level: int, required_level: int) -> None:
    """Raise 403 if user doesn't have required chamber level."""
    if user_chamber_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: insufficient chamber level",
        )


def check_plan_quota(plan: PlanEnum, current_usage: int) -> None:
    """Raise 429 if user exceeded their plan's question quota."""
    limit = PlanLimits.get_question_limit(plan)
    if current_usage >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Question limit reached ({limit}) for plan '{plan.value}'",
        )
