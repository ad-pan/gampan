"""`gampan plan` — show pending changes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer
from ruamel.yaml import YAML

from gampan.cli._envs import resolve_plan_targets
from gampan.cli._render import render_plan, render_summary
from gampan.core.engine.diff import (
    NEW_KEY_MARKER,
    CreativeTemplateReadOnlyError,
    MissingRemoteError,
    validate_v0_1_constraints,
)
from gampan.core.engine.planner import build_plan
from gampan.core.env.filter import participates_in_env
from gampan.core.fs.config import Config
from gampan.core.fs.loader import load_all, validate_no_duplicates
from gampan.core.fs.writer import slugify
from gampan.core.hooks.contract import TransformInput, TransformOutput
from gampan.core.hooks.discover import resolve_hook_path
from gampan.core.hooks.invoke import invoke_hook
from gampan.core.identity.resolve import resolve_identity
from gampan.core.protocols import Client, Resource
from gampan.gam.auth import resolve_credentials
from gampan.gam.models.creative_template import CreativeTemplate
from gampan.gam.models.native_style import NativeStyle


def build_clients(network_code: str) -> Mapping[str, Client]:
    """Resolve credentials + construct GAM clients. Patched in tests."""
    creds = resolve_credentials()
    from gampan.gam.clients.adapter import build_client_map
    from gampan.gam.clients.factory import (
        rest_client_factory,
        soap_client_factory,
    )

    return build_client_map(
        soap_factory=lambda: soap_client_factory(network_code, creds),
        rest_factory=lambda: rest_client_factory(network_code, creds),
    )


def run(
    detailed_exitcode: bool = typer.Option(
        True,
        "--detailed-exitcode/--simple-exitcode",
        help="Exit 2 when there are pending changes (default on).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    show_unchanged: bool = typer.Option(
        False,
        "-u",
        "--show-unchanged",
        help="Print NO_CHANGE rows too.",
    ),
    include_archived: bool | None = typer.Option(
        None,
        "--include-archived/--no-include-archived",
        help=(
            "Include ARCHIVED remote resources in the diff. Overrides "
            "config.include_archived for this run; falls back to the config "
            "value when omitted."
        ),
    ),
    env: str | None = typer.Option(
        None,
        "-e",
        "--env",
        help=(
            "Target environment (must be a key under `environments:` in "
            ".gampan/config.yml). Required when environments are declared; "
            "ignored in v1 single-env mode."
        ),
    ),
    all_envs: bool = typer.Option(
        False,
        "--all-envs",
        help=(
            "Plan every declared environment in turn. Mutually exclusive "
            "with --env. Ignored in v1 single-env mode."
        ),
    ),
) -> None:
    """Show pending changes between local YAML and the remote GAM state."""
    root = Path.cwd()
    cfg = _load_config(root)
    targets = resolve_plan_targets(cfg, env, all_envs=all_envs)
    clients = build_clients(cfg.network_code)
    effective_include_archived = (
        cfg.include_archived if include_archived is None else include_archived
    )
    # State drives env-scoped DELETE detection (see scope_current_to_env).
    # Load once; reused across every target env in the loop below.
    from gampan.core.state.store import StateStore

    state_store = StateStore(root / ".gampan" / "state.json")
    plan_state = state_store.load_or_empty(network_code=cfg.network_code)

    any_pending = False
    multi = len(targets) > 1

    # Build a single JSON envelope across all targets when --json is on so
    # downstream consumers get one parse instead of one-per-env.
    json_envelopes: list[dict[str, Any]] = []

    for target_env in targets:
        if multi and not as_json:
            typer.echo(f"=== env: {target_env} ===")

        desired, desired_yaml_paths = _load_desired(root, cfg, env=target_env)
        # Only query kinds we actually manage (kinds present in desired YAMLs OR
        # in state.json from a prior import). Skipping unmanaged kinds avoids
        # unnecessary SOAP/REST traffic and keeps `gampan plan` cassette-friendly.
        managed_kinds = _managed_kinds(root, desired)
        current = _load_current(
            clients,
            kinds=managed_kinds,
            include_archived=effective_include_archived,
        )
        # Drop resources owned by other envs so they don't appear as DELETEs.
        current = scope_current_to_env(current, plan_state, target_env, cfg)
        try:
            plan = build_plan(
                desired=desired,
                current=current,
                strict_missing_remote=not effective_include_archived,
                desired_yaml_paths=desired_yaml_paths,
            )
        except MissingRemoteError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e

        # v0.1 backend constraint: CreativeTemplate write verbs are not exposed.
        # Render the plan so the operator can see the would-be diff, then refuse.
        try:
            validate_v0_1_constraints(plan.changes)
        except CreativeTemplateReadOnlyError as e:
            render_plan(plan, show_unchanged=show_unchanged)
            typer.echo(f"\nError: {e}", err=True)
            raise typer.Exit(code=1) from e

        if as_json:
            json_envelopes.append(
                {
                    "env": target_env,
                    "summary": {a.value: n for a, n in plan.summary().items()},
                    "changes": [
                        {
                            "action": c.action,
                            "key": c.key,
                            "diffs": [
                                {"path": d.path, "before": d.before, "after": d.after}
                                for d in c.diffs
                            ],
                        }
                        for c in plan.changes
                    ],
                }
            )
        else:
            render_plan(plan, show_unchanged=show_unchanged)
            render_summary(plan)

        if plan.has_pending:
            any_pending = True

    if as_json:
        # Single-env mode: preserve the v1 flat shape so existing JSON
        # consumers keep working. Multi-env mode emits a list keyed by env.
        if multi:
            typer.echo(json.dumps({"envs": json_envelopes}, indent=2))
        else:
            envelope = json_envelopes[0]
            typer.echo(
                json.dumps(
                    {"summary": envelope["summary"], "changes": envelope["changes"]},
                    indent=2,
                )
            )

    if detailed_exitcode and any_pending:
        raise typer.Exit(code=2)


def _load_config(root: Path) -> Config:
    yaml = YAML(typ="safe")
    return Config.model_validate(yaml.load((root / ".gampan" / "config.yml").read_text()))


def _load_desired(
    root: Path, cfg: Config, env: str
) -> tuple[list[tuple[str, Resource]], dict[str, str]]:
    """Load YAML resources for ``env`` and return ``(desired, yaml_paths)``.

    Pipeline:
        1. Read every YAML via :func:`load_all` and reject duplicates.
        2. For each item, resolve identity (``_gam_ids``/``_gam_id`` →
           ``gam_id`` for ``env``) and filter out resources whose ``_envs``
           does not include ``env``.
        3. Hand the survivors' clean payloads to the user's ``transform``
           hook (if configured) along with ``cfg.environments[env].vars``.
        4. Pair surviving identities to transformed payloads positionally
           (gampan v1.x requires the hook to preserve resource count).
        5. Build Pydantic models and assign state keys
           (``{kind}:{gam_id}`` for known ids, ``{kind}:NEW:{slug}-{hash8}``
           otherwise).
    """
    raw = load_all(root, cfg)
    validate_no_duplicates(raw)

    # Stage 1: identity resolve + env filter. Keep (resolved, source) pairs.
    survivors: list[tuple[Any, str | None]] = []  # tuple[ResolvedResource, source]
    for item in raw:
        source = item.get("__source__")
        cleaned = {k: v for k, v in item.items() if not k.startswith("__")}
        resolved = resolve_identity(cleaned, env=env)
        if not participates_in_env(resolved.envs, env):
            continue
        survivors.append((resolved, source))

    # Stage 2: transform hook. Pass-through when no hook is configured.
    env_vars: dict[str, Any] = {}
    if env in cfg.environments:
        env_vars = dict(cfg.environments[env].vars)
    ti = TransformInput(
        environment=env,
        config={"network_code": cfg.network_code, "vars": env_vars},
        resources=[r.payload for (r, _) in survivors],
    )
    hook_path = resolve_hook_path(root, cfg.hook, "transform")
    out_payload = invoke_hook(
        hook_path=hook_path, subcommand="transform", payload=ti.to_payload()
    )
    transformed = TransformOutput.from_payload(out_payload).resources

    if len(transformed) != len(survivors):
        raise ValueError(
            f"transform hook returned {len(transformed)} resources from "
            f"{len(survivors)}; gampan v1.x requires preservation "
            f"(the hook must return the same number of resources in the same order)"
        )

    # Stage 3: pair, build models, assign state keys.
    out: list[tuple[str, Resource]] = []
    paths: dict[str, str] = {}
    for (resolved, source), payload in zip(survivors, transformed, strict=True):
        item_payload = dict(payload)
        kind = item_payload.pop("kind")
        # Strip any leaked managed metadata the hook may have re-emitted —
        # state key comes from the pre-hook identity, not the payload.
        for managed in ("_gam_id", "_gam_ids", "_envs"):
            item_payload.pop(managed, None)
        if kind == "NativeStyle":
            model: Resource = NativeStyle(**item_payload)
        elif kind == "CreativeTemplate":
            model = CreativeTemplate(**item_payload)
        else:
            continue
        gam_id = resolved.gam_id
        if gam_id:
            key = f"{kind}:{gam_id}"
        else:
            # User-authored YAML — stable synthetic key so re-runs are idempotent.
            name_slug = slugify(model.name) or "unnamed"
            name_hash = hashlib.sha256(model.name.encode()).hexdigest()[:8]
            key = f"{kind}{NEW_KEY_MARKER}{name_slug}-{name_hash}"
        out.append((key, model))
        if source:
            paths[key] = source
    return out, paths


def _load_current(
    clients: Mapping[str, Client],
    kinds: set[str] | None = None,
    *,
    include_archived: bool = False,
) -> dict[str, tuple[str, Any]]:
    """Fetch remote resources for the given kinds.

    When ``kinds`` is None, fetch every kind known to ``clients`` (legacy
    behaviour, used by callers that already know they want everything).
    """
    target = kinds if kinds is not None else set(clients)
    current: dict[str, tuple[str, Any]] = {}
    for kind in target:
        if kind not in clients:
            continue
        for gam_id, r in clients[kind].list(include_archived=include_archived):
            current[f"{kind}:{gam_id}"] = (gam_id, r)
    return current


def scope_current_to_env(
    current: dict[str, tuple[str, Any]],
    state: Any,
    env: str,
    cfg: Config,
) -> dict[str, tuple[str, Any]]:
    """Restrict the remote ``current`` map to the resources *env* manages.

    GAM is a single network: ``_load_current`` fetches every remote resource
    of the managed kinds, env-blind. In multi-env mode that would make every
    resource not in the current env's desired set look like a DELETE — e.g.
    ``apply --env=dev`` would propose archiving every prod-only resource.

    The per-env source of truth for "what this env manages" is its state
    slice (spec §5.4). We keep only the remote entries whose gam_id appears in
    ``state.environments[env].resources``; everything else is another env's
    concern and is excluded so it can never surface as a DELETE.

    v1 single-env mode (no ``environments:`` declared) is unaffected — every
    remote resource belongs to the one env, so the full map passes through.
    """
    if not cfg.environments:
        return current
    slice_ = state.environments.get(env)
    if slice_ is None:
        managed: set[str] = set()
    else:
        managed = {
            f"{entry.kind}:{gid}"
            for gid, entry in slice_.resources.items()
            if entry.kind
        }
    return {k: v for k, v in current.items() if k in managed}


def _managed_kinds(root: Path, desired: list[tuple[str, Resource]]) -> set[str]:
    """Set of kinds the user manages: any kind present in local YAML OR
    referenced by an entry in state.json from a prior import."""
    kinds: set[str] = {item[0].partition(":")[0] for item in desired}
    state_path = root / ".gampan" / "state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError):
            state = {}
        for key in state.get("resources", {}):
            kind = key.partition(":")[0]
            if kind:
                kinds.add(kind)
    return kinds
