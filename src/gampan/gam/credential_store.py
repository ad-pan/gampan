"""Credential storage backend for OAuth refresh tokens.

Default: file at $XDG_CONFIG_HOME/gampan/credentials.json (or
~/.config/gampan/credentials.json), mode 0600. Matches the pattern
used by gcloud, gh, firebase, vercel.

Set GAMPAN_CRED_BACKEND=keychain to use the OS keychain via the
keyring library instead. Useful for enterprise contexts where the
keychain is required by policy.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

_KEYCHAIN_SERVICE = "gampan"
_KEYCHAIN_USER = "default"


def _backend() -> Literal["file", "keychain"]:
    """Return the active backend: 'file' (default) or 'keychain' (opt-in).

    Reads the ``GAMPAN_CRED_BACKEND`` environment variable.  Any value other
    than ``"keychain"`` (case-insensitive) is treated as ``"file"``.
    """
    val = os.environ.get("GAMPAN_CRED_BACKEND", "file").strip().lower()
    if val == "keychain":
        return "keychain"
    return "file"


def _file_path() -> Path:
    """Return the credentials file path, honouring XDG_CONFIG_HOME."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "gampan" / "credentials.json"


# ---------------------------------------------------------------------------
# File backend
# ---------------------------------------------------------------------------


def _load_file() -> dict[str, str] | None:
    path = _file_path()
    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw)  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001  – missing / unreadable / corrupt → None
        return None


def _save_file(email: str, refresh_token: str) -> None:
    path = _file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"email": email, "refresh_token": refresh_token}, indent=2)
    # Atomic write: write to a sibling .tmp file then os.replace to avoid
    # partial reads if the process is interrupted mid-write.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _clear_file() -> None:
    path = _file_path()
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


# ---------------------------------------------------------------------------
# Keychain backend  (opt-in via GAMPAN_CRED_BACKEND=keychain)
# ---------------------------------------------------------------------------


def _load_keychain() -> dict[str, str] | None:
    import keyring

    raw = keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USER)
    if not raw:
        return None
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001
        return None


def _save_keychain(email: str, refresh_token: str) -> None:
    import keyring

    keyring.set_password(
        _KEYCHAIN_SERVICE,
        _KEYCHAIN_USER,
        json.dumps({"email": email, "refresh_token": refresh_token}),
    )


def _clear_keychain() -> None:
    import keyring

    with contextlib.suppress(Exception):  # noqa: BLE001 – already absent → idempotent
        keyring.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_USER)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load() -> dict[str, str] | None:
    """Load credentials from the active backend.

    Returns ``{"email": ..., "refresh_token": ...}`` or ``None`` when no
    credentials are stored, the storage is unreadable, or the payload is
    corrupt.  Never raises.
    """
    if _backend() == "keychain":
        return _load_keychain()
    return _load_file()


def save(email: str, refresh_token: str) -> None:
    """Persist *email* and *refresh_token* to the active backend.

    Idempotent: calling ``save`` twice with the same values is safe.
    """
    if _backend() == "keychain":
        _save_keychain(email, refresh_token)
    else:
        _save_file(email, refresh_token)


def clear() -> None:
    """Remove stored credentials from the active backend.

    Idempotent: calling ``clear`` when nothing is stored is safe.
    """
    if _backend() == "keychain":
        _clear_keychain()
    else:
        _clear_file()
