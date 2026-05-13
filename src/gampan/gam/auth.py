"""Four-strategy credential resolver (env / keychain / gcloud / metadata)."""

from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import keyring

from gampan.core.errors import AuthError

_KEYCHAIN_SERVICE = "gampan"
_KEYCHAIN_USER = "default"


@dataclass(frozen=True)
class Credentials:
    """Concrete credentials implementing the core.protocols.Credentials protocol."""

    principal: str
    _token_provider: Callable[[], str]

    def get_token(self) -> str:
        return self._token_provider()


class Strategy(ABC):
    name: str

    @abstractmethod
    def try_load(self) -> Credentials | None:
        """Return creds if this strategy applies, else None."""


class EnvServiceAccountStrategy(Strategy):
    name = "env"

    def try_load(self) -> Credentials | None:
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not path:
            return None
        data = json.loads(Path(path).read_text())
        if data.get("type") != "service_account":
            raise AuthError(f"GOOGLE_APPLICATION_CREDENTIALS={path} is not a service account file")

        def token() -> str:
            # Token minting handled by client libs (google-auth) using the same env var.
            return ""  # placeholder: libs read env directly

        return Credentials(principal=data["client_email"], _token_provider=token)


class KeychainStrategy(Strategy):
    """Stores user OAuth refresh token written by `gampan auth login`."""

    name = "keychain"

    def try_load(self) -> Credentials | None:
        raw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USER)
        if not raw:
            return None
        data = json.loads(raw)
        return Credentials(
            principal=data["email"],
            _token_provider=lambda: data["refresh_token"],
        )


class GcloudAdcStrategy(Strategy):
    name = "gcloud"

    def try_load(self) -> Credentials | None:
        try:
            out = subprocess.check_output(
                ["gcloud", "auth", "application-default", "print-access-token"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

        # principal not directly available via this command; ask gcloud for the active account
        try:
            principal = subprocess.check_output(
                ["gcloud", "config", "get-value", "account"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            principal = "unknown@gcloud-adc"

        return Credentials(principal=principal, _token_provider=lambda: out)


def resolve_credentials(strategies: list[Strategy] | None = None) -> Credentials:
    """Try each strategy in order; raise AuthError if none yields creds."""
    chain: list[Strategy] = strategies or [
        EnvServiceAccountStrategy(),
        KeychainStrategy(),
        GcloudAdcStrategy(),
    ]
    for s in chain:
        creds = s.try_load()
        if creds is not None:
            return creds
    raise AuthError(
        "No credentials found. Run `gampan auth login` or set GOOGLE_APPLICATION_CREDENTIALS."
    )
