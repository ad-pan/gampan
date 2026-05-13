# tests/unit/test_cli_init.py
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app


def test_init_creates_skeleton(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--network-code", "42", "--non-interactive"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".gampan" / "config.yml").exists()
    assert (tmp_path / "native-styles").exists()
    assert (tmp_path / "creative-templates").exists()


def test_init_writes_network_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--network-code", "21700", "--non-interactive"])
    content = (tmp_path / ".gampan" / "config.yml").read_text()
    assert "network_code" in content
    assert "21700" in content
