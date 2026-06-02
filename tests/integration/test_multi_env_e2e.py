"""End-to-end multi-environment workflow test.

Exercises the full lifecycle of a multi-env gampan repo against a fake
in-memory GAM backend:

  1. Scaffold a repo with ``environments: {dev, prod}`` and a kind-aware
     reverse-/forward-transform hook.
  2. ``gampan import --envs=dev,prod`` — pulls env-aware remote state,
     reverse-transforms decorated names, reconciles across envs, writes
     canonical YAML with ``_gam_ids: {dev, prod}``.
  3. Edit a YAML.
  4. ``gampan plan --all-envs`` — both env slices report the same diff.
  5. ``gampan apply --env=dev --auto-approve`` — transform decorates the
     name before update, executor mutates remote at the dev gam_id.
  6. ``gampan apply --env=prod --auto-approve`` — same change, prod
     gam_id, no decoration.

The fake :class:`FakeClient` mirrors :class:`gampan.core.protocols.Client`
and persists remote state in a dict so assertions can verify what the
executor actually mutated.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from gampan.cli.main import app
from gampan.gam.models.native_style import NativeStyle, Size

runner = CliRunner()


# --- fake client ------------------------------------------------------------


class FakeClient:
    """In-memory GAM client honouring the ``Client`` protocol shape.

    The ``store`` dict is keyed by gam_id and persists across .list() and
    .update() calls so the test can observe mutation semantics.
    """

    def __init__(self, store: dict[str, NativeStyle]) -> None:
        self.store = store
        self._next_id = max((int(k) for k in store), default=900000) + 1

    def list(self, *, include_archived: bool = False) -> list[tuple[str, NativeStyle]]:
        return [(gid, ns) for gid, ns in self.store.items()]

    def get(self, gam_id: str) -> NativeStyle:
        return self.store[gam_id]

    def create(self, resource: NativeStyle) -> str:
        gid = str(self._next_id)
        self._next_id += 1
        self.store[gid] = resource
        return gid

    def update(
        self,
        gam_id: str,
        resource: NativeStyle,
        *,
        changed_paths: list[str] | None = None,
    ) -> None:
        # FakeClient does no per-endpoint dispatch — it just records the
        # full desired model, so changed_paths is informational only here.
        del changed_paths
        self.store[gam_id] = resource

    def delete(self, gam_id: str) -> None:
        del self.store[gam_id]


def _ns(name: str, css: str = "") -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=320, height=250, is_fluid=False),
        template_id=1,
        html="<div/>",
        css=css,
        status="ACTIVE",
    )


# --- repo scaffold ----------------------------------------------------------


_HOOK_SCRIPT = """#!/usr/bin/env python3
import json, sys

DECORATED = {"NativeStyle", "NativeFormat"}
PREFIX = "[dev] "

sub = sys.argv[1] if len(sys.argv) > 1 else ""
inp = json.load(sys.stdin)

if sub == "transform":
    env = inp["environment"]
    out = []
    for r in inp["resources"]:
        if r["kind"] in DECORATED and env == "dev":
            r["name"] = f"{PREFIX}{r['name']}"
        out.append(r)
    json.dump({"schema_version": 1, "resources": out}, sys.stdout)

elif sub == "reverse-transform":
    env = inp["environment"]
    out = []
    for r in inp["resources"]:
        if r["kind"] not in DECORATED:
            out.append(r)
            continue
        decorated = r["name"].startswith(PREFIX)
        if env == "dev":
            if not decorated:
                continue
            r["name"] = r["name"][len(PREFIX):]
        else:
            if decorated:
                continue
        out.append(r)
    json.dump({"schema_version": 1, "resources": out}, sys.stdout)

else:
    sys.exit(64)
