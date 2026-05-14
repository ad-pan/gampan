"""Unit tests for gampan.gam.oauth keychain helpers and client-config loading."""

import json
import os
from unittest.mock import patch

import pytest

from gampan.core.errors import AuthError
from gampan.gam.oauth import _DEFAULT_CLIENT_ID, _load_client_config, store_credentials


def test_store_credentials_writes_keychain() -> None:
    with patch("gampan.gam.oauth.keyring") as kr:
        store_credentials(email="user@example.com", refresh_token="rt-abc")
        kr.set_password.assert_called_once()
        args = kr.set_password.call_args.args
        assert args[0] == "gampan"
        payload = json.loads(args[2])
        assert payload["email"] == "user@example.com"
        assert payload["refresh_token"] == "rt-abc"


def test_clear_credentials_deletes_keychain() -> None:
    from gampan.gam.oauth import clear_credentials

    with patch("gampan.gam.oauth.keyring") as kr:
        clear_credentials()
        kr.delete_password.assert_called_once_with("gampan", "default")


def test_load_client_config_raises_when_placeholders_unfilled() -> None:
    """AuthError fires when defaults are still placeholders and no env vars set."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("GAMPAN_OAUTH_CLIENT_ID", "GAMPAN_OAUTH_CLIENT_SECRET")
    }
    with (
        patch.dict(os.environ, env, clear=True),
        pytest.raises(AuthError, match="oauth-client-setup.md"),
    ):
        _load_client_config()


def test_load_client_config_uses_env_when_set() -> None:
    """Env vars take precedence over the baked-in defaults."""
    overrides = {
        "GAMPAN_OAUTH_CLIENT_ID": "real-client-id.apps.googleusercontent.com",
        "GAMPAN_OAUTH_CLIENT_SECRET": "real-secret",
    }
    with patch.dict(os.environ, overrides):
        config = _load_client_config()
    assert config["installed"]["client_id"] == "real-client-id.apps.googleusercontent.com"
    assert config["installed"]["client_secret"] == "real-secret"
    assert config["installed"]["auth_uri"] == "https://accounts.google.com/o/oauth2/auth"


def test_load_client_config_raises_only_when_client_id_is_placeholder() -> None:
    """Confirming the guard checks client_id specifically (not client_secret)."""
    # If client_id is set via env but client_secret is not, it should NOT raise —
    # the secret will fall back to the placeholder value but the client_id check passes.
    overrides = {
        "GAMPAN_OAUTH_CLIENT_ID": "my-registered-id.apps.googleusercontent.com",
    }
    env = {k: v for k, v in os.environ.items() if k != "GAMPAN_OAUTH_CLIENT_SECRET"}
    env.update(overrides)
    with patch.dict(os.environ, env, clear=True):
        config = _load_client_config()  # should not raise
    assert config["installed"]["client_id"] == "my-registered-id.apps.googleusercontent.com"


def test_default_client_id_sentinel_value() -> None:
    """Ensure the placeholder constant stays recognisable for the guard check."""
    assert _DEFAULT_CLIENT_ID == "TODO_REGISTER_OAUTH_CLIENT.apps.googleusercontent.com"
