"""Tests for the CLI main entry point."""

from typer.testing import CliRunner

from gampan.cli.main import app


def test_help_lists_all_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["init", "auth", "import", "plan", "apply", "refresh", "info", "version"]:
        assert cmd in result.output
