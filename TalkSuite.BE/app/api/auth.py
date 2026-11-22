from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db_session
from app.services.auth_service import authenticate_user, create_access_token
from app.services.account_service import AccountService

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    accounts: list[dict]


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Authenticate with email + password, receive a JWT token and the list of
    NetSuite accounts assigned to the user.
    """
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )

    account_service = AccountService(db)
    accounts = await account_service.list_for_user(user.id)

    return LoginResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
        accounts=[
            {"id": str(a.id), "name": a.name, "account_id": a.account_id}
            for a in accounts
        ],
    )
