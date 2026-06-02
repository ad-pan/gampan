"""Task 14 — multi-env import reconciliation + reverse-transform wiring.

The reconciliation helper folds per-env reverse-transformed resource
lists into one canonical descriptor per (kind, name). The integration
test exercises the full ``run()`` pipeline with two envs, a mocked
client, and verifies that the YAML carries ``_gam_ids: {dev, prod}``
plus per-env state slices are written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from gampan.cli.import_cmd import (
    ImportConflict,
    MergedResource,
    reconcile_across_envs,
)
from gampan.cli.main import app
from gampan.gam.models.native_style import NativeStyle, Size

# --- reconcile_across_envs unit tests ---------------------------------------


def _r(name: str, gam_id: str, css: str = "", kind: str = "NativeStyle") -> dict[str, Any]:
    return {
        "kind": kind,
        "name": name,
        "gam_id": gam_id,
        "css": css,
        "size": {"width": 1, "height": 1, "is_fluid": False},
    }


def test_same_canonical_name_both_envs_identical_merges_one_file() -> None:
    out = reconcile_across_envs(
        per_env={
            "dev": [_r("article-card", "943048")],
            "prod": [_r("article-card", "961262")],
        }
    )
    assert len(out) == 1
    merged = out[0]
    assert isinstance(merged, MergedResource)
    assert merged.canonical_name == "article-card"
    assert merged.gam_ids == {"dev": "943048", "prod": "961262"}
    # Participates in all declared envs ⇒ no `_envs` annotation needed.
    assert merged.envs is None


def test_one_env_only_writes_envs_annotation() -> None:
    out = reconcile_across_envs(
        per_env={
            "dev": [_r("experiment", "999000")],
            "prod": [],
        }
    )
    assert len(out) == 1
    merged = out[0]
    # Only dev observed ⇒ annotation records the partial-env subset.
    assert merged.envs == ["dev"]
    assert merged.gam_ids == {"dev": "999000"}


def test_different_content_raises_conflict() -> None:
    with pytest.raises(ImportConflict, match="article-card"):
        reconcile_across_envs(
            per_env={
                "dev": [_r("article-card", "1", css="A")],
                "prod": [_r("article-card", "2", css="B")],
            }
        )


def test_explicit_declared_envs_drives_annotation_decision() -> None:
    # ``per_env`` only carries ``dev``; without ``declared_envs`` the
    # reconciler would think dev IS the universe and skip the annotation.
    # Passing the broader declared list forces the annotation to surface.
    out = reconcile_across_envs(
        per_env={"dev": [_r("only-dev", "1")]},
        declared_envs=["dev", "prod"],
    )
    assert out[0].envs == ["dev"]


# --- end-to-end import multi-env integration --------------------------------


def _ns(name: str = "card") -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=320, height=250, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        status="ACTIVE",
    )


def _init_multi_env_repo(tmp_path: Path) -> None:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text(
        "network_code: '42'\n"
        "environments:\n"
        "  dev:\n"
        "    vars: {}\n"
        "  prod:\n"
        "    vars: {}\n",
        encoding="utf-8",
    )
    (tmp_path / "native-styles").mkdir()


def test_import_multi_env_writes_merged_gam_ids_and_per_env_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two-env import: same canonical name in dev + prod with identical
    content ⇒ one YAML carrying ``_gam_ids: {dev, prod}`` plus per-env
    state slices keyed by gam_id."""
    monkeypatch.chdir(tmp_path)
    _init_multi_env_repo(tmp_path)

    # One client instance per kind; .list() is invoked once per env, so
    # use side_effect to return env-specific (gam_id, model) pairs.
    fake_client = MagicMock()
    fake_client.list.side_effect = [
        [("943048", _ns(name="article-card"))],  # dev
        [("961262", _ns(name="article-card"))],  # prod
    ]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["import", "--resource", "native-styles"],
        )
    assert result.exit_code == 0, result.output

    yaml_path = tmp_path / "native-styles" / "article-card.native-style.yaml"
    assert yaml_path.exists(), result.output
    yaml_safe = YAML(typ="safe")
    data = yaml_safe.load(yaml_path.read_text(encoding="utf-8"))
    # Multi-env form: _gam_ids dict (no scalar _gam_id).
    assert data.get("_gam_ids") == {"dev": "943048", "prod": "961262"}
    assert "_gam_id" not in data
    # Participates in every declared env ⇒ no `_envs` annotation.
    assert "_envs" not in data

    # Per-env state slices keyed by gam_id (v2 layout).
    state_doc = json.loads((tmp_path / ".gampan" / "state.json").read_text())
    assert state_doc["schema_version"] == 2  # must be v2 so reload skips migration
    envs = state_doc["environments"]
    assert "943048" in envs["dev"]["resources"]
    assert "961262" in envs["prod"]["resources"]

    # Regression: reloading the state through StateStore must NOT clobber the
    # env slices. import writes schema_version=2; if it left it at 1, the
    # v1→v2 migration would overwrite `environments` with a single `default`
    # slice built from the (empty) top-level resources, wiping dev/prod.
    from gampan.core.state.store import StateStore

    reloaded = StateStore(tmp_path / ".gampan" / "state.json").load()
    assert set(reloaded.environments) == {"dev", "prod"}
    assert "943048" in reloaded.environments["dev"].resources
    assert "961262" in reloaded.environments["prod"].resources
    assert "default" not in reloaded.environments


def test_import_multi_env_partial_env_writes_envs_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resource that only exists in one env gets an ``_envs: [dev]``
    annotation so a later prod-only apply correctly skips it."""
    monkeypatch.chdir(tmp_path)
    _init_multi_env_repo(tmp_path)

    fake_client = MagicMock()
    fake_client.list.side_effect = [
        [("999000", _ns(name="experiment"))],  # dev
        [],  # prod — empty
    ]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["import", "--resource", "native-styles"],
        )
    assert result.exit_code == 0, result.output

    yaml_path = tmp_path / "native-styles" / "experiment.native-style.yaml"
    yaml_safe = YAML(typ="safe")
    data = yaml_safe.load(yaml_path.read_text(encoding="utf-8"))
    assert data["_gam_ids"] == {"dev": "999000"}
    assert data["_envs"] == ["dev"]


def test_import_multi_env_conflict_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same canonical name across envs but different content ⇒ hard
    error surfacing the conflicting resource."""
    monkeypatch.chdir(tmp_path)
    _init_multi_env_repo(tmp_path)

    dev_ns = _ns(name="article-card")
    prod_ns = NativeStyle(
        name="article-card",
        size=Size(width=320, height=250, is_fluid=False),
        template_id=1,
        html="<div/>",
        css=".prod{}",  # different css ⇒ conflict
        status="ACTIVE",
    )
    fake_client = MagicMock()
    fake_client.list.side_effect = [
        [("1", dev_ns)],
        [("2", prod_ns)],
    ]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["import", "--resource", "native-styles"],
        )
    # Hard error: non-zero exit, error message references the conflict.
    assert result.exit_code != 0
    assert "article-card" in (result.output + (result.stderr or ""))
