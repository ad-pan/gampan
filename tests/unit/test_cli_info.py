# tests/unit/test_cli_info.py
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app


def _init_repo(tmp_path: Path) -> None:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text("network_code: '42'\nenv: dev\n")
    (tmp_path / "native-styles").mkdir()


def test_info_offline_runs_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["info", "--offline"])
    assert result.exit_code == 0
    assert "gampan" in result.output
    assert "Config" in result.output


def test_info_json_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["info", "--offline", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["version"]
    assert payload["config"]["network_code"] == "42"
