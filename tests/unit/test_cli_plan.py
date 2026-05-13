# tests/unit/test_cli_plan.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app
from gampan.gam.models.native_style import NativeStyle, Size, Targeting


def _ns(name: str, html: str = "<div/>") -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html=html,
        css="",
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )


def _scaffold(tmp_path: Path) -> None:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text("network_code: '42'\nenv: dev\n")
    (tmp_path / ".gampan" / "state.json").write_text(
        '{"schema_version": 1, "network_code": "42", "resources": {}}'
    )
    (tmp_path / "native-styles").mkdir()
    (tmp_path / "native-styles" / "card.yaml").write_text(
        "kind: NativeStyle\nname: card\nsize:\n  width: 1\n  height: 1\n  is_fluid: false\n"
        "template_id: 1\nhtml: '<div/>'\ncss: ''\n"
        "targeting:\n  ad_units: []\n  custom: {}\nstatus: ACTIVE\n"
    )


def test_plan_shows_create_for_new_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    with patch(
        "gampan.cli.plan.build_clients",
        return_value={
            "NativeStyle": MagicMock(list=MagicMock(return_value=[])),
            "CreativeTemplate": MagicMock(list=MagicMock(return_value=[])),
        },
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["plan"])
    assert result.exit_code == 2  # has pending changes
    assert "CREATE" in result.output
    assert "card" in result.output
