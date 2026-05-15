"""`gampan refresh` — re-sync state.json checksums from remote."""

from __future__ import annotations

from pathlib import Path

import typer
from ruamel.yaml import YAML

from gampan.cli.plan import build_clients
from gampan.core.fs.config import Config
from gampan.core.state.store import StateStore


def run() -> None:
    """Re-sync state.json remote checksums from the live GAM API."""
    root = Path.cwd()
    yaml = YAML(typ="safe")
    cfg = Config.model_validate(yaml.load((root / ".gampan" / "config.yml").read_text()))
    clients = build_clients(cfg.network_code)

    store = StateStore(root / ".gampan" / "state.json")
    state = store.load()

    drifted: list[str] = []
    for kind, client in clients.items():
        for gam_id, r in client.list():
            key = f"{kind}:{gam_id}"
            entry = state.resources.get(key)
            if entry is None:
                continue
            new_cs = r.checksum()
            if entry.checksum_remote != new_cs:
                drifted.append(key)
            entry.checksum_remote = new_cs
            entry.gam_id = gam_id  # heal any drifted ID

    store.save(state)

    if drifted:
        typer.echo("Drift detected (remote changed since last apply):")
        for k in drifted:
            typer.echo(f"  {k}")
    else:
        typer.echo("No drift.")
