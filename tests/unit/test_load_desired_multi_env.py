"""Function-level tests for `_load_desired` after multi-env wiring (Task 11).

These exercise identity resolution, `_envs` filtering, and the transform hook
without going through the CLI (the ``--env`` flag is wired up in Task 13).
"""

from __future__ import annotations

import os
from pathlib import Path

from gampan.cli.plan import _load_desired
from gampan.core.fs.config import Config, Environment


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def _basic_ns(name: str, gam_ids_block: str = "") -> str:
    return (
        f"kind: NativeStyle\n"
        f"name: {name}\n"
        f"{gam_ids_block}"
        f"size: {{width: 1, height: 1, is_fluid: false}}\n"
        f"template_id: 1\n"
        f"html: '<div/>'\n"
        f"css: ''\n"
        f"targeting: {{ad_units: [], custom: {{}}}}\n"
        f"status: ACTIVE\n"
    )


def _install_hook(repo: Path, body: str) -> None:
    h = repo / ".gampan" / "hooks"
    h.parent.mkdir(parents=True, exist_ok=True)
    h.write_text(body)
    os.chmod(h, 0o755)


def test_no_hook_returns_resources_unchanged(tmp_path: Path) -> None:
    _write(tmp_path / "native-styles" / "card.yaml", _basic_ns("card"))
    out, paths = _load_desired(tmp_path, Config(network_code="217"), env="default")
    assert len(out) == 1
    key, model = out[0]
    assert "card" in key
    assert model.name == "card"


def test_transform_hook_renames_resources(tmp_path: Path) -> None:
    _write(tmp_path / "native-styles" / "card.yaml", _basic_ns("card"))
    _install_hook(
        tmp_path,
        """#!/usr/bin/env python3
import json, sys
sub = sys.argv[1]
inp = json.load(sys.stdin)
if sub == "transform":
    env = inp["environment"]
    for r in inp["resources"]:
        r["name"] = f"[{env}] {r['name']}"
    json.dump({"schema_version": 1, "resources": inp["resources"]}, sys.stdout)
else:
    sys.exit(64)
""",
    )
    cfg = Config(
        network_code="217",
        environments={"dev": Environment(), "prod": Environment()},
    )
    out, _ = _load_desired(tmp_path, cfg, env="dev")
    assert len(out) == 1
    _, model = out[0]
    assert model.name == "[dev] card"


def test_envs_filter_drops_non_participating(tmp_path: Path) -> None:
    _write(
        tmp_path / "native-styles" / "experimental.yaml",
        "kind: NativeStyle\nname: experimental\n_envs: [dev]\n"
        "size: {width: 1, height: 1, is_fluid: false}\ntemplate_id: 1\n"
        "html: '<div/>'\ncss: ''\ntargeting: {ad_units: [], custom: {}}\nstatus: ACTIVE\n",
    )
    cfg = Config(
        network_code="217",
        environments={"dev": Environment(), "prod": Environment()},
    )
    # In prod, the resource is filtered out.
    out, _ = _load_desired(tmp_path, cfg, env="prod")
    assert out == []
    # In dev, it appears.
    out, _ = _load_desired(tmp_path, cfg, env="dev")
    assert len(out) == 1


def test_gam_ids_dict_threads_through_to_state_key(tmp_path: Path) -> None:
    _write(
        tmp_path / "native-styles" / "card.yaml",
        _basic_ns("card", "_gam_ids:\n  dev: '943048'\n  prod: '961262'\n"),
    )
    cfg = Config(
        network_code="217",
        environments={"dev": Environment(), "prod": Environment()},
    )
    out_dev, _ = _load_desired(tmp_path, cfg, env="dev")
    out_prod, _ = _load_desired(tmp_path, cfg, env="prod")
    [(key_dev, _)] = out_dev
    [(key_prod, _)] = out_prod
    assert key_dev == "NativeStyle:943048"
    assert key_prod == "NativeStyle:961262"
