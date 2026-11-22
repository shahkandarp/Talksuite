"""Account endpoints — list my accounts + PKCE auth flow."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, require_admin
from app.models.database import get_db_session
from app.models.user import User
from app.schemas.account import AccountSummary, PkceStartResponse
from app.services.account_service import AccountService
from app.services.pkce_service import PkceService

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=list[AccountSummary])
async def my_accounts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List the NetSuite accounts assigned to the current user."""
    account_service = AccountService(db)
    accounts = await account_service.list_for_user(user.id)
    return [AccountSummary.model_validate(a) for a in accounts]


@router.post("/{account_id}/pkce/start", response_model=PkceStartResponse)
async def pkce_start(
    account_id: UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Begin the PKCE flow for an account — returns the NetSuite authorize URL."""
    account_service = AccountService(db)
    account = await account_service.get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    pkce = PkceService(db)
    auth_url, state = await pkce.start(account)
    return PkceStartResponse(auth_url=auth_url, state=state)


@router.get("/pkce/callback", response_class=HTMLResponse)
async def pkce_callback(
    state: str = "",
    code: str = "",
    db: AsyncSession = Depends(get_db_session),
):
    """
    NetSuite redirects here after login. Exchanges the code for tokens and
    saves them to the account. Returns a small HTML page that closes the popup.
    """
    if not state or not code:
        return HTMLResponse(
            "<h3>TalkSuite: missing code or state. You can close this window.</h3>",
            status_code=400,
        )

    pkce = PkceService(db)
    try:
        account = await pkce.handle_callback(state, code)
    except ValueError as e:
        return HTMLResponse(f"<h3>TalkSuite: connection failed — {e}</h3>", status_code=400)

    # Invalidate any cached MCP client so it reconnects with new tokens
    try:
        from app.main import mcp_manager
        await mcp_manager.invalidate(str(account.id))
    except Exception:
        pass

    return HTMLResponse(
        f"""
        <html><body style="font-family:sans-serif;text-align:center;padding:40px">
        <h2 style="color:#004851">✓ {account.name} connected</h2>
        <p>NetSuite account <b>{account.account_id}</b> is now linked to TalkSuite.</p>
        <p>You can close this window and return to the app.</p>
        <script>setTimeout(function(){{ window.close(); }}, 2000);</script>
        </body></html>
        """
    )
