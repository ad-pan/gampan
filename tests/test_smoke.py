from typer.testing import CliRunner

from gampan.cli.main import app


def test_version_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "gampan" in result.output
