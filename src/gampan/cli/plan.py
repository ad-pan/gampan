"""`gampan plan` — show pending changes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from ruamel.yaml import YAML

from gampan.core.engine.planner import build_plan
from gampan.core.fs.config import Config
from gampan.core.fs.loader import load_all, validate_no_duplicates
from gampan.core.protocols import Client, Resource
from gampan.gam.auth import resolve_credentials
from gampan.gam.models.creative_template import CreativeTemplate
from gampan.gam.models.native_style import NativeStyle


def build_clients(network_code: str) -> dict[str, Client]:
    """Resolve credentials + construct GAM clients. Patched in tests."""
    resolve_credentials()  # raises AuthError if no creds
    from gampan.gam.clients.adapter import build_client_map
    from gampan.gam.clients.factory import (
        rest_client_factory,
        soap_client_factory,
    )

    return build_client_map(
        soap_factory=lambda: soap_client_factory(network_code),
        rest_factory=lambda: rest_client_factory(network_code),
    )


def run(
    detailed_exitcode: bool = typer.Option(
        True,
        "--detailed-exitcode/--simple-exitcode",
        help="Exit 2 when there are pending changes (default on).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show pending changes between local YAML and the remote GAM state."""
    root = Path.cwd()
    cfg = _load_config(root)
    clients = build_clients(cfg.network_code)

    desired = _load_desired(root, cfg)
    current = _load_current(clients)
    plan = build_plan(desired=desired, current=current)

    if as_json:
        typer.echo(
            json.dumps(
                {
                    "summary": {a.value: n for a, n in plan.summary().items()},
                    "changes": [{"action": c.action, "key": c.key} for c in plan.changes],
                },
                indent=2,
            )
        )
    else:
        for c in plan.changes:
            typer.echo(f"  {c.action.value:9s} {c.key}")
        typer.echo("")
        for action, count in plan.summary().items():
            typer.echo(f"{action.value}: {count}")

    if detailed_exitcode and plan.has_pending:
        raise typer.Exit(code=2)


def _load_config(root: Path) -> Config:
    yaml = YAML(typ="safe")
    return Config.model_validate(yaml.load((root / ".gampan" / "config.yml").read_text()))


def _load_desired(root: Path, cfg: Config) -> list[Resource]:
    raw = load_all(root, cfg)
    validate_no_duplicates(raw)
    out: list[Resource] = []
    for item in raw:
        item = {k: v for k, v in item.items() if not k.startswith("__")}
        kind = item.pop("kind")
        if kind == "NativeStyle":
            out.append(NativeStyle(**item))
        elif kind == "CreativeTemplate":
            out.append(CreativeTemplate(**item))
    return out


def _load_current(clients: dict[str, Client]) -> dict[str, tuple[str, Any]]:
    current: dict[str, tuple[str, Any]] = {}
    for kind, client in clients.items():
        for gam_id, r in client.list():
            current[f"{kind}:{r.name}"] = (gam_id, r)
    return current
