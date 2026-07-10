from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.schemas.common import ErrorResponse


class GnosisException(Exception):
    """Base exception for gnosis-chat."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class QuotaExceededException(GnosisException):
    def __init__(self, plan: str, limit: int) -> None:
        super().__init__(
            message=f"Question limit reached ({limit}) for plan '{plan}'",
            code="QUOTA_EXCEEDED",
            status_code=429,
        )


class UnauthorizedException(GnosisException):
    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(message=detail, code="UNAUTHORIZED", status_code=401)


class ForbiddenException(GnosisException):
    def __init__(self, detail: str = "Access denied") -> None:
        super().__init__(message=detail, code="FORBIDDEN", status_code=403)


class NotFoundException(GnosisException):
    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(message=f"{resource} not found", code="NOT_FOUND", status_code=404)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(GnosisException)
    async def gnosis_exception_handler(request: Request, exc: GnosisException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                code="HTTP_ERROR",
                message=str(exc.detail),
            ).model_dump(),
        )

    @app.exception_handler(RateLimitExceeded)
    def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                code="TOO_MANY_REQUESTS",
                message="Muitas requisições. Por favor, aguarde um momento antes de enviar a próxima pergunta."
            ).model_dump(),
        )
