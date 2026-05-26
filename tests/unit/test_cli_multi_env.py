"""CLI flag tests for Task 13 — `--env` / `--envs` / `--all-envs`.

All assertions deliberately fire BEFORE any GAM client is touched: the
flag validation in :mod:`gampan.cli._envs` runs before `build_clients`,
so an empty `MagicMock` stand-in is enough — the tests are checking
validation behaviour, not the planner/executor.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app

runner = CliRunner()


def _multi_env_repo(tmp_path: Path) -> Path:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text(
        'network_code: "217"\nenvironments:\n  dev: {}\n  prod: {}\n'
    )
    (tmp_path / ".gampan" / "state.json").write_text(
        '{"schema_version": 2, "network_code": "217", '
        '"environments": {"dev": {"resources": {}}, "prod": {"resources": {}}}}'
    )
    return tmp_path


def _v1_repo(tmp_path: Path) -> Path:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text('network_code: "217"\n')
    (tmp_path / ".gampan" / "state.json").write_text(
        '{"schema_version": 1, "network_code": "217", "resources": {}}'
    )
    return tmp_path


def _empty_clients() -> dict[str, MagicMock]:
    """Minimal client map: every kind list() returns nothing."""
    return {
        "NativeStyle": MagicMock(list=MagicMock(return_value=[])),
        "CreativeTemplate": MagicMock(list=MagicMock(return_value=[])),
    }


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


def test_plan_requires_env_when_envs_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.plan.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["plan"], catch_exceptions=False)
    out = result.stdout + result.stderr
    assert result.exit_code == 2
    assert "--env" in out
    assert "dev" in out and "prod" in out


def test_plan_unknown_env_lists_choices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.plan.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["plan", "--env", "staging"], catch_exceptions=False)
    out = result.stdout + result.stderr
    assert result.exit_code == 2
    assert "staging" in out
    assert "dev" in out and "prod" in out


def test_plan_env_and_all_envs_are_mutually_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.plan.build_clients", return_value=_empty_clients()):
        result = runner.invoke(
            app, ["plan", "--env", "dev", "--all-envs"], catch_exceptions=False
        )
    out = result.stdout + result.stderr
    assert result.exit_code == 2
    assert "--env" in out and "--all-envs" in out


def test_plan_all_envs_iterates_each_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.plan.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["plan", "--all-envs"], catch_exceptions=False)
    # No pending changes (no YAMLs, no remote) → exit 0 with two headers.
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "=== env: dev ===" in result.stdout
    assert "=== env: prod ===" in result.stdout


def test_v1_single_env_plan_works_without_env_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_v1_repo(tmp_path))
    with patch("gampan.cli.plan.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["plan"], catch_exceptions=False)
    # v1 mode: --env not required, no validation error.
    assert "--env is required" not in (result.stderr or "")
    # And nothing pending → exit 0.
    assert result.exit_code == 0, result.stdout + result.stderr


def test_v1_plan_ignores_passed_env_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v1 mode: --env is silently ignored so configs don't break."""
    monkeypatch.chdir(_v1_repo(tmp_path))
    with patch("gampan.cli.plan.build_clients", return_value=_empty_clients()):
        result = runner.invoke(
            app, ["plan", "--env", "anything"], catch_exceptions=False
        )
    assert result.exit_code == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def test_apply_rejects_all_envs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """apply intentionally has no --all-envs flag (spec §2 non-goals)."""
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.apply.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["apply", "--all-envs"], catch_exceptions=False)
    out = result.stdout + result.stderr
    assert result.exit_code != 0
    # typer/click rejects the unknown option.
    assert "--all-envs" in out or "No such option" in out


def test_apply_requires_env_when_envs_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.apply.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["apply"], catch_exceptions=False)
    out = result.stdout + result.stderr
    assert result.exit_code == 2
    assert "--env" in out


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


def test_refresh_requires_env_when_envs_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.refresh.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["refresh"], catch_exceptions=False)
    out = result.stdout + result.stderr
    assert result.exit_code == 2
    assert "--env" in out


def test_refresh_v1_works_without_env_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_v1_repo(tmp_path))
    with patch("gampan.cli.refresh.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["refresh"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def test_import_envs_flag_required_when_environments_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.import_cmd.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["import"], catch_exceptions=False)
    out = result.stdout + result.stderr
    assert result.exit_code == 2
    assert "--envs" in out


def test_import_envs_unknown_name_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_multi_env_repo(tmp_path))
    with patch("gampan.cli.import_cmd.build_clients", return_value=_empty_clients()):
        result = runner.invoke(
            app, ["import", "--envs", "dev,staging"], catch_exceptions=False
        )
    out = result.stdout + result.stderr
    assert result.exit_code == 2
    assert "staging" in out


def test_import_v1_works_without_envs_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_v1_repo(tmp_path))
    with patch("gampan.cli.import_cmd.build_clients", return_value=_empty_clients()):
        result = runner.invoke(app, ["import"], catch_exceptions=False)
    # v1: no flag needed, command runs to completion with zero remote resources.
    assert result.exit_code == 0, result.stdout + result.stderr
