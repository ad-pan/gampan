# tests/unit/test_cli_refresh.py
import json
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


def test_refresh_updates_remote_checksum_in_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text("network_code: '42'\nenv: dev\n")
    # State key is now {kind}:{gam_id}
    entry = {
        "gam_id": "1",
        "checksum_local": "sha256:old",
        "checksum_remote": "sha256:old",
    }
    (tmp_path / ".gampan" / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "network_code": "42",
                "resources": {"NativeStyle:1": entry},
            }
        )
    )

    # remote drifted: html changed to "<span/>"
    soap = MagicMock(list=MagicMock(return_value=[("1", _ns("card", html="<span/>"))]))
    rest = MagicMock(list=MagicMock(return_value=[]))
    clients = {"NativeStyle": soap, "CreativeTemplate": rest}
    with patch("gampan.cli.refresh.build_clients", return_value=clients):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh"])
    assert result.exit_code == 0, result.output

    state = json.loads((tmp_path / ".gampan" / "state.json").read_text())
    # State key is {kind}:{gam_id}
    remote_cs = state["resources"]["NativeStyle:1"]["checksum_remote"]
    assert remote_cs != "sha256:old"
