"""
NetSuite Native MCP Client (per-account).

Connects to NetSuite's official MCP server using OAuth 2.0 PKCE tokens
(public client, scope=mcp). Each instance is bound to ONE NetSuite account.
Tokens live in memory and are persisted via an injected async callback
(so they can be written back to the DB encrypted).
"""

import asyncio
import json
import time
from typing import Any, Awaitable, Callable

import httpx


# Callback signature: (access_token, refresh_token, expires_in_seconds) -> awaitable
TokenPersistCallback = Callable[[str, str, int], Awaitable[None]]

# Tools whose results are stable enough to cache (metadata / listings).
# Data-returning tools (SuiteQL, records, reports) are NOT cached.
_CACHEABLE_TOOLS = {
    "ns_getSuiteQLMetadata",
    "ns_getRecordTypeMetadata",
    "ns_getSubsidiaries",
    "ns_getAccountingBooks",
    "ns_getAccountingContexts",
    "ns_getNexusIds",
    "ns_listAllReports",
    "ns_listSavedSearches",
}
_CACHE_TTL_SECONDS = 600  # 10 minutes


class MCPClient:
    """Client for NetSuite's native MCP server, bound to a single account."""

    def __init__(
        self,
        account_id: str,
        client_id: str,
        mcp_url: str,
        refresh_token: str,
        access_token: str | None = None,
        token_expiry_epoch: float = 0,
        on_tokens_updated: TokenPersistCallback | None = None,
    ):
        self.netsuite_account = account_id  # e.g. 661135_SB2
        self.client_id = client_id

        host = account_id.replace("_", "-").lower()
        self._token_url = (
            f"https://{host}.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token"
        )
        self._mcp_url = mcp_url or (
            f"https://{host}.suitetalk.api.netsuite.com/services/mcp/v1/all"
        )

        self._refresh_token = refresh_token
        self._access_token = access_token
        self._token_expiry = token_expiry_epoch
        self._on_tokens_updated = on_tokens_updated

        self._tools: list[dict[str, Any]] = []
        self._http_client: httpx.AsyncClient | None = None
        self._rpc_id = 0
        self._connected = False
        # cache: key -> (expiry_epoch, result_str)
        self._result_cache: dict[str, tuple[float, str]] = {}
        # Serializes token refreshes so concurrent tool calls don't each refresh
        # (NetSuite rotates the refresh token, so simultaneous refreshes break it).
        self._refresh_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def initialize(self):
        """Connect: refresh token + discover tools."""
        if not (self.netsuite_account and self.client_id and self._refresh_token):
            print("[TalkSuite] MCP client not configured (missing account creds)")
            return
        try:
            self._http_client = httpx.AsyncClient(timeout=90.0)
            await self._refresh_access_token()
            await self._discover_tools()
            self._connected = True
            print(
                f"[TalkSuite] MCP connected to {self.netsuite_account} "
                f"({len(self._tools)} tools)"
            )
        except Exception as e:
            print(f"[TalkSuite] MCP connect failed for {self.netsuite_account}: {e}")
            self._connected = False
            self._tools = []

    async def _refresh_access_token(self):
        resp = await self._http_client.post(
            self._token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self.client_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Token refresh failed (HTTP {resp.status_code}): {resp.text}"
            )
        data = resp.json()
        self._access_token = data["access_token"]
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._token_expiry = time.time() + expires_in
        # Persist back to DB
        if self._on_tokens_updated:
            try:
                await self._on_tokens_updated(
                    self._access_token, self._refresh_token, expires_in
                )
            except Exception as e:
                print(f"[TalkSuite] Token persist failed: {e}")

    async def _ensure_valid_token(self):
        """Refresh proactively if the access token is near expiry (serialized)."""
        if time.time() <= self._token_expiry - 60:
            return
        async with self._refresh_lock:
            # Re-check inside the lock — another coroutine may have just refreshed.
            if time.time() > self._token_expiry - 60:
                await self._refresh_access_token()

    async def _refresh_after_401(self, stale_access_token: str):
        """
        Refresh after a 401, but only once across concurrent callers.
        If another coroutine already refreshed (token changed), skip.
        """
        async with self._refresh_lock:
            if self._access_token == stale_access_token:
                await self._refresh_access_token()

    async def _rpc(self, method: str, params: dict) -> dict:
        await self._ensure_valid_token()
        self._rpc_id += 1
        token_used = self._access_token
        resp = await self._http_client.post(
            self._mcp_url,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": self._rpc_id},
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        if resp.status_code == 401:
            await self._refresh_after_401(token_used)
            self._rpc_id += 1
            resp = await self._http_client.post(
                self._mcp_url,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": self._rpc_id},
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
        if resp.status_code != 200:
            raise RuntimeError(f"MCP HTTP {resp.status_code}: {resp.text[:500]}")

        body = resp.text.strip()
        if body.startswith("event:") or body.startswith("data:") or "\ndata:" in body:
            for line in body.splitlines():
                if line.startswith("data:"):
                    body = line[5:].strip()
                    break
        data = json.loads(body)
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        return data.get("result", {})

    async def _discover_tools(self):
        result = await self._rpc("tools/list", {})
        self._tools = result.get("tools", [])

    async def get_tools(self) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        return [self._to_bedrock_format(t) for t in self._tools]

    async def execute_tool(self, tool_name: str, input_params: dict[str, Any]) -> str:
        if not self._connected:
            return f"Error: MCP server not connected. Cannot execute tool '{tool_name}'."

        # Serve from cache for idempotent metadata/listing tools
        cache_key = None
        if tool_name in _CACHEABLE_TOOLS:
            cache_key = f"{tool_name}:{json.dumps(input_params, sort_keys=True)}"
            cached = self._result_cache.get(cache_key)
            if cached and cached[0] > time.time():
                return cached[1]

        try:
            result = await self._rpc(
                "tools/call", {"name": tool_name, "arguments": input_params}
            )
            content = result.get("content", [])
            texts = [b["text"] for b in content if b.get("type") == "text"]
            output = "\n".join(texts) if texts else json.dumps(result)
            if cache_key:
                self._result_cache[cache_key] = (time.time() + _CACHE_TTL_SECONDS, output)
            return output
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

    def _to_bedrock_format(self, tool: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "inputSchema": {"json": tool.get("inputSchema", {})},
        }

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._connected = False
