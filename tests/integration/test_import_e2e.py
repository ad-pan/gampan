"""Integration test: gampan import against recorded GAM responses.

Cassettes must be pre-recorded by running the same test against a real GAM sandbox
with VCR_RECORD=once. Until cassettes exist, this test is skipped.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app


@pytest.mark.skipif(
    not any(Path("tests/integration/cassettes").glob("*.yaml"))
    if Path("tests/integration/cassettes").exists()
    else True,
    reason="cassettes not recorded yet — run with real GAM sandbox once to seed",
)
def test_import_native_styles(tmp_path, monkeypatch, cassette):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text(
        "network_code: '21700000000'\nenv: integration\n"
    )
    runner = CliRunner()
    result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output
