# tests/unit/test_cli_bootstrap.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app

_NETWORK = {"networkCode": "12345678", "displayName": "Test Network"}


def _mock_service() -> MagicMock:
    svc = MagicMock()
    svc.makeTestNetwork.return_value = _NETWORK
    return svc


def test_bootstrap_prints_network_code() -> None:
    runner = CliRunner()
    with (
        patch("gampan.cli.bootstrap.resolve_credentials", return_value=MagicMock()),
        patch("gampan.cli.bootstrap.soap_bootstrap_service_factory", return_value=_mock_service()),
    ):
        result = runner.invoke(app, ["bootstrap-test-network", "--no-write-config"])
    assert result.exit_code == 0, result.output
    assert "12345678" in result.output
    assert "Test Network" in result.output
    assert "https://admanager.google.com/12345678" in result.output


def test_bootstrap_writes_config_when_config_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg_dir = tmp_path / ".gampan"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "config.yml"
    cfg_file.write_text("network_code: '0'\nenv: default\n")

    runner = CliRunner()
    with (
        patch("gampan.cli.bootstrap.resolve_credentials", return_value=MagicMock()),
        patch("gampan.cli.bootstrap.soap_bootstrap_service_factory", return_value=_mock_service()),
    ):
        result = runner.invoke(app, ["bootstrap-test-network", "--force"])
    assert result.exit_code == 0, result.output
    content = cfg_file.read_text()
    assert "12345678" in content
    assert "config.yml updated" in result.output


def test_bootstrap_skips_config_write_with_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg_dir = tmp_path / ".gampan"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "config.yml"
    original = "network_code: '0'\nenv: default\n"
    cfg_file.write_text(original)

    runner = CliRunner()
    with (
        patch("gampan.cli.bootstrap.resolve_credentials", return_value=MagicMock()),
        patch("gampan.cli.bootstrap.soap_bootstrap_service_factory", return_value=_mock_service()),
    ):
        result = runner.invoke(app, ["bootstrap-test-network", "--no-write-config"])
    assert result.exit_code == 0, result.output
    # config.yml must not have changed
    assert cfg_file.read_text() == original


def test_bootstrap_falls_back_to_getAllNetworks_when_already_associated() -> None:
    """When the account is already associated with a network, makeTestNetwork raises
    GOOGLE_ACCOUNT_ALREADY_ASSOCIATED_WITH_NETWORK; we should fall back to
    getAllNetworks() and surface what the account already has access to."""
    svc = MagicMock()
    svc.makeTestNetwork.side_effect = Exception(
        "[AuthenticationError.GOOGLE_ACCOUNT_ALREADY_ASSOCIATED_WITH_NETWORK @ ]"
    )
    svc.getAllNetworks.return_value = [
        {"networkCode": "999000", "displayName": "Zigbang Prod"},
    ]
    runner = CliRunner()
    with (
        patch("gampan.cli.bootstrap.resolve_credentials", return_value=MagicMock()),
        patch("gampan.cli.bootstrap.soap_bootstrap_service_factory", return_value=svc),
    ):
        result = runner.invoke(app, ["bootstrap-test-network", "--no-write-config"])
    assert result.exit_code == 0, result.output
    assert "999000" in result.output
    assert "Zigbang Prod" in result.output


def test_bootstrap_lists_multiple_existing_networks() -> None:
    """With multiple existing networks, the command lists them and exits without
    auto-picking one."""
    svc = MagicMock()
    svc.makeTestNetwork.side_effect = Exception(
        "[AuthenticationError.GOOGLE_ACCOUNT_ALREADY_ASSOCIATED_WITH_NETWORK @ ]"
    )
    svc.getAllNetworks.return_value = [
        {"networkCode": "111", "displayName": "Network A"},
        {"networkCode": "222", "displayName": "Network B"},
    ]
    runner = CliRunner()
    with (
        patch("gampan.cli.bootstrap.resolve_credentials", return_value=MagicMock()),
        patch("gampan.cli.bootstrap.soap_bootstrap_service_factory", return_value=svc),
    ):
        result = runner.invoke(app, ["bootstrap-test-network"])
    assert result.exit_code == 0, result.output
    assert "111" in result.output
    assert "Network A" in result.output
    assert "222" in result.output
    assert "Network B" in result.output
    assert "gampan init --network-code" in result.output
