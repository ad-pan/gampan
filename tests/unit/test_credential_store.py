"""Unit tests for gampan.gam.credential_store — file and keychain backends."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from gampan.gam import credential_store

# ---------------------------------------------------------------------------
# Helper: redirect XDG_CONFIG_HOME to a tmp directory
# ---------------------------------------------------------------------------


@pytest.fixture()
def file_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configure the file backend to write under *tmp_path* and return the expected path."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("GAMPAN_CRED_BACKEND", raising=False)
    return tmp_path / "gampan" / "credentials.json"


# ---------------------------------------------------------------------------
# _backend()
# ---------------------------------------------------------------------------


def test_backend_defaults_to_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GAMPAN_CRED_BACKEND", raising=False)
    assert credential_store._backend() == "file"


def test_backend_keychain_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "keychain")
    assert credential_store._backend() == "keychain"


def test_backend_keychain_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "KEYCHAIN")
    assert credential_store._backend() == "keychain"


def test_backend_unknown_value_defaults_to_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "something-else")
    assert credential_store._backend() == "file"


# ---------------------------------------------------------------------------
# _file_path()
# ---------------------------------------------------------------------------


def test_file_path_uses_xdg_config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert credential_store._file_path() == tmp_path / "gampan" / "credentials.json"


def test_file_path_falls_back_to_home_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = credential_store._file_path()
    assert path.parts[-3:] == (".config", "gampan", "credentials.json")


# ---------------------------------------------------------------------------
# File backend: round-trip save / load / clear
# ---------------------------------------------------------------------------


def test_save_and_load_round_trip(file_backend: Path) -> None:
    credential_store.save("alice@example.com", "my-refresh-token")
    result = credential_store.load()
    assert result == {"email": "alice@example.com", "refresh_token": "my-refresh-token"}


def test_save_creates_parent_dirs(file_backend: Path) -> None:
    assert not file_backend.parent.exists()
    credential_store.save("a@b.com", "rt")
    assert file_backend.parent.is_dir()


def test_save_sets_mode_0600(file_backend: Path) -> None:
    credential_store.save("a@b.com", "rt")
    file_mode = stat.S_IMODE(file_backend.stat().st_mode)
    assert file_mode == 0o600


def test_save_is_idempotent(file_backend: Path) -> None:
    credential_store.save("a@b.com", "rt1")
    credential_store.save("a@b.com", "rt2")
    result = credential_store.load()
    assert result is not None
    assert result["refresh_token"] == "rt2"


def test_atomic_write_no_tmp_file_left(file_backend: Path) -> None:
    """After a successful save, the .tmp sibling must not exist."""
    credential_store.save("a@b.com", "rt")
    tmp = file_backend.with_suffix(".tmp")
    assert not tmp.exists()


def test_load_returns_none_when_file_absent(file_backend: Path) -> None:
    assert credential_store.load() is None


def test_load_returns_none_on_corrupt_json(file_backend: Path) -> None:
    file_backend.parent.mkdir(parents=True, exist_ok=True)
    file_backend.write_text("not-valid-json")
    assert credential_store.load() is None


def test_clear_removes_file(file_backend: Path) -> None:
    credential_store.save("a@b.com", "rt")
    assert file_backend.exists()
    credential_store.clear()
    assert not file_backend.exists()


def test_clear_is_idempotent_when_absent(file_backend: Path) -> None:
    # Should not raise even if the file does not exist.
    credential_store.clear()
    credential_store.clear()


# ---------------------------------------------------------------------------
# Keychain backend routing
# ---------------------------------------------------------------------------


def test_save_routes_to_keychain_when_backend_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "keychain")
    with patch("keyring.set_password") as mock_set:
        credential_store.save("user@example.com", "rt-xyz")
    mock_set.assert_called_once()
    service, user, payload_str = mock_set.call_args.args
    assert service == "gampan"
    payload = json.loads(payload_str)
    assert payload["email"] == "user@example.com"
    assert payload["refresh_token"] == "rt-xyz"


def test_load_routes_to_keychain_when_backend_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "keychain")
    raw = json.dumps({"email": "user@example.com", "refresh_token": "rt-xyz"})
    with patch("keyring.get_password", return_value=raw) as mock_get:
        result = credential_store.load()
    mock_get.assert_called_once_with("gampan", "default")
    assert result == {"email": "user@example.com", "refresh_token": "rt-xyz"}


def test_load_keychain_returns_none_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "keychain")
    with patch("keyring.get_password", return_value=None):
        assert credential_store.load() is None


def test_clear_routes_to_keychain_when_backend_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "keychain")
    with patch("keyring.delete_password") as mock_del:
        credential_store.clear()
    mock_del.assert_called_once_with("gampan", "default")


def test_clear_keychain_is_idempotent_on_missing_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAMPAN_CRED_BACKEND", "keychain")
    with patch("keyring.delete_password", side_effect=Exception("not found")):
        credential_store.clear()  # must not raise
