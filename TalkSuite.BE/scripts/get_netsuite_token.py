"""
One-time script to obtain a NetSuite OAuth 2.0 refresh token.

Uses plain Authorization Code flow (no PKCE) for confidential clients.

Usage:
    python scripts/get_netsuite_token.py

Prerequisites:
- Integration Record in NetSuite with:
  - Authorization Code Grant enabled
  - Scope: NetSuite AI Connector Service ONLY
  - Redirect URI: http://localhost:9876/callback
  - Public Client: unchecked (confidential client)
"""

import os
import re
import secrets
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

import httpx

# =============================================================================
# Load from environment variables — NEVER hardcode secrets here.
NETSUITE_ACCOUNT_ID = os.environ["NETSUITE_ACCOUNT_ID"]
CLIENT_ID = os.environ["NETSUITE_CLIENT_ID"]
CLIENT_SECRET = os.environ["NETSUITE_CLIENT_SECRET"]
REDIRECT_URI = os.environ.get("NETSUITE_REDIRECT_URI", "http://localhost:9876/callback")
SCOPE = os.environ.get("NETSUITE_SCOPE", "NetSuiteAIConnectorService")

AUTHORIZE_URL = f"https://{NETSUITE_ACCOUNT_ID}.app.netsuite.com/app/login/oauth2/authorize.nl"
TOKEN_URL = f"https://{NETSUITE_ACCOUNT_ID}.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token"
# =============================================================================


def _write_refresh_token_to_env(token: str):
    env_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    with open(env_path, "r") as f:
        content = f.read()
    if re.search(r"^NETSUITE_REFRESH_TOKEN=", content, re.MULTILINE):
        content = re.sub(
            r"^NETSUITE_REFRESH_TOKEN=.*$",
            f"NETSUITE_REFRESH_TOKEN={token}",
            content,
            flags=re.MULTILINE,
        )
    else:
        content += f"\nNETSUITE_REFRESH_TOKEN={token}\n"
    with open(env_path, "w") as f:
        f.write(content)
    print(f"  Refresh token written to {env_path}")


def build_auth_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str) -> dict | None:
    with httpx.Client(timeout=30) as client:
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(CLIENT_ID, CLIENT_SECRET),
        )
    if response.status_code != 200:
        print(f"\nToken exchange failed (HTTP {response.status_code}):")
        print(response.text)
        return None
    return response.json()


class CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None
    received_state = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/callback":
            CallbackHandler.auth_code = params.get("code", [None])[0]
            CallbackHandler.received_state = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization successful!</h1>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    print("=" * 60)
    print("  NetSuite OAuth 2.0 — Refresh Token Generator")
    print("=" * 60)
    print(f"  Account:  {NETSUITE_ACCOUNT_ID}")
    print(f"  ClientID: {CLIENT_ID[:20]}...")
    print(f"  Scope:    {SCOPE}")
    print()

    state = secrets.token_urlsafe(32)
    auth_url = build_auth_url(state)

    server = HTTPServer(("localhost", 9876), CallbackHandler)
    server_thread = Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print("Opening browser for NetSuite authorization...")
    print(f"  If it doesn't open, navigate to:\n\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for authorization callback...")
    server_thread.join(timeout=120)
    server.server_close()

    if not CallbackHandler.auth_code:
        print("\nNo authorization code received. Timed out or user denied.")
        return

    if CallbackHandler.received_state != state:
        print("\nState mismatch!")
        return

    print("\nAuthorization code received! Exchanging for tokens...")
    tokens = exchange_code(CallbackHandler.auth_code)

    if not tokens:
        return

    refresh_token = tokens.get("refresh_token", "")

    print("\n" + "=" * 60)
    print("  SUCCESS — Tokens obtained!")
    print("=" * 60)
    print(f"  Access Token:  {tokens.get('access_token', '')[:40]}...")
    print(f"  Expires In:    {tokens.get('expires_in', '')} seconds")
    print(f"  Refresh Token: {refresh_token[:40]}...")
    print()

    if refresh_token:
        _write_refresh_token_to_env(refresh_token)
    else:
        print("  WARNING: No refresh token returned!")


if __name__ == "__main__":
    main()
