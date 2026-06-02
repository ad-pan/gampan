import os
from pathlib import Path

import pytest

from gampan.core.fs.config import HookConfig, HookSubconfig
from gampan.core.hooks.discover import HookPathError, resolve_hook_path


def _make_exec(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/usr/bin/env bash\nexit 64\n")
    os.chmod(p, 0o755)


def test_default_location_file(tmp_path: Path) -> None:
    _make_exec(tmp_path / ".gampan" / "hooks")
    expected = tmp_path / ".gampan" / "hooks"
    assert resolve_hook_path(tmp_path, hook=None, subcommand="transform") == expected


def test_default_location_py_alternative(tmp_path: Path) -> None:
    _make_exec(tmp_path / ".gampan" / "hooks.py")
    expected = tmp_path / ".gampan" / "hooks.py"
    assert resolve_hook_path(tmp_path, hook=None, subcommand="transform") == expected


def test_default_ambiguous_raises(tmp_path: Path) -> None:
    _make_exec(tmp_path / ".gampan" / "hooks")
    _make_exec(tmp_path / ".gampan" / "hooks.py")
    with pytest.raises(HookPathError, match="ambiguous"):
        resolve_hook_path(tmp_path, hook=None, subcommand="transform")


def test_no_hook_returns_none(tmp_path: Path) -> None:
    assert resolve_hook_path(tmp_path, hook=None, subcommand="transform") is None


def test_subcommand_specific_path_overrides(tmp_path: Path) -> None:
    _make_exec(tmp_path / ".gampan" / "hooks")
    _make_exec(tmp_path / "hooks" / "policy.sh")
    hook = HookConfig(
        path=".gampan/hooks",
        **{"before-apply": HookSubconfig(path="hooks/policy.sh")},
    )
    assert resolve_hook_path(tmp_path, hook, "transform") == tmp_path / ".gampan" / "hooks"
    assert resolve_hook_path(tmp_path, hook, "before-apply") == tmp_path / "hooks" / "policy.sh"


def test_config_path_missing_file_raises(tmp_path: Path) -> None:
    hook = HookConfig(path="does-not-exist")
    with pytest.raises(HookPathError, match="does-not-exist"):
        resolve_hook_path(tmp_path, hook, "transform")


def test_config_path_not_executable_raises(tmp_path: Path) -> None:
    p = tmp_path / "script.py"
    p.write_text("#!/usr/bin/env python3\n")
    # no chmod
    hook = HookConfig(path="script.py")
    with pytest.raises(HookPathError, match="executable"):
        resolve_hook_path(tmp_path, hook, "transform")
