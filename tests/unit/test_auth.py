"""Tests for credential strategies, resolver chain, and to_google_credentials()."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gampan.core.errors import AuthError
from gampan.gam.auth import (
    Credentials,
    EnvServiceAccountStrategy,
    KeychainStrategy,
    resolve_credentials,
)

# ---------------------------------------------------------------------------
# Strategy: EnvServiceAccountStrategy
# ---------------------------------------------------------------------------


def test_env_strategy_returns_creds_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text(
        json.dumps({"type": "service_account", "client_email": "bot@x.iam.gserviceaccount.com"})
    )
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(sa))
    s = EnvServiceAccountStrategy()
    creds = s.try_load()
    assert creds is not None
    assert creds.principal == "bot@x.iam.gserviceaccount.com"
    assert creds._strategy == "env"
    assert creds._extra["sa_path"] == str(sa)


def test_env_strategy_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert EnvServiceAccountStrategy().try_load() is None


def test_resolver_raises_when_no_strategy_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(AuthError):
        resolve_credentials(strategies=[EnvServiceAccountStrategy()])


# ---------------------------------------------------------------------------
# Strategy: KeychainStrategy (now backed by credential_store)
# ---------------------------------------------------------------------------


def test_keychain_strategy_sets_strategy_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GAMPAN_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GAMPAN_OAUTH_CLIENT_SECRET", "csec")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GAMPAN_CRED_BACKEND", raising=False)

    # Pre-write credentials into the file backend so KeychainStrategy can load them.
    cred_file = tmp_path / "gampan" / "credentials.json"
    cred_file.parent.mkdir(parents=True, exist_ok=True)
    cred_file.write_text(json.dumps({"email": "user@example.com", "refresh_token": "rtoken123"}))

    creds = KeychainStrategy().try_load()
    assert creds is not None
    assert creds.principal == "user@example.com"
    assert creds._strategy == "keychain"
    assert creds._extra["refresh_token"] == "rtoken123"
    assert creds._extra["client_id"] == "cid"
    assert creds._extra["client_secret"] == "csec"


def test_keychain_strategy_returns_none_when_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GAMPAN_CRED_BACKEND", raising=False)
    assert KeychainStrategy().try_load() is None


def test_keychain_strategy_routes_to_keyring_when_backend_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GAMPAN_CRED_BACKEND=keychain routes credential_store to the keyring backend."""
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "keychain")
    monkeypatch.setenv("GAMPAN_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GAMPAN_OAUTH_CLIENT_SECRET", "csec")
    raw = json.dumps({"email": "user@example.com", "refresh_token": "rtoken123"})
    with patch("keyring.get_password", return_value=raw):
        creds = KeychainStrategy().try_load()
    assert creds is not None
    assert creds.principal == "user@example.com"
    assert creds._strategy == "keychain"
    assert creds._extra["refresh_token"] == "rtoken123"


# ---------------------------------------------------------------------------
# to_google_credentials() — one test per strategy path
# ---------------------------------------------------------------------------


def test_to_google_credentials_env_strategy(tmp_path: Path) -> None:
    """env path → google.oauth2.service_account.Credentials.from_service_account_file"""
    sa_path = str(tmp_path / "sa.json")
    creds = Credentials(
        principal="bot@x.iam.gserviceaccount.com",
        _token_provider=lambda: "",
        _strategy="env",
        _extra={"sa_path": sa_path},
    )
    mock_sa_creds = MagicMock()
    with patch(
        "gampan.gam.auth._google_service_account_credentials",
        return_value=mock_sa_creds,
    ) as mock_fn:
        result = creds.to_google_credentials()
    mock_fn.assert_called_once_with(sa_path)
    assert result is mock_sa_creds


def test_to_google_credentials_keychain_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    """keychain path → google.oauth2.credentials.Credentials with refresh token"""
    creds = Credentials(
        principal="user@example.com",
        _token_provider=lambda: "rtoken123",
        _strategy="keychain",
        _extra={
            "refresh_token": "rtoken123",
            "client_id": "cid",
            "client_secret": "csec",
        },
    )
    mock_oauth_creds = MagicMock()
    with patch(
        "gampan.gam.auth._google_oauth2_credentials",
        return_value=mock_oauth_creds,
    ) as mock_fn:
        result = creds.to_google_credentials()
    mock_fn.assert_called_once_with(
        token=None,
        refresh_token="rtoken123",
        client_id="cid",
        client_secret="csec",
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/admanager"],
    )
    assert result is mock_oauth_creds


def test_to_google_credentials_gcloud_strategy() -> None:
    """gcloud path → google.auth.default()"""
    creds = Credentials(
        principal="user@example.com",
        _token_provider=lambda: "tok",
        _strategy="gcloud",
        _extra={},
    )
    mock_adc_creds = MagicMock()
    with patch(
        "gampan.gam.auth._google_adc_credentials",
        return_value=mock_adc_creds,
    ) as mock_fn:
        result = creds.to_google_credentials()
    mock_fn.assert_called_once()
    assert result is mock_adc_creds
