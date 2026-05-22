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
                # ``refresh`` records the new remote checksum so ``plan`` can
                # surface the drift as a normal UPDATE diff — but the operator
                # has not yet decided whether to overwrite, re-import, or
                # accept the change. Mark the entry unacknowledged so the next
                # ``apply`` aborts (or warns under ``--allow-drift``) instead
                # of treating the post-refresh checksum as the new baseline.
                entry.drift_acknowledged = False
            entry.checksum_remote = new_cs
            entry.gam_id = gam_id  # heal any drifted ID

    store.save(state)

    if drifted:
        typer.echo("Drift detected (remote changed since last apply):")
        for k in drifted:
            typer.echo(f"  {k}")
        typer.echo(
            "\nNext: run `gampan plan` to inspect the diff, then either "
            "`gampan import` to absorb the remote, `gampan apply --allow-drift` "
            "to overwrite with the YAML, or edit the YAML to reconcile."
        )
    else:
        typer.echo("No drift.")
