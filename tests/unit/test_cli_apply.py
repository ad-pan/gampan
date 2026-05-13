# tests/unit/test_cli_apply.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app

_CARD_YAML = (
    "kind: NativeStyle\nname: card\nsize:\n  width: 1\n  height: 1\n  is_fluid: false\n"
    "template_id: 1\nhtml: '<div/>'\ncss: ''\n"
    "targeting:\n  ad_units: []\n  custom: {}\nstatus: ACTIVE\n"
)


def _scaffold(tmp_path: Path) -> None:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text("network_code: '42'\nenv: dev\n")
    (tmp_path / ".gampan" / "state.json").write_text(
        '{"schema_version": 1, "network_code": "42", "resources": {}}'
    )
    (tmp_path / "native-styles").mkdir()
    (tmp_path / "native-styles" / "card.yaml").write_text(_CARD_YAML)


def test_apply_auto_approve_creates_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    soap = MagicMock(list=MagicMock(return_value=[]), create=MagicMock(return_value="new-id-1"))
    rest = MagicMock(list=MagicMock(return_value=[]))
    clients = {"NativeStyle": soap, "CreativeTemplate": rest}
    with patch("gampan.cli.apply.build_clients", return_value=clients):
        runner = CliRunner()
        result = runner.invoke(app, ["apply", "--auto-approve"])
    assert result.exit_code == 0, result.output
    soap.create.assert_called_once()


def test_apply_declines_without_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    soap = MagicMock(list=MagicMock(return_value=[]), create=MagicMock())
    rest = MagicMock(list=MagicMock(return_value=[]))
    clients = {"NativeStyle": soap, "CreativeTemplate": rest}
    with patch("gampan.cli.apply.build_clients", return_value=clients):
        runner = CliRunner()
        result = runner.invoke(app, ["apply"], input="no\n")
    assert result.exit_code == 3
    soap.create.assert_not_called()
