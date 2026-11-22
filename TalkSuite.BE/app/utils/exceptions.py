from fastapi import Request, status
from fastapi.responses import JSONResponse


class DatabaseUnavailableError(Exception):
    """Raised when the database connection is not available."""

    pass


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


async def database_unavailable_handler(
    request: Request, exc: DatabaseUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Service temporarily unavailable"},
    )


async def authentication_error_handler(
    request: Request, exc: AuthenticationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Authentication required"},
    )
