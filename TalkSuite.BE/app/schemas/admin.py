from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.account import AccountSummary


class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    role: str = "viewer"
    account_ids: list[UUID] = []  # at least one required (validated in API)


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    created_at: datetime
    accounts: list[AccountSummary] = []

    model_config = {"from_attributes": True}


class AssignAccountsRequest(BaseModel):
    account_ids: list[UUID]


class UpdateUserRoleRequest(BaseModel):
    role: str


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    password: str | None = None
    account_ids: list[UUID] | None = None
