"""
OAuth 2.0 PKCE service for capturing NetSuite refresh tokens.

Flow:
  1. start(account) -> generates code_verifier/challenge + state, stores a
     pkce_session row, returns the NetSuite authorize URL.
  2. handle_callback(state, code) -> exchanges the code for tokens, encrypts
     and saves refresh/access tokens onto the account row, deletes the session.
"""

import base64
import hashlib
import secrets
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.netsuite_account import NetSuiteAccount
from app.models.pkce_session import PkceSession
from app.utils.crypto import encrypt


def _gen_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


class PkceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _host(self, account_id: str) -> str:
        return account_id.replace("_", "-").lower()

    def _redirect_uri(self, account: NetSuiteAccount) -> str:
        if account.redirect_uri:
            return account.redirect_uri
        return f"{settings.pkce_redirect_base.rstrip('/')}/accounts/pkce/callback"

    async def start(self, account: NetSuiteAccount) -> tuple[str, str]:
        """Returns (auth_url, state)."""
        verifier, challenge = _gen_pkce()
        state = secrets.token_urlsafe(24)

        # Persist the PKCE session
        self.db.add(
            PkceSession(
                state=state,
                code_verifier=verifier,
                account_id=account.id,
            )
        )
        await self.db.commit()

        host = self._host(account.account_id)
        auth_url = (
            f"https://{host}.app.netsuite.com/app/login/oauth2/authorize.nl?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": account.client_id,
                    "redirect_uri": self._redirect_uri(account),
                    "scope": account.scope or "mcp",
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )
        return auth_url, state

    async def handle_callback(self, state: str, code: str) -> NetSuiteAccount:
        """Exchange the authorization code for tokens and store them."""
        # Look up the PKCE session
        sess_stmt = select(PkceSession).where(PkceSession.state == state)
        sess = (await self.db.execute(sess_stmt)).scalar_one_or_none()
        if not sess:
            raise ValueError("Invalid or expired PKCE state.")

        acc_stmt = select(NetSuiteAccount).where(NetSuiteAccount.id == sess.account_id)
        account = (await self.db.execute(acc_stmt)).scalar_one_or_none()
        if not account:
            raise ValueError("Account not found for PKCE session.")

        host = self._host(account.account_id)
        token_url = (
            f"https://{host}.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token"
        )

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri(account),
                    "client_id": account.client_id,
                    "code_verifier": sess.code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code != 200:
            raise ValueError(f"Token exchange failed (HTTP {resp.status_code}): {resp.text}")

        tokens = resp.json()
        expires_in = int(tokens.get("expires_in", 3600))
        account.refresh_token = encrypt(tokens["refresh_token"])
        account.access_token = encrypt(tokens.get("access_token"))
        account.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Clean up the PKCE session
        await self.db.execute(delete(PkceSession).where(PkceSession.state == state))
        await self.db.commit()
        await self.db.refresh(account)
        return account
