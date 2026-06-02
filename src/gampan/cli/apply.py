"""`gampan apply` — execute the plan."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

import typer

from gampan import __version__
from gampan.cli._envs import resolve_single_env
from gampan.cli._render import render_plan
from gampan.cli.plan import (
    _load_config,
    _load_current,
    _load_desired,
    _managed_kinds,
    build_clients,
    scope_current_to_env,
)
from gampan.core.engine.diff import (
    Action,
    CreativeTemplateReadOnlyError,
    FieldDiff,
    MissingRemoteError,
    detect_remote_drift,
    validate_v0_1_constraints,
)
from gampan.core.engine.executor import execute_plan
from gampan.core.engine.planner import Plan, build_plan
from gampan.core.hooks.contract import BeforeApplyInput, BeforeApplyPlanAction
from gampan.core.hooks.discover import resolve_hook_path
from gampan.core.hooks.invoke import HookCrash, HookRejected, invoke_hook
from gampan.core.state.schema import State
from gampan.core.state.store import StateStore

# Resource fields whose values are large enough (HTML/CSS template bodies)
# that shipping them verbatim through the hook envelope would balloon the
# payload and leak sensitive snippet content. Hash these to a short digest
# so the hook can still detect "this body changed" without seeing it.
_BLOB_FIELD_NAMES = {"html", "css", "snippet", "htmlSnippet", "cssSnippet"}


def _is_blob_path(path: str) -> bool:
    """Whether the final segment of ``path`` is a known blob field."""
    # path looks like "html" or "variables[2].default" — split on "." and "["
    # and check the rightmost identifier.
    tail = path.rsplit(".", 1)[-1]
    tail = tail.split("[", 1)[0]
    return tail in _BLOB_FIELD_NAMES


def _hash_value(value: Any) -> str:
    digest = hashlib.sha256(str(value).encode()).hexdigest()[:16]
    return f"<sha256:{digest}>"


def _diff_to_change_entry(diff: FieldDiff) -> dict[str, Any]:
    if _is_blob_path(diff.path):
        return {
            "path": diff.path,
            "before": _hash_value(diff.before) if diff.before is not None else None,
            "after": _hash_value(diff.after) if diff.after is not None else None,
        }
    return {"path": diff.path, "before": diff.before, "after": diff.after}


def _action_label(action: Action) -> Literal["create", "update", "delete"]:
    mapping: dict[Action, Literal["create", "update", "delete"]] = {
        Action.CREATE: "create",
        Action.UPDATE: "update",
        Action.DELETE: "delete",
    }
    return mapping[action]


def _build_before_apply_actions(plan: Plan) -> list[BeforeApplyPlanAction]:
    out: list[BeforeApplyPlanAction] = []
    for change in plan.changes:
        if change.action == Action.NO_CHANGE:
            continue
        kind = change.key.split(":", 1)[0]
        # For DELETE, ``desired`` is None — fall back to the remote model's name.
        # ``current`` is always populated on UPDATE/DELETE; ``desired`` on
        # CREATE/UPDATE. At least one is set for any non-NO_CHANGE row.
        name_source = change.desired if change.desired is not None else change.current
        assert name_source is not None, f"change {change.key} has neither desired nor current"
        name = name_source.name
        out.append(
            BeforeApplyPlanAction(
                action=_action_label(change.action),
                kind=kind,
                name=name,
                post_transform_name=name,
                gam_id=change.gam_id,
                changes=[_diff_to_change_entry(d) for d in change.diffs],
            )
        )
    return out


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
    env: str | None = typer.Option(
        None,
        "-e",
        "--env",
        help=(
            "Target environment (must be a key under `environments:` in "
            ".gampan/config.yml). Required when environments are declared; "
            "ignored in v1 single-env mode. apply intentionally has no "
            "--all-envs flag — multi-env apply is out of scope for v1.x "
            "(blast-radius safety)."
        ),
    ),
) -> None:
    """Apply pending changes to Google Ad Manager."""
    root = Path.cwd()
    cfg = _load_config(root)
    target_env = resolve_single_env(cfg, env)
    clients = build_clients(cfg.network_code)
    effective_include_archived = (
        cfg.include_archived if include_archived is None else include_archived
    )

    desired, desired_yaml_paths = _load_desired(root, cfg, env=target_env)
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

    # Restrict the env-blind remote fetch to the resources this env manages,
    # so resources owned by *other* envs never surface as spurious DELETEs.
    current = scope_current_to_env(current, state, target_env, cfg)

    # Build the expected-checksum map drift detection compares against.
    # In multi-env mode the env-slice (``state.environments[<env>].resources``)
    # is the source of truth — the legacy flat ``state.resources`` is empty
    # after a multi-env import, so reading from it would silently disable
    # drift detection entirely. Single-env (v1) repos still use the flat map.
    if cfg.environments:
        slice_ = state.environments.get(target_env)
        expected = (
            {
                f"{e.kind}:{gid}": (e.checksum_remote, e.drift_acknowledged)
                for gid, e in slice_.resources.items()
                if e.kind
            }
            if slice_
            else {}
        )
    else:
        expected = {
            k: (v.checksum_remote, v.drift_acknowledged)
            for k, v in state.resources.items()
        }
    drifted = detect_remote_drift(expected, current)
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

    # Policy gate. The user already approved interactively; the hook gets the
    # last word so org-wide rules (e.g. "no DELETE in prod", "size budget")
    # can stop the mutation even when a human said yes. Skipped when there
    # is nothing actionable to gate.
    env_vars: dict[str, Any] = {}
    if target_env in cfg.environments:
        env_vars = dict(cfg.environments[target_env].vars)
    hook_path = resolve_hook_path(root, cfg.hook, "before-apply")
    if hook_path is not None:
        bai = BeforeApplyInput(
            environment=target_env,
            config={"network_code": cfg.network_code, "vars": env_vars},
            plan=_build_before_apply_actions(plan),
        )
        try:
            invoke_hook(
                hook_path=hook_path,
                subcommand="before-apply",
                payload=bai.to_payload(),
            )
        except HookRejected as rej:
            typer.echo(
                f"Apply rejected by before-apply hook: {rej.reason}", err=True
            )
            raise typer.Exit(code=3) from rej
        except HookCrash as crash:
            typer.echo(
                f"Apply aborted: before-apply hook crashed: {crash}", err=True
            )
            raise typer.Exit(code=1) from crash

    try:
        final_state = execute_plan(
            plan,
            clients,
            store,
            tool_version=f"gampan/{__version__}",
            root=root,
            initial_state=state,
            env=target_env,
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
