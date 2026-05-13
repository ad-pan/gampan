# tests/unit/test_cli_import.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app
from gampan.gam.models.native_style import NativeStyle, Size, Targeting


def _ns() -> NativeStyle:
    return NativeStyle(
        name="card",
        size=Size(width=320, height=250, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )


def _init_repo(tmp_path: Path) -> None:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text("network_code: '42'\nenv: dev\n")
    (tmp_path / "native-styles").mkdir()


def test_import_writes_yaml_and_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    fake_client = MagicMock()
    fake_client.list.return_value = [("999", _ns())]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output
    yaml_path = tmp_path / "native-styles" / "card.yaml"
    assert yaml_path.exists()
    state_path = tmp_path / ".gampan" / "state.json"
    assert state_path.exists()
    assert "NativeStyle:card" in state_path.read_text()
