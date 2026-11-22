from uuid import UUID

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import get_db_session
from app.models.user import User
from app.models.netsuite_account import NetSuiteAccount
from app.services.auth_service import decode_token

# HTTP Bearer scheme — extracts token from Authorization header
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Resolve the current user from the JWT token in the Authorization header.

    Raises 401 if token is missing, invalid, or expired.
    Raises 401 if user not found in database.
    """
    token = credentials.credentials

    # Decode and verify JWT
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load user from database
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    stmt = select(User).where(User.id == UUID(user_id))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Ensure the current user has the admin role."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return user


async def get_current_account(
    x_account_id: str | None = Header(default=None, alias="X-Account-Id"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> NetSuiteAccount:
    """
    Resolve the active NetSuite account from the X-Account-Id header.

    Verifies the user is assigned to that account. If no header is provided
    and the user has exactly one account, that account is used.
    """
    from app.services.account_service import AccountService

    account_service = AccountService(db)
    user_accounts = await account_service.list_for_user(user.id)

    if not user_accounts:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No NetSuite account assigned to your user.",
        )

    if x_account_id:
        try:
            target = UUID(x_account_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-Account-Id header.")
        for acc in user_accounts:
            if acc.id == target:
                return acc
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to the requested account.",
        )

    # No header → default to the only account (or the first if multiple)
    return user_accounts[0]
