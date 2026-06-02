# tests/unit/test_cli_apply_before_apply.py
"""End-to-end ``apply`` tests for the before-apply hook gate."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app

runner = CliRunner()


_CARD_YAML = (
    "kind: NativeStyle\nname: card\nsize:\n  width: 1\n  height: 1\n  is_fluid: false\n"
    "template_id: 1\nhtml: '<div/>'\ncss: ''\n"
    "targeting:\n  ad_units: []\n  custom: {}\nstatus: ACTIVE\n"
)


def _scaffold(tmp_path: Path) -> None:
    """Scaffold a repo with one pending CREATE so the plan is non-empty."""
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text("network_code: '42'\nenv: dev\n")
    (tmp_path / ".gampan" / "state.json").write_text(
        '{"schema_version": 1, "network_code": "42", "resources": {}}'
    )
    (tmp_path / "native-styles").mkdir()
    (tmp_path / "native-styles" / "card.yaml").write_text(_CARD_YAML)


def _write_hook(tmp_path: Path, body: str) -> Path:
    hooks_dir = tmp_path / ".gampan"
    hooks_dir.mkdir(exist_ok=True)
    hook = hooks_dir / "hooks"
    hook.write_text(body)
    os.chmod(hook, 0o755)
    return hook


def _build_clients() -> dict[str, MagicMock]:
    soap = MagicMock(list=MagicMock(return_value=[]), create=MagicMock(return_value="new-id-1"))
    rest = MagicMock(list=MagicMock(return_value=[]))
    return {"NativeStyle": soap, "CreativeTemplate": rest}


def test_before_apply_absent_apply_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control: no hook on disk → apply proceeds normally."""
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    clients = _build_clients()
    with patch("gampan.cli.apply.build_clients", return_value=clients):
        result = runner.invoke(app, ["apply", "--auto-approve"])
    assert result.exit_code == 0, result.output
    clients["NativeStyle"].create.assert_called_once()


def test_before_apply_rejecting_aborts_with_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hook returns non-zero with ``{"reject": ...}`` envelope → exit 3, no mutation."""
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    _write_hook(
        tmp_path,
        """#!/usr/bin/env python3
import json, sys
sub = sys.argv[1]
if sub == "before-apply":
    sys.stdout.write(json.dumps({"reject": "test rejection"}))
    sys.exit(1)
sys.exit(64)
""",
    )
    clients = _build_clients()
    with patch("gampan.cli.apply.build_clients", return_value=clients):
        result = runner.invoke(app, ["apply", "--auto-approve"])
    assert result.exit_code == 3, result.output
    assert "test rejection" in result.output
    clients["NativeStyle"].create.assert_not_called()


def test_before_apply_crashing_aborts_with_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hook exits non-zero with no JSON envelope → HookCrash → exit 1."""
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    _write_hook(
        tmp_path,
        """#!/usr/bin/env python3
import sys
sub = sys.argv[1]
if sub == "before-apply":
    sys.stderr.write("boom")
    sys.exit(2)
sys.exit(64)
""",
    )
    clients = _build_clients()
    with patch("gampan.cli.apply.build_clients", return_value=clients):
        result = runner.invoke(app, ["apply", "--auto-approve"])
    assert result.exit_code == 1, result.output
    assert "before-apply hook crashed" in result.output
    clients["NativeStyle"].create.assert_not_called()


def test_before_apply_exit_64_passes_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hook returns 64 (not-implemented) → apply proceeds."""
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    _write_hook(
        tmp_path,
        """#!/usr/bin/env python3
import sys
sys.exit(64)
""",
    )
    clients = _build_clients()
    with patch("gampan.cli.apply.build_clients", return_value=clients):
        result = runner.invoke(app, ["apply", "--auto-approve"])
    assert result.exit_code == 0, result.output
    clients["NativeStyle"].create.assert_called_once()
