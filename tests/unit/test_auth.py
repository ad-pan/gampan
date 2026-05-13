"""Tests for credential strategies and resolver chain."""

import json
from pathlib import Path

import pytest

from gampan.core.errors import AuthError
from gampan.gam.auth import (
    EnvServiceAccountStrategy,
    resolve_credentials,
)


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


def test_env_strategy_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert EnvServiceAccountStrategy().try_load() is None


def test_resolver_raises_when_no_strategy_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(AuthError):
        resolve_credentials(strategies=[EnvServiceAccountStrategy()])
