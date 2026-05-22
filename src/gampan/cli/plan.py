"""`gampan plan` — show pending changes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer
from ruamel.yaml import YAML

from gampan.cli._render import render_plan, render_summary
from gampan.core.engine.diff import (
    NEW_KEY_MARKER,
    CreativeTemplateReadOnlyError,
    MissingRemoteError,
    validate_v0_1_constraints,
)
from gampan.core.engine.planner import build_plan
from gampan.core.fs.config import Config
from gampan.core.fs.loader import load_all, validate_no_duplicates
from gampan.core.fs.writer import slugify
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
) -> None:
    """Show pending changes between local YAML and the remote GAM state."""
    root = Path.cwd()
    cfg = _load_config(root)
    clients = build_clients(cfg.network_code)
    effective_include_archived = (
        cfg.include_archived if include_archived is None else include_archived
    )

    desired, desired_yaml_paths = _load_desired(root, cfg)
    # Only query kinds we actually manage (kinds present in desired YAMLs OR
    # in state.json from a prior import). Skipping unmanaged kinds avoids
    # unnecessary SOAP/REST traffic and keeps `gampan plan` cassette-friendly.
    managed_kinds = _managed_kinds(root, desired)
    current = _load_current(
        clients,
        kinds=managed_kinds,
        include_archived=effective_include_archived,
    )
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
        typer.echo(
            json.dumps(
                {
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
                },
                indent=2,
            )
        )
    else:
        render_plan(plan, show_unchanged=show_unchanged)
        render_summary(plan)

    if detailed_exitcode and plan.has_pending:
        raise typer.Exit(code=2)


def _load_config(root: Path) -> Config:
    yaml = YAML(typ="safe")
    return Config.model_validate(yaml.load((root / ".gampan" / "config.yml").read_text()))


def _load_desired(root: Path, cfg: Config) -> tuple[list[tuple[str, Resource]], dict[str, str]]:
    """Load YAML resources and return ``(desired, yaml_paths)``.

    ``desired`` is a list of ``(state_key, model)`` pairs; ``yaml_paths``
    maps each state key to the repo-relative source file. State key is
    ``{kind}:{gam_id}`` for imported YAMLs (those carrying a ``_gam_id``
    field), or ``{kind}:NEW:{slug}-{hash8}`` for user-authored YAMLs that
    have never been imported. The ``NEW:`` prefix ensures they always
    appear as CREATE in the plan; the executor uses ``yaml_paths`` on
    CREATE to stamp the newly-assigned ``_gam_id`` back into the source
    file.
    """
    raw = load_all(root, cfg)
    validate_no_duplicates(raw)
    out: list[tuple[str, Resource]] = []
    paths: dict[str, str] = {}
    for item in raw:
        source = item.get("__source__")
        item = {k: v for k, v in item.items() if not k.startswith("__")}
        kind = item.pop("kind")
        gam_id: str | None = item.pop("_gam_id", None)
        if kind == "NativeStyle":
            model: Resource = NativeStyle(**item)
        elif kind == "CreativeTemplate":
            model = CreativeTemplate(**item)
        else:
            continue
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
