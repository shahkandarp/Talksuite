"""
MCP Manager — maintains a cache of per-account MCPClient instances.

Given a NetSuiteAccount row, returns a connected MCPClient. Token refreshes
are persisted back to the DB (encrypted) via a callback.
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from app.clients.mcp_client import MCPClient
from app.models.database import async_session_factory
from app.models.netsuite_account import NetSuiteAccount
from app.utils.crypto import encrypt, decrypt
from sqlalchemy import update


class MCPManager:
    """Caches MCPClient instances keyed by account UUID."""

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _make_persist_callback(self, account_uuid: UUID):
        async def _persist(access_token: str, refresh_token: str, expires_in: int):
            from time import time
            expiry = datetime.fromtimestamp(time() + expires_in, tz=timezone.utc)
            async with async_session_factory() as session:
                await session.execute(
                    update(NetSuiteAccount)
                    .where(NetSuiteAccount.id == account_uuid)
                    .values(
                        access_token=encrypt(access_token),
                        refresh_token=encrypt(refresh_token),
                        token_expiry=expiry,
                    )
                )
                await session.commit()

        return _persist

    async def get_client(self, account: NetSuiteAccount) -> MCPClient:
        """Return a connected MCPClient for the given account (cached)."""
        key = str(account.id)
        async with self._lock_for(key):
            existing = self._clients.get(key)
            if existing and existing.is_connected:
                return existing

            refresh_token = decrypt(account.refresh_token)
            access_token = decrypt(account.access_token)
            expiry_epoch = (
                account.token_expiry.timestamp() if account.token_expiry else 0
            )

            client = MCPClient(
                account_id=account.account_id,
                client_id=account.client_id,
                mcp_url=account.mcp_url or "",
                refresh_token=refresh_token or "",
                access_token=access_token,
                token_expiry_epoch=expiry_epoch,
                on_tokens_updated=self._make_persist_callback(account.id),
            )
            await client.initialize()
            self._clients[key] = client
            return client

    async def invalidate(self, account_id: str):
        """Drop a cached client (e.g., after re-auth)."""
        client = self._clients.pop(account_id, None)
        if client:
            await client.close()

    async def close_all(self):
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
