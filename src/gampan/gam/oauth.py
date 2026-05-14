"""Browser-PKCE and device-code OAuth flows. Persists refresh tokens to OS keychain."""

from __future__ import annotations

import json
import os
import urllib.request

import keyring
from google_auth_oauthlib.flow import Flow

from gampan.core.errors import AuthError

_SCOPES = ["https://www.googleapis.com/auth/dfp"]  # Google Ad Manager
_KEYCHAIN_SERVICE = "gampan"
_KEYCHAIN_USER = "default"


def _load_client_config() -> dict:  # type: ignore[type-arg]
    """Build OAuth client config from environment variables.

    Reads ``GAMPAN_OAUTH_CLIENT_ID`` and ``GAMPAN_OAUTH_CLIENT_SECRET``.
    Raises :class:`~gampan.core.errors.AuthError` with setup instructions when
    either variable is absent.
    """
    client_id = os.environ.get("GAMPAN_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GAMPAN_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        missing = []
        if not client_id:
            missing.append("GAMPAN_OAUTH_CLIENT_ID")
        if not client_secret:
            missing.append("GAMPAN_OAUTH_CLIENT_SECRET")
        raise AuthError(
            f"Missing environment variable(s): {', '.join(missing)}.\n"
            "To authenticate with gampan you must register a Google OAuth client "
            "and export its credentials before running `gampan auth login`.\n"
            "See https://github.com/ad-pan/gampan/blob/main/docs/oauth-setup.md "
            "for step-by-step instructions."
        )
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://127.0.0.1"],
        }
    }


def browser_login() -> tuple[str, str]:
    """Run PKCE flow via local HTTP server; return (email, refresh_token)."""
    client_config = _load_client_config()
    flow = Flow.from_client_config(client_config, scopes=_SCOPES)
    flow.run_local_server(port=0, prompt="consent", access_type="offline")
    creds = flow.credentials
    # ID token (when present) carries email; for v0.1 use userinfo endpoint as fallback
    email = _fetch_email(creds.token)
    return email, creds.refresh_token


def device_code_login() -> tuple[str, str]:
    """Placeholder for device-code flow (not yet implemented)."""
    _load_client_config()  # validate env vars eagerly before attempting the flow
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
