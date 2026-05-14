"""Four-strategy credential resolver (env / keychain / gcloud / metadata)."""

from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import keyring

from gampan.core.errors import AuthError

_KEYCHAIN_SERVICE = "gampan"
_KEYCHAIN_USER = "default"
_GAM_SCOPE = "https://www.googleapis.com/auth/dfp"

# ---------------------------------------------------------------------------
# google.oauth2 type aliases (imported lazily to allow mocking in tests)
# ---------------------------------------------------------------------------


def _google_oauth2_credentials(
    *,
    token: str | None,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    token_uri: str,
    scopes: list[str],
) -> object:
    """Construct a ``google.oauth2.credentials.Credentials`` at call time."""
    from google.oauth2.credentials import Credentials as GoogleOAuthCredentials

    return GoogleOAuthCredentials(  # type: ignore[no-untyped-call]
        token=token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri=token_uri,
        scopes=scopes,
    )


def _google_service_account_credentials(path: str) -> object:
    """Construct a ``google.oauth2.service_account.Credentials`` at call time."""
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
        path, scopes=[_GAM_SCOPE]
    )


def _google_adc_credentials() -> object:
    """Return the first element of ``google.auth.default()`` at call time."""
    import google.auth

    credentials, _ = google.auth.default(scopes=[_GAM_SCOPE])
    return credentials


# ---------------------------------------------------------------------------
# Credentials dataclass
# ---------------------------------------------------------------------------

_Strategy = Literal["env", "keychain", "gcloud"]


@dataclass(frozen=True)
class Credentials:
    """Concrete credentials implementing the core.protocols.Credentials protocol.

    ``_strategy`` controls which Google auth object ``to_google_credentials()``
    constructs:

    * ``"env"``      – service-account key file referenced by
                       ``GOOGLE_APPLICATION_CREDENTIALS``.
    * ``"keychain"`` – user OAuth refresh token stored by ``gampan auth login``.
    * ``"gcloud"``   – Google ADC obtained via ``google.auth.default()``.

    ``_extra`` carries the minimal state needed for each path:

    * ``"env"``      – ``{"sa_path": "<path>"}``
    * ``"keychain"`` – ``{"refresh_token": "...", "client_id": "...",
                          "client_secret": "..."}``
    * ``"gcloud"``   – ``{}``
    """

    principal: str
    _token_provider: Callable[[], str]
    _strategy: _Strategy = field(default="gcloud")
    _extra: dict[str, str] = field(default_factory=dict)

    def get_token(self) -> str:
        return self._token_provider()

    def to_google_credentials(self) -> object:
        """Return a ``google.auth.credentials.Credentials``-compatible object.

        The concrete type depends on ``_strategy``:

        * ``"env"``      → ``google.oauth2.service_account.Credentials``
        * ``"keychain"`` → ``google.oauth2.credentials.Credentials``
        * ``"gcloud"``   → whatever ``google.auth.default()`` returns
        """
        if self._strategy == "env":
            return _google_service_account_credentials(self._extra["sa_path"])
        if self._strategy == "keychain":
            return _google_oauth2_credentials(
                token=None,
                refresh_token=self._extra["refresh_token"],
                client_id=self._extra["client_id"],
                client_secret=self._extra["client_secret"],
                token_uri="https://oauth2.googleapis.com/token",
                scopes=[_GAM_SCOPE],
            )
        # "gcloud"
        return _google_adc_credentials()


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------


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

        return Credentials(
            principal=data["client_email"],
            _token_provider=token,
            _strategy="env",
            _extra={"sa_path": path},
        )


class KeychainStrategy(Strategy):
    """Stores user OAuth refresh token written by `gampan auth login`."""

    name = "keychain"

    def try_load(self) -> Credentials | None:
        raw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USER)
        if not raw:
            return None
        data = json.loads(raw)
        refresh_token: str = data["refresh_token"]
        client_id = os.environ.get("GAMPAN_OAUTH_CLIENT_ID", "")
        client_secret = os.environ.get("GAMPAN_OAUTH_CLIENT_SECRET", "")
        return Credentials(
            principal=data["email"],
            _token_provider=lambda: refresh_token,
            _strategy="keychain",
            _extra={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )


class GcloudAdcStrategy(Strategy):
    name = "gcloud"

    def try_load(self) -> Credentials | None:
        # Initial call verifies gcloud is installed and ADC is configured.
        try:
            subprocess.check_output(
                ["gcloud", "auth", "application-default", "print-access-token"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
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

        def _get_token() -> str:
            return subprocess.check_output(
                ["gcloud", "auth", "application-default", "print-access-token"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()

        return Credentials(
            principal=principal,
            _token_provider=_get_token,
            _strategy="gcloud",
            _extra={},
        )


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
