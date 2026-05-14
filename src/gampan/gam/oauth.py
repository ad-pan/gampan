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

# Baked-in OAuth client for `gampan`, registered under the `ad-pan` GCP project.
# Per RFC 8252 §8.5, installed-app client secrets are not actually secret — they
# ship in the source. Mainstream CLIs (gcloud, gh, firebase, rclone) follow the
# same pattern. Enterprise forks can override via GAMPAN_OAUTH_CLIENT_ID /
# GAMPAN_OAUTH_CLIENT_SECRET env vars.
_DEFAULT_CLIENT_ID = "834482691156-56qq3gl79pm709d46fi5oniudeed2eq3.apps.googleusercontent.com"
_DEFAULT_CLIENT_SECRET = "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"  # noqa: S105


def _load_client_config() -> dict:  # type: ignore[type-arg]
    """Build OAuth client config from env vars, falling back to baked-in defaults.

    Reads ``GAMPAN_OAUTH_CLIENT_ID`` (falling back to :data:`_DEFAULT_CLIENT_ID`)
    and ``GAMPAN_OAUTH_CLIENT_SECRET`` (falling back to :data:`_DEFAULT_CLIENT_SECRET`).

    Raises :class:`~gampan.core.errors.AuthError` when the resolved client_id is
    still the placeholder — i.e. the OAuth client has not yet been registered and no
    env-var override was provided.  Enterprise users can override via env vars without
    touching the source.
    """
    client_id = os.environ.get("GAMPAN_OAUTH_CLIENT_ID", _DEFAULT_CLIENT_ID)
    client_secret = os.environ.get("GAMPAN_OAUTH_CLIENT_SECRET", _DEFAULT_CLIENT_SECRET)
    if client_id.startswith("TODO_REGISTER_"):
        raise AuthError(
            "gampan's OAuth client has not been registered yet.\n"
            "Follow docs/oauth-client-setup.md to create a Google Cloud OAuth client\n"
            "and replace the _DEFAULT_CLIENT_ID / _DEFAULT_CLIENT_SECRET constants\n"
            "in src/gampan/gam/oauth.py (one-time commit).\n"
            "Enterprise users can also set GAMPAN_OAUTH_CLIENT_ID and\n"
            "GAMPAN_OAUTH_CLIENT_SECRET environment variables to skip source changes."
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
