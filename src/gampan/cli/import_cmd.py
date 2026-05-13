"""`gampan import` — pull remote resources into local YAML + state."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer
from ruamel.yaml import YAML

from gampan.core.fs.writer import write_resource
from gampan.core.protocols import Client
from gampan.core.state.schema import ResourceEntry
from gampan.core.state.store import StateStore
from gampan.gam.auth import resolve_credentials


def build_clients(network_code: str) -> dict[str, Client]:
    """Resolve credentials + construct GAM clients. Patched in tests."""
    resolve_credentials()  # raises AuthError if no creds
    # Concrete factories live in gam/clients/factory.py — see Task 25.
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
    resource: str = typer.Option(
        "all", "--resource", "-r", help="native-styles | creative-templates | all"
    ),
) -> None:
    """Pull GAM resources into YAML + populate state.json."""
    root = Path.cwd()
    cfg_path = root / ".gampan" / "config.yml"
    if not cfg_path.exists():
        typer.echo("Not a gampan repo (missing .gampan/config.yml). Run `gampan init` first.")
        raise typer.Exit(code=1)
    yaml = YAML(typ="safe")
    cfg = dict(yaml.load(cfg_path.read_text()))

    clients = build_clients(cfg["network_code"])

    store = StateStore(root / ".gampan" / "state.json")
    state = store.load_or_empty(network_code=cfg["network_code"])

    kinds = _resolve_kinds(resource)
    for kind in kinds:
        for gam_id, r in clients[kind].list():
            yaml_path = write_resource(root, r)
            cs = r.checksum()
            state.resources[f"{kind}:{r.name}"] = ResourceEntry(
                gam_id=gam_id,
                checksum_local=cs,
                checksum_remote=cs,
                last_modified_remote=datetime.now(tz=UTC),
            )
            typer.echo(f"  ✓ {yaml_path.relative_to(root)}")

    store.save(state)
    typer.echo(f"\nState: {len(state.resources)} resources tracked in .gampan/state.json")


def _resolve_kinds(resource: str) -> list[str]:
    if resource == "all":
        return ["NativeStyle", "CreativeTemplate"]
    if resource == "native-styles":
        return ["NativeStyle"]
    if resource == "creative-templates":
        return ["CreativeTemplate"]
    raise typer.BadParameter(f"unknown resource '{resource}'")
