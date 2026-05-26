"""`gampan apply` — execute the plan."""

from __future__ import annotations

from pathlib import Path

import typer

from gampan import __version__
from gampan.cli._render import render_plan
from gampan.cli.plan import (
    _load_config,
    _load_current,
    _load_desired,
    _managed_kinds,
    build_clients,
)
from gampan.core.engine.diff import (
    CreativeTemplateReadOnlyError,
    MissingRemoteError,
    detect_remote_drift,
    validate_v0_1_constraints,
)
from gampan.core.engine.executor import execute_plan
from gampan.core.engine.planner import build_plan
from gampan.core.state.schema import State
from gampan.core.state.store import StateStore


def run(
    auto_approve: bool = typer.Option(False, "--auto-approve"),
    include_archived: bool | None = typer.Option(
        None,
        "--include-archived/--no-include-archived",
        help=(
            "Include ARCHIVED remote resources in the diff. Overrides "
            "config.include_archived for this run; falls back to the config "
            "value when omitted."
        ),
    ),
    allow_drift: bool = typer.Option(
        False,
        "--allow-drift",
        help=(
            "Proceed even if the remote diverged from state.json since the "
            "last import/apply. Without this flag, drift aborts apply so an "
            "out-of-band change (GAM UI edit, parallel apply) is not silently "
            "overwritten. With the flag, drift is printed as a warning and "
            "the apply continues."
        ),
    ),
) -> None:
    """Apply pending changes to Google Ad Manager."""
    root = Path.cwd()
    cfg = _load_config(root)
    clients = build_clients(cfg.network_code)
    effective_include_archived = (
        cfg.include_archived if include_archived is None else include_archived
    )

    # Task 13 will plumb the real --env value; until then every caller uses
    # the placeholder "default" env so identity resolution + transform hooks
    # still wire through correctly.
    desired, desired_yaml_paths = _load_desired(root, cfg, env="default")
    # Mirror ``plan``'s ``managed_kinds`` scoping — otherwise apply would
    # query every client kind, fetching resources plan never looked at and
    # silently widening the drift pre-check window.
    managed = _managed_kinds(root, desired)
    current = _load_current(
        clients,
        kinds=managed,
        include_archived=effective_include_archived,
    )

    store = StateStore(root / ".gampan" / "state.json")
    state = store.load()

    drifted = detect_remote_drift(
        {k: (v.checksum_remote, v.drift_acknowledged) for k, v in state.resources.items()},
        current,
    )
    if drifted:
        message_body = "\n".join(f"  - {k}" for k in drifted)
        if not allow_drift:
            typer.echo(
                "Error: remote drift detected since the last import/apply:\n"
                f"{message_body}\n"
                "Someone changed these resources outside this repo. Run "
                "`gampan refresh && gampan plan` to review, or rerun with "
                "`--allow-drift` to overwrite anyway.",
                err=True,
            )
            raise typer.Exit(code=1)
        typer.echo(
            "WARNING: proceeding despite remote drift on:\n"
            f"{message_body}\n"
            "These resources may be overwritten with the local YAML state.",
            err=True,
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

    render_plan(plan, show_unchanged=False)

    try:
        validate_v0_1_constraints(plan.changes)
    except CreativeTemplateReadOnlyError as e:
        typer.echo(f"\nError: {e}", err=True)
        raise typer.Exit(code=1) from e

    if not plan.has_pending:
        typer.echo("No changes.")
        # No CRUD action will touch drifted keys; ack them in the
        # already-loaded state and persist once so the operator does not
        # have to re-pass ``--allow-drift`` on the next run.
        if _ack_drifted(state, drifted):
            store.save(state)
        return

    if not auto_approve:
        confirm = typer.prompt("\nApply these changes? (yes/no)", default="no")
        if confirm.strip().lower() not in {"yes", "y"}:
            typer.echo("Aborted.")
            raise typer.Exit(code=3)

    try:
        final_state = execute_plan(
            plan,
            clients,
            store,
            tool_version=f"gampan/{__version__}",
            root=root,
            initial_state=state,
        )
        # ``_entry()`` already acks keys the executor CREATE/UPDATE'd.
        # Catch the leftover keys that drifted but were untouched by the
        # plan (drift on A, plan only changed B), then collapse the
        # drift-ack save with the executor's last save.
        if _ack_drifted(final_state, drifted):
            store.save(final_state)
        typer.echo("\nDone.")
    except Exception as e:
        typer.echo(f"\nFailed: {e}", err=True)
        raise typer.Exit(code=1) from e


def _ack_drifted(state: State, keys: list[str]) -> bool:
    """Flip ``drift_acknowledged`` to ``True`` on each listed key in place.

    Returns whether anything actually changed so callers can decide
    whether the follow-up ``store.save`` is needed.
    """
    changed = False
    for k in keys:
        entry = state.resources.get(k)
        if entry is None or entry.drift_acknowledged:
            continue
        entry.drift_acknowledged = True
        changed = True
    return changed
