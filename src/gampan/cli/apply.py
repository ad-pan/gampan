"""`gampan apply` — execute the plan."""

from __future__ import annotations

from pathlib import Path

import typer

from gampan import __version__
from gampan.cli.plan import _load_config, _load_current, _load_desired, build_clients
from gampan.core.engine.executor import execute_plan
from gampan.core.engine.planner import build_plan
from gampan.core.state.store import StateStore


def run(
    auto_approve: bool = typer.Option(False, "--auto-approve"),
) -> None:
    """Apply pending changes to Google Ad Manager."""
    root = Path.cwd()
    cfg = _load_config(root)
    clients = build_clients(cfg.network_code)

    desired = _load_desired(root, cfg)
    current = _load_current(clients)
    plan = build_plan(desired=desired, current=current)

    from gampan.cli._render import render_plan

    render_plan(plan, show_unchanged=False)

    if not plan.has_pending:
        typer.echo("No changes.")
        return

    if not auto_approve:
        confirm = typer.prompt("\nApply these changes? (yes/no)", default="no")
        if confirm.strip().lower() not in {"yes", "y"}:
            typer.echo("Aborted.")
            raise typer.Exit(code=3)

    store = StateStore(root / ".gampan" / "state.json")
    try:
        execute_plan(plan, clients, store, tool_version=f"gampan/{__version__}")
        typer.echo("\nDone.")
    except Exception as e:
        typer.echo(f"\nFailed: {e}", err=True)
        raise typer.Exit(code=1) from e
