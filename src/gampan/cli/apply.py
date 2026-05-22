"""`gampan apply` — execute the plan."""

from __future__ import annotations

from pathlib import Path

import typer

from gampan import __version__
from gampan.cli.plan import _load_config, _load_current, _load_desired, build_clients
from gampan.core.engine.diff import (
    CreativeTemplateReadOnlyError,
    MissingRemoteError,
    detect_remote_drift,
    validate_v0_1_constraints,
)
from gampan.core.engine.executor import execute_plan
from gampan.core.engine.planner import build_plan
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

    desired, desired_yaml_paths = _load_desired(root, cfg)
    current = _load_current(clients, include_archived=effective_include_archived)

    # Drift pre-check: compare the just-fetched remote checksums against the
    # state.json snapshot left by the previous import/apply. A mismatch means
    # someone — the GAM UI, another apply, or an out-of-band SDK call —
    # touched a resource since we last looked. Without the guard, build_plan
    # would happily re-emit the YAML state and silently overwrite that
    # change. With ``--allow-drift`` the operator can override after eyeballing
    # the diff.
    store = StateStore(root / ".gampan" / "state.json")
    state_snapshot = store.load()
    drifted = detect_remote_drift(
        {
            k: (v.checksum_remote, v.drift_acknowledged)
            for k, v in state_snapshot.resources.items()
        },
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

    from gampan.cli._render import render_plan

    render_plan(plan, show_unchanged=False)

    # v0.1 backend constraint: CreativeTemplate is read-only via REST.
    # Refuse before executor so a half-applied state cannot happen.
    try:
        validate_v0_1_constraints(plan.changes)
    except CreativeTemplateReadOnlyError as e:
        typer.echo(f"\nError: {e}", err=True)
        raise typer.Exit(code=1) from e

    if not plan.has_pending:
        typer.echo("No changes.")
        # No CRUD action will touch the drifted keys, so executor's per-action
        # _entry() rewrite cannot ack them. Reset the flag here so the operator
        # does not have to pass ``--allow-drift`` again on the next run.
        if drifted:
            _ack_drift_keys(store, drifted)
        return

    if not auto_approve:
        confirm = typer.prompt("\nApply these changes? (yes/no)", default="no")
        if confirm.strip().lower() not in {"yes", "y"}:
            typer.echo("Aborted.")
            raise typer.Exit(code=3)

    try:
        execute_plan(
            plan,
            clients,
            store,
            tool_version=f"gampan/{__version__}",
            root=root,
        )
        # executor's _entry() already sets drift_acknowledged=True for keys it
        # CREATE/UPDATE'd. Catch any leftover drifted keys that the plan did
        # not touch (e.g. drift on resource A, plan only changed resource B)
        # so the operator's ``--allow-drift`` decision sticks across runs.
        if drifted:
            _ack_drift_keys(store, drifted)
        typer.echo("\nDone.")
    except Exception as e:
        typer.echo(f"\nFailed: {e}", err=True)
        raise typer.Exit(code=1) from e


def _ack_drift_keys(store: StateStore, keys: list[str]) -> None:
    state = store.load()
    changed = False
    for k in keys:
        entry = state.resources.get(k)
        if entry is None or entry.drift_acknowledged:
            continue
        entry.drift_acknowledged = True
        changed = True
    if changed:
        store.save(state)
