"""Tests for v1.x `.gampan/config.yml` schema additions."""

from __future__ import annotations

import logging

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


def test_env_field_accepted_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="gampan.core.fs.config"):
        Config(network_code="217", env="prod")
    assert any(
        "env:` field is removed" in r.message for r in caplog.records
    )
