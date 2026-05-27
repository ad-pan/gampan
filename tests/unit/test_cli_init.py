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
    assert (tmp_path / "native-formats").exists()


def test_init_writes_network_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--network-code", "21700", "--non-interactive"])
    content = (tmp_path / ".gampan" / "config.yml").read_text()
    assert "network_code" in content
    assert "21700" in content


def test_init_single_env_omits_deprecated_env_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["init", "--network-code", "42", "--non-interactive"])
    content = (tmp_path / ".gampan" / "config.yml").read_text()
    # v1 single-env init must NOT emit the deprecated `env:` scalar (it would
    # fire a deprecation warning on every load) and must NOT declare envs.
    assert "env:" not in content
    assert "environments:" not in content


def test_init_with_envs_declares_environments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gampan.core.fs.config import Config

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "--network-code", "42", "--envs", "dev,prod", "--non-interactive"],
    )
    assert result.exit_code == 0, result.output
    cfg_file = tmp_path / ".gampan" / "config.yml"
    # Round-trip through Config to assert the block parses into real envs.
    from ruamel.yaml import YAML

    data = YAML(typ="safe").load(cfg_file.read_text())
    cfg = Config(**data)
    assert set(cfg.environments) == {"dev", "prod"}
    # Deprecated scalar must not be present.
    assert cfg.env is None


def test_init_rejects_blank_env_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["init", "--network-code", "42", "--envs", "dev,,prod", "--non-interactive"],
    )
    assert result.exit_code != 0
    assert "empty" in (result.output).lower() or "blank" in (result.output).lower()
