from __future__ import annotations

import os
from pathlib import Path

from gampan.core.fs.config import HookConfig

_SUBCOMMAND_ATTR = {
    "transform": "transform",
    "reverse-transform": "reverse_transform",
    "before-apply": "before_apply",
}


class HookPathError(Exception):
    """Raised when a hook path is declared but invalid (missing, non-executable, ambiguous)."""


class HookNotFound(Exception):
    """Sentinel — not raised; reserved for callers that want to distinguish missing from invalid."""


def resolve_hook_path(repo_root: Path, hook: HookConfig | None, subcommand: str) -> Path | None:
    """Return an executable path, or None for pass-through mode."""
    # 1. Per-subcommand config override
    if hook is not None:
        attr = _SUBCOMMAND_ATTR.get(subcommand)
        sub = getattr(hook, attr, None) if attr else None
        if sub is not None and sub.path is not None:
            return _check(repo_root, sub.path)
        # 2. Shared config fallback
        if hook.path is not None:
            return _check(repo_root, hook.path)
        return None  # config block present but no path for this sub — pass-through

    # 3. Default location
    file_form = repo_root / ".gampan" / "hooks"
    py_form = repo_root / ".gampan" / "hooks.py"
    if file_form.exists() and py_form.exists():
        raise HookPathError(
            "ambiguous default hook location: both .gampan/hooks and .gampan/hooks.py exist; "
            "remove one or set hook.path in config"
        )
    for candidate in (file_form, py_form):
        if candidate.exists():
            if not os.access(candidate, os.X_OK):
                raise HookPathError(f"{candidate} exists but is not executable")
            return candidate
    return None


def _check(repo_root: Path, raw: str) -> Path:
    p = (repo_root / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
    if not p.exists():
        raise HookPathError(f"hook path {raw} does not exist (resolved: {p})")
    if not os.access(p, os.X_OK):
        raise HookPathError(f"hook path {raw} is not executable (resolved: {p})")
    return p