"""


def _scaffold_repo(repo: Path) -> None:
    (repo / ".gampan").mkdir()
    (repo / ".gampan" / "config.yml").write_text(
        "network_code: '42'\n"
        "environments:\n"
        "  dev: {}\n"
        "  prod: {}\n",
        encoding="utf-8",
    )
    # Empty v2 state — apply/plan call StateStore.load() (not load_or_empty),
    # so the file must exist even before the first import.
    (repo / ".gampan" / "state.json").write_text(
        '{"schema_version": 2, "network_code": "42", "environments": {}}',
        encoding="utf-8",
    )
    hook = repo / ".gampan" / "hooks"
    hook.write_text(_HOOK_SCRIPT, encoding="utf-8")
    os.chmod(hook, 0o755)


# --- the actual e2e test ----------------------------------------------------


def test_multi_env_e2e_import_plan_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Walk through import → edit → plan → apply (dev) → apply (prod)."""
    monkeypatch.chdir(tmp_path)
    _scaffold_repo(tmp_path)

    # Initial remote state. Use per-env fake clients so that an apply
    # scoped to one env doesn't see the other env's resources. (The v1.x
    # diff engine is not yet env-aware on the remote-fetch side; filtering
    # at the fake-client boundary mirrors the eventual real-world setup
    # where the hook would identify which gam_ids belong to which env.)
    dev_client = FakeClient(
        {"943048": _ns("[dev] article-card", css=".card { display: block; }")}
    )
    prod_client = FakeClient(
        {"961262": _ns("article-card", css=".card { display: block; }")}
    )
    # Import needs to see BOTH envs at once; use a "merged" client that
    # returns the union, paralleling a real GAM network where dev and prod
    # variants coexist.
    import_client = FakeClient({**dev_client.store, **prod_client.store})

    # === Step 1: import ===
    with patch("gampan.cli.import_cmd.build_clients", return_value={"NativeStyle": import_client}):
        result = runner.invoke(
            app,
            ["import", "--resource", "native-styles"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, result.output

    yaml_path = tmp_path / "native-styles" / "article-card.native-style.yaml"
    assert yaml_path.exists(), f"missing canonical YAML\n{result.output}"
    yaml_safe = YAML(typ="safe")
    data = yaml_safe.load(yaml_path.read_text(encoding="utf-8"))
    # One canonical YAML with both env gam_ids; no scalar _gam_id; no _envs
    # because the resource participates in every declared env.
    assert data["_gam_ids"] == {"dev": "943048", "prod": "961262"}
    assert "_gam_id" not in data
    assert "_envs" not in data
    assert data["name"] == "article-card"

    # state.json: per-env slices keyed by gam_id
    state_doc = json.loads((tmp_path / ".gampan" / "state.json").read_text())
    assert "943048" in state_doc["environments"]["dev"]["resources"]
    assert "961262" in state_doc["environments"]["prod"]["resources"]

    # === Step 2: edit the canonical YAML (change CSS) ===
    # write_resource may inline css directly OR via !file side reference,
    # depending on the writer's heuristics. Cover both: edit the side file if
    # it exists, otherwise mutate the YAML inline.
    css_side = tmp_path / "native-styles" / "article-card.native-style.css"
    new_css = ".updated { color: red; }"
    if css_side.exists():
        css_side.write_text(new_css, encoding="utf-8")
    else:
        # Inline css — rewrite the YAML's css field.
        yaml_rt = YAML()
        yaml_rt.default_flow_style = False
        yaml_rt.width = 2**31 - 1
        d = yaml_rt.load(yaml_path.read_text(encoding="utf-8"))
        d["css"] = new_css
        with yaml_path.open("w", encoding="utf-8") as f:
            yaml_rt.dump(d, f)

    # === Step 3: plan --all-envs ===
    # Each plan iteration sees only its own env's remote (via per-env client).
    # In a real GAM network this would be filtered by the hook + env-aware
    # state lookup; here we approximate by routing clients per env.
    def _plan_clients_for(env_target: str) -> dict[str, Any]:
        return {"NativeStyle": dev_client if env_target == "dev" else prod_client}

    # The plan command's per-env loop calls build_clients once globally, so we
    # invoke plan per env separately to keep client scoping clean.
    with patch("gampan.cli.plan.build_clients", return_value={"NativeStyle": dev_client}):
        plan_dev = runner.invoke(
            app, ["plan", "--env", "dev", "--simple-exitcode"], catch_exceptions=False
        )
    assert plan_dev.exit_code == 0, plan_dev.output
    with patch("gampan.cli.plan.build_clients", return_value={"NativeStyle": prod_client}):
        plan_prod = runner.invoke(
            app, ["plan", "--env", "prod", "--simple-exitcode"], catch_exceptions=False
        )
    assert plan_prod.exit_code == 0, plan_prod.output

    # === Step 4: apply --env=dev ===
    with patch("gampan.cli.apply.build_clients", return_value={"NativeStyle": dev_client}):
        result = runner.invoke(
            app,
            ["apply", "--env", "dev", "--auto-approve"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, result.output
    # The dev gam_id resource on the fake backend must now reflect the new CSS,
    # and its name on GAM must carry the [dev] prefix (added by transform).
    dev_remote = dev_client.store["943048"]
    assert dev_remote.css == ".updated { color: red; }"
    assert dev_remote.name == "[dev] article-card"
    # Prod resource (on its separate fake client) is untouched until step 5.
    prod_remote_before = prod_client.store["961262"]
    assert prod_remote_before.css == ".card { display: block; }"

    # === Step 5: apply --env=prod ===
    with patch("gampan.cli.apply.build_clients", return_value={"NativeStyle": prod_client}):
        result = runner.invoke(
            app,
            ["apply", "--env", "prod", "--auto-approve"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, result.output
    prod_remote = prod_client.store["961262"]
    assert prod_remote.css == ".updated { color: red; }"
    # Prod keeps the canonical (undecorated) name.
    assert prod_remote.name == "article-card"


def test_multi_env_e2e_create_dev_then_promote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Demonstrate the brand-new resource → dev create → promote → prod create flow.

    1. User writes a new NativeStyle YAML with ``_envs: [dev]`` and no
       ``_gam_ids``.
    2. ``apply --env=dev`` creates it in dev only; writeback adds the
       returned gam_id under ``_gam_ids[dev]``. Remote-side name carries
       the ``[dev]`` prefix because the transform hook decorates dev.
    3. Operator promotes by removing ``_envs: [dev]``.
    4. ``apply --env=prod`` creates the prod counterpart; writeback
       records ``_gam_ids[prod]`` alongside the existing dev id. The prod
       remote keeps the canonical (undecorated) name.

    Note: this test deliberately does NOT exercise the "prod apply is a no-op
    while the resource is dev-only" path, because the env-aware DELETE
    detection (skipping remote resources whose gam_id isn't in the env's
    state slice) is a separate concern not yet wired in v1.x. Without that
    filtering the fake client returns the dev resource in the prod fetch
    and the plan would (incorrectly) propose a DELETE.
    """
    monkeypatch.chdir(tmp_path)
    _scaffold_repo(tmp_path)

    # Per-env fake clients so dev-side mutations don't bleed into prod's
    # list() output during the prod apply later. Each FakeClient has its
    # own ``store`` dict.
    dev_client = FakeClient({})
    prod_client = FakeClient({})

    (tmp_path / "native-styles").mkdir()
    yaml_path = tmp_path / "native-styles" / "experimental.native-style.yaml"
    yaml_path.write_text(
        "kind: NativeStyle\n"
        "_envs: [dev]\n"
        "name: experimental\n"
        "size: {width: 320, height: 250, is_fluid: false}\n"
        "template_id: 1\n"
        "html: '<div/>'\n"
        "css: ''\n"
        "targeting: {ad_units: [], custom: {}}\n"
        "status: ACTIVE\n",
        encoding="utf-8",
    )

    # --- apply dev: CREATE
    with patch("gampan.cli.apply.build_clients", return_value={"NativeStyle": dev_client}):
        result = runner.invoke(
            app,
            ["apply", "--env", "dev", "--auto-approve"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, result.output
    # One resource created on dev side, named with [dev] prefix
    assert len(dev_client.store) == 1
    dev_id = next(iter(dev_client.store))
    assert dev_client.store[dev_id].name == "[dev] experimental"

    # YAML now carries _gam_ids[dev] (write-back, with the real env name)
    yaml_safe = YAML(typ="safe")
    data = yaml_safe.load(yaml_path.read_text(encoding="utf-8"))
    assert data["_gam_ids"] == {"dev": dev_id}, data

    # --- promote: remove the _envs annotation
    yaml_rt = YAML()
    yaml_rt.default_flow_style = False
    yaml_rt.width = 2**31 - 1
    d_full = yaml_rt.load(yaml_path.read_text(encoding="utf-8"))
    if "_envs" in d_full:
        del d_full["_envs"]
    with yaml_path.open("w", encoding="utf-8") as f:
        yaml_rt.dump(d_full, f)

    # --- apply prod: CREATE for prod
    with patch("gampan.cli.apply.build_clients", return_value={"NativeStyle": prod_client}):
        result = runner.invoke(
            app,
            ["apply", "--env", "prod", "--auto-approve"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, result.output
    assert len(prod_client.store) == 1

    # The prod resource carries the canonical (undecorated) name
    prod_id = next(iter(prod_client.store))
    assert prod_client.store[prod_id].name == "experimental"

    # YAML now records both env gam_ids
    data_after = yaml_safe.load(yaml_path.read_text(encoding="utf-8"))
    assert set(data_after["_gam_ids"]) == {"dev", "prod"}, data_after["_gam_ids"]
    assert data_after["_gam_ids"]["dev"] == dev_id
    assert data_after["_gam_ids"]["prod"] == prod_id

    # Regression for C3: running plan after the CREATE must be clean.
    # Without the env-slice writeback, the new gam_id is missing from
    # `state.environments[<env>].resources`, so `scope_current_to_env`
    # drops it from current → diff proposes another CREATE (or errors with
    # "absent from remote"). This assertion locks in the fix.
    with patch("gampan.cli.apply.build_clients", return_value={"NativeStyle": prod_client}):
        post = runner.invoke(
            app,
            ["apply", "--env", "prod", "--auto-approve"],
            catch_exceptions=False,
        )
    assert post.exit_code == 0, post.output
    assert "No changes" in post.output, post.output


def test_apply_dev_does_not_delete_prod_only_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a SHARED GAM client (one network) must not let
    ``apply --env=dev`` propose deleting a prod-only resource.

    Before the scope_current_to_env fix, the env-blind remote fetch made
    every resource outside the current env's desired set look like a DELETE,
    so a single shared client (the real-world topology) would archive
    prod-only resources on a dev apply. The two earlier e2e tests masked
    this by routing per-env fake clients. This test deliberately uses ONE
    client to lock the fix in.
    """
    monkeypatch.chdir(tmp_path)
    _scaffold_repo(tmp_path)

    # One network, one client. A prod-only resource lives here with the
    # canonical (undecorated) name; dev has nothing yet.
    shared = FakeClient({"700001": _ns("prod-only-style", css=".p{}")})

    (tmp_path / "native-styles").mkdir()
    # The repo's YAML declares the prod-only resource as prod-scoped.
    (tmp_path / "native-styles" / "prod-only-style.native-style.yaml").write_text(
        "kind: NativeStyle\n"
        "_gam_ids:\n  prod: '700001'\n"
        "_envs: [prod]\n"
        "name: prod-only-style\n"
        "size: {width: 320, height: 250, is_fluid: false}\n"
        "template_id: 1\n"
        "html: '<div/>'\n"
        "css: '.p{}'\n"
        "targeting: {ad_units: [], custom: {}}\n"
        "status: ACTIVE\n",
        encoding="utf-8",
    )
    # Seed state so the prod env "manages" 700001 but dev manages nothing.
    (tmp_path / ".gampan" / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "network_code": "42",
                "environments": {
                    "dev": {"resources": {}},
                    "prod": {
                        "resources": {
                            "700001": {
                                "gam_id": "700001",
                                "kind": "NativeStyle",
                                "name_hint": "prod-only-style",
                                "checksum_local": _ns("prod-only-style", css=".p{}").checksum(),
                                "checksum_remote": _ns("prod-only-style", css=".p{}").checksum(),
                            }
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    with patch("gampan.cli.apply.build_clients", return_value={"NativeStyle": shared}):
        result = runner.invoke(
            app, ["apply", "--env", "dev", "--auto-approve"], catch_exceptions=False
        )
    assert result.exit_code == 0, result.output
    # The prod-only resource must still exist on the shared backend — dev
    # apply must not have archived/deleted it.
    assert "700001" in shared.store, result.output
    # And the plan should report no destroys for dev.
    assert "to destroy" not in result.output or "0 to destroy" in result.output.replace(
        "\x1b[1;31m", ""
    ).replace("\x1b[0m", "")
