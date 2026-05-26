"""`gampan refresh` — re-sync state.json checksums from remote."""

from __future__ import annotations

from pathlib import Path

import typer

from gampan.cli._envs import resolve_single_env
from gampan.cli.plan import _load_config, build_clients
from gampan.core.state.store import StateStore


def run(
    include_archived: bool | None = typer.Option(
        None,
        "--include-archived/--no-include-archived",
        help=(
            "Include ARCHIVED remote resources when scanning for drift. "
            "Overrides config.include_archived for this run; falls back to "
            "the config value when omitted."
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
) -> None:
    """Re-sync state.json remote checksums from the live GAM API."""
    root = Path.cwd()
    cfg = _load_config(root)
    # Task 13 plumbs --env so the CLI surface is consistent across plan /
    # apply / refresh, but the v1→v2 state migration is *additive* — Task 3
    # still populates top-level ``state.resources`` for any env we touched
    # — so refresh keeps using that flat view regardless of the requested
    # env. A future cleanup task will narrow this to ``state.environments[env]``
    # once we drop the legacy top-level slot.
    _ = resolve_single_env(cfg, env)
    effective_include_archived = (
        cfg.include_archived if include_archived is None else include_archived
    )
    clients = build_clients(cfg.network_code)

    store = StateStore(root / ".gampan" / "state.json")
    state = store.load()

    drifted: list[str] = []
    changed = False
    for kind, client in clients.items():
        for gam_id, r in client.list(include_archived=effective_include_archived):
            key = f"{kind}:{gam_id}"
            entry = state.resources.get(key)
            if entry is None:
                continue
            new_cs = r.checksum()
            if entry.checksum_remote != new_cs:
                drifted.append(key)
                entry.checksum_remote = new_cs
                # ``refresh`` records the new remote checksum so ``plan``
                # can render the drift as a normal UPDATE diff, but the
                # operator has not yet decided whether to overwrite,
                # re-import, or accept the change. Mark the entry
                # unacknowledged so the next ``apply`` still aborts
                # (or warns under ``--allow-drift``) instead of treating
                # the refreshed checksum as the new baseline.
                entry.drift_acknowledged = False
                changed = True
            if entry.gam_id != gam_id:
                entry.gam_id = gam_id
                changed = True

    if changed:
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
