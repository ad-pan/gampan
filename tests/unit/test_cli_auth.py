"""Unit tests for `gampan auth` CLI subcommands."""

from unittest.mock import patch

from typer.testing import CliRunner

from gampan.cli.main import app


def test_login_invokes_browser_flow_and_stores_creds() -> None:
    runner = CliRunner()
    with (
        patch("gampan.cli.auth.browser_login", return_value=("u@x", "rt-1")) as bl,
        patch("gampan.cli.auth.store_credentials") as sc,
    ):
        result = runner.invoke(app, ["auth", "login"])
        assert result.exit_code == 0
        bl.assert_called_once()
        sc.assert_called_once_with(email="u@x", refresh_token="rt-1")


def test_logout_clears_keychain() -> None:
    runner = CliRunner()
    with patch("gampan.cli.auth.clear_credentials") as cc:
        result = runner.invoke(app, ["auth", "logout"])
        assert result.exit_code == 0
        cc.assert_called_once()


def test_status_prints_principal_when_stored() -> None:
    runner = CliRunner()
    creds = {"email": "u@x", "refresh_token": "rt"}
    with patch("gampan.cli.auth.load_credentials", return_value=creds):
        result = runner.invoke(app, ["auth", "status"])
        assert result.exit_code == 0
        assert "u@x" in result.output
