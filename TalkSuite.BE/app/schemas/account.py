from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AccountCreate(BaseModel):
    name: str
    account_id: str
    client_id: str
    client_secret: str | None = None
    mcp_url: str | None = None
    redirect_uri: str | None = None
    scope: str = "mcp"


class AccountUpdate(BaseModel):
    name: str | None = None
    account_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    mcp_url: str | None = None
    redirect_uri: str | None = None
    scope: str | None = None


class AccountResponse(BaseModel):
    id: UUID
    name: str
    account_id: str
    client_id: str
    mcp_url: str | None = None
    scope: str
    is_active: bool
    connected: bool = False  # whether a refresh token is present
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountSummary(BaseModel):
    """Lightweight account info returned to end users (no secrets)."""

    id: UUID
    name: str
    account_id: str

    model_config = {"from_attributes": True}


class PkceStartResponse(BaseModel):
    auth_url: str
    state: str
