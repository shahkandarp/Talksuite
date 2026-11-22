"""Service for NetSuite account CRUD and user assignment."""

from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.netsuite_account import NetSuiteAccount
from app.models.user_account_map import UserAccountMap
from app.utils.crypto import encrypt


class AccountService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        name: str,
        account_id: str,
        client_id: str,
        client_secret: str | None,
        mcp_url: str | None,
        redirect_uri: str | None,
        scope: str = "mcp",
    ) -> NetSuiteAccount:
        account = NetSuiteAccount(
            name=name,
            account_id=account_id,
            client_id=client_id,
            client_secret=encrypt(client_secret),
            mcp_url=mcp_url,
            redirect_uri=redirect_uri,
            scope=scope,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def get(self, account_uuid: UUID) -> NetSuiteAccount | None:
        stmt = select(NetSuiteAccount).where(NetSuiteAccount.id == account_uuid)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(
        self,
        account_uuid: UUID,
        name: str | None = None,
        account_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        mcp_url: str | None = None,
        redirect_uri: str | None = None,
        scope: str | None = None,
    ) -> tuple[NetSuiteAccount | None, bool]:
        """
        Update an account. Returns (account, creds_changed).
        creds_changed is True if account_id or client_id changed — in that case
        the stored tokens are cleared (a reconnect is required).
        """
        account = await self.get(account_uuid)
        if not account:
            return None, False

        creds_changed = False
        if name is not None and name.strip():
            account.name = name.strip()
        if account_id is not None and account_id.strip() and account_id != account.account_id:
            account.account_id = account_id.strip()
            creds_changed = True
        if client_id is not None and client_id.strip() and client_id != account.client_id:
            account.client_id = client_id.strip()
            creds_changed = True
        if client_secret is not None and client_secret.strip():
            account.client_secret = encrypt(client_secret)
        if mcp_url is not None:
            account.mcp_url = mcp_url.strip() or None
        if redirect_uri is not None:
            account.redirect_uri = redirect_uri.strip() or None
        if scope is not None and scope.strip():
            account.scope = scope.strip()

        # If the identity changed, the old refresh token is no longer valid
        if creds_changed:
            account.refresh_token = None
            account.access_token = None
            account.token_expiry = None

        await self.db.commit()
        await self.db.refresh(account)
        return account, creds_changed

    async def list_all(self) -> list[NetSuiteAccount]:
        stmt = select(NetSuiteAccount).order_by(NetSuiteAccount.created_at)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_user(self, user_id: UUID) -> list[NetSuiteAccount]:
        stmt = (
            select(NetSuiteAccount)
            .join(UserAccountMap, UserAccountMap.account_id == NetSuiteAccount.id)
            .where(
                UserAccountMap.user_id == user_id,
                NetSuiteAccount.is_active.is_(True),
            )
            .order_by(NetSuiteAccount.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def user_has_account(self, user_id: UUID, account_uuid: UUID) -> bool:
        stmt = select(UserAccountMap).where(
            UserAccountMap.user_id == user_id,
            UserAccountMap.account_id == account_uuid,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def assign_accounts(self, user_id: UUID, account_ids: list[UUID]) -> None:
        """Replace the set of accounts assigned to a user."""
        await self.db.execute(
            delete(UserAccountMap).where(UserAccountMap.user_id == user_id)
        )
        for acc_id in account_ids:
            self.db.add(UserAccountMap(user_id=user_id, account_id=acc_id))
        await self.db.commit()

    async def add_accounts(self, user_id: UUID, account_ids: list[UUID]) -> None:
        """Add accounts to a user without removing existing assignments."""
        existing = await self.list_for_user(user_id)
        existing_ids = {a.id for a in existing}
        for acc_id in account_ids:
            if acc_id not in existing_ids:
                self.db.add(UserAccountMap(user_id=user_id, account_id=acc_id))
        await self.db.commit()
