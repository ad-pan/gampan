"""Browser-PKCE and device-code OAuth flows. Persists refresh tokens to OS keychain."""

from __future__ import annotations

import json
import urllib.request

import keyring
from google_auth_oauthlib.flow import Flow

# OAuth client registered for gampan; client_secret is "shared" per RFC 8252.
_CLIENT_CONFIG = {
    "installed": {
        "client_id": "REPLACE_AT_RELEASE.apps.googleusercontent.com",
        "client_secret": "REPLACE_AT_RELEASE",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://127.0.0.1"],
    }
}
_SCOPES = ["https://www.googleapis.com/auth/dfp"]  # Google Ad Manager
_KEYCHAIN_SERVICE = "gampan"
_KEYCHAIN_USER = "default"


def browser_login() -> tuple[str, str]:
    """Run PKCE flow via local HTTP server; return (email, refresh_token)."""
    flow = Flow.from_client_config(_CLIENT_CONFIG, scopes=_SCOPES)
    flow.run_local_server(port=0, prompt="consent", access_type="offline")
    creds = flow.credentials
    # ID token (when present) carries email; for v0.1 use userinfo endpoint as fallback
    email = _fetch_email(creds.token)
    return email, creds.refresh_token


def device_code_login() -> tuple[str, str]:
    """Placeholder for device-code flow (not yet implemented)."""
    # google-auth-oauthlib does not implement device flow directly; v0.1 surfaces a TODO
    raise NotImplementedError("device-code flow lands in v0.1.1; use `gampan auth login` for now")


def _fetch_email(access_token: str) -> str:
    """Fetch authenticated user's email from Google userinfo endpoint."""
    req = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return str(data["email"])


def store_credentials(email: str, refresh_token: str) -> None:
    """JSON-encode email + refresh_token and write to OS keychain."""
    keyring.set_password(
        _KEYCHAIN_SERVICE,
        _KEYCHAIN_USER,
        json.dumps({"email": email, "refresh_token": refresh_token}),
    )


def load_credentials() -> dict[str, str] | None:
    """Load credentials from OS keychain; return None if not set."""
    raw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USER)
    if not raw:
        return None
    return json.loads(raw)  # type: ignore[no-any-return]


def clear_credentials() -> None:
    """Delete stored credentials from OS keychain."""
    keyring.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USER)
