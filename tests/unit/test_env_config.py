"""Tests for v1.x `.gampan/config.yml` schema additions."""

from __future__ import annotations

import pytest

from gampan.core.fs.config import Config, Environment, HookConfig, HookSubconfig


def test_minimal_config_no_environments() -> None:
    cfg = Config(network_code="217")
    assert cfg.environments == {}
    assert cfg.hook is None


def test_environments_block_parsed() -> None:
    cfg = Config(
        network_code="217",
        environments={
            "dev": Environment(vars={"ad_unit": "12345"}),
            "prod": Environment(vars={"ad_unit": "67890"}),
        },
    )
    assert set(cfg.environments) == {"dev", "prod"}
    assert cfg.environments["dev"].vars == {"ad_unit": "12345"}


def test_hook_config_hierarchical() -> None:
    cfg = Config(
        network_code="217",
        hook=HookConfig(
            path="./hooks/all.py",
            **{"before-apply": HookSubconfig(path="./hooks/policy.sh")},
        ),
    )
    assert cfg.hook is not None
    assert cfg.hook.path == "./hooks/all.py"
    assert cfg.hook.before_apply is not None
    assert cfg.hook.before_apply.path == "./hooks/policy.sh"


def test_env_field_accepted_with_warning(capsys: pytest.CaptureFixture[str]) -> None:
    # structlog default PrintLogger writes to stdout; capture there.
    Config(network_code="217", env="prod")
    captured = capsys.readouterr()
    assert "`env:` field is deprecated" in captured.out


def test_environment_defaults_to_empty_vars() -> None:
    env = Environment()
    assert env.vars == {}


def test_hook_config_with_only_subcommand_path() -> None:
    """hook.path may be omitted when at least one subcommand has its own path."""
    cfg = Config(
        network_code="217",
        hook=HookConfig(transform=HookSubconfig(path="./hooks/data.py")),
    )
    assert cfg.hook.path is None
    assert cfg.hook.transform.path == "./hooks/data.py"
    assert cfg.hook.before_apply is None
