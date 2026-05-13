"""Unit tests for gampan.gam.oauth keychain helpers."""

import json
from unittest.mock import patch

from gampan.gam.oauth import store_credentials


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
