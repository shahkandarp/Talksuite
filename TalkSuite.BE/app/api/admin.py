"""Admin endpoints — user management, account management, assignment.

All routes require the admin role.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import require_admin
from app.models.database import get_db_session
from app.models.user import User
from app.schemas.account import AccountCreate, AccountResponse, AccountSummary, AccountUpdate
from app.schemas.admin import (
    UserCreate,
    UserResponse,
    AssignAccountsRequest,
    UpdateUserRoleRequest,
    UserUpdate,
)
from app.services.account_service import AccountService
from app.services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["admin"])


async def _user_to_response(
    user: User, account_service: AccountService
) -> UserResponse:
    accounts = await account_service.list_for_user(user.id)
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        created_at=user.created_at,
        accounts=[AccountSummary.model_validate(a) for a in accounts],
    )


# ─── Users ─────────────────────────────────────────────────────────────────

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    if not body.account_ids:
        raise HTTPException(
            status_code=400, detail="At least one account must be assigned to the user."
        )

    user_service = UserService(db)
    account_service = AccountService(db)

    if await user_service.get_by_email(body.email):
        raise HTTPException(status_code=409, detail="A user with this email already exists.")

    # Validate the account IDs exist
    for acc_id in body.account_ids:
        if not await account_service.get(acc_id):
            raise HTTPException(status_code=400, detail=f"Account {acc_id} not found.")

    user = await user_service.create(body.email, body.name, body.password, body.role)
    await account_service.assign_accounts(user.id, body.account_ids)
    return await _user_to_response(user, account_service)


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    user_service = UserService(db)
    account_service = AccountService(db)
    users = await user_service.list_all()
    return [await _user_to_response(u, account_service) for u in users]


@router.put("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: UUID,
    body: UpdateUserRoleRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    user_service = UserService(db)
    account_service = AccountService(db)
    user = await user_service.update_role(user_id, body.role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return await _user_to_response(user, account_service)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Update a user's name, role, password, and/or account assignments."""
    user_service = UserService(db)
    account_service = AccountService(db)

    user = await user_service.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Update basic fields
    if body.name is not None or body.role is not None or body.password is not None:
        user = await user_service.update(
            user_id, name=body.name, role=body.role, password=body.password
        )

    # Update account assignments (must keep at least one)
    if body.account_ids is not None:
        if not body.account_ids:
            raise HTTPException(
                status_code=400, detail="At least one account must remain assigned."
            )
        for acc_id in body.account_ids:
            if not await account_service.get(acc_id):
                raise HTTPException(status_code=400, detail=f"Account {acc_id} not found.")
        await account_service.assign_accounts(user_id, body.account_ids)

    return await _user_to_response(user, account_service)


@router.put("/users/{user_id}/accounts", response_model=UserResponse)
async def assign_user_accounts(
    user_id: UUID,
    body: AssignAccountsRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    if not body.account_ids:
        raise HTTPException(status_code=400, detail="At least one account is required.")
    user_service = UserService(db)
    account_service = AccountService(db)
    user = await user_service.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    await account_service.assign_accounts(user_id, body.account_ids)
    return await _user_to_response(user, account_service)


# ─── Accounts ──────────────────────────────────────────────────────────────

@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    account_service = AccountService(db)
    account = await account_service.create(
        name=body.name,
        account_id=body.account_id,
        client_id=body.client_id,
        client_secret=body.client_secret,
        mcp_url=body.mcp_url,
        redirect_uri=body.redirect_uri,
        scope=body.scope,
    )
    return AccountResponse(
        id=account.id,
        name=account.name,
        account_id=account.account_id,
        client_id=account.client_id,
        mcp_url=account.mcp_url,
        scope=account.scope,
        is_active=account.is_active,
        connected=bool(account.refresh_token),
        created_at=account.created_at,
    )


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    account_service = AccountService(db)
    accounts = await account_service.list_all()
    return [
        AccountResponse(
            id=a.id,
            name=a.name,
            account_id=a.account_id,
            client_id=a.client_id,
            mcp_url=a.mcp_url,
            scope=a.scope,
            is_active=a.is_active,
            connected=bool(a.refresh_token),
            created_at=a.created_at,
        )
        for a in accounts
    ]


@router.put("/accounts/{account_uuid}", response_model=AccountResponse)
async def update_account(
    account_uuid: UUID,
    body: AccountUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    account_service = AccountService(db)
    account, creds_changed = await account_service.update(
        account_uuid,
        name=body.name,
        account_id=body.account_id,
        client_id=body.client_id,
        client_secret=body.client_secret,
        mcp_url=body.mcp_url,
        redirect_uri=body.redirect_uri,
        scope=body.scope,
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    # Drop any cached MCP client so it rebuilds with the new config
    try:
        from app.main import mcp_manager
        await mcp_manager.invalidate(str(account.id))
    except Exception:
        pass

    return AccountResponse(
        id=account.id,
        name=account.name,
        account_id=account.account_id,
        client_id=account.client_id,
        mcp_url=account.mcp_url,
        scope=account.scope,
        is_active=account.is_active,
        connected=bool(account.refresh_token),
        created_at=account.created_at,
    )
