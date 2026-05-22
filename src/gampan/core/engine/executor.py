"""Execute a Plan against typed Clients, persisting state after each action."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML

from gampan.core.engine.diff import Action
from gampan.core.engine.planner import Plan
from gampan.core.protocols import Client, Resource
from gampan.core.state.schema import ResourceEntry, State
from gampan.core.state.store import StateStore

# Round-trip YAML loader reused across CREATE writebacks. ruamel keeps no
# per-call state on the loader itself (state lives on the returned
# CommentedMap), so a single shared instance is safe and avoids repeating
# the (non-trivial) representer/constructor registration per action.
_RT_YAML = YAML()
_RT_YAML.preserve_quotes = True


def execute_plan(
    plan: Plan,
    client_by_kind: Mapping[str, Client],
    store: StateStore,
    tool_version: str,
    root: Path | None = None,
    initial_state: State | None = None,
) -> State:
    """Run *plan* against *client_by_kind* and persist progress.

    Returns the mutated ``State`` so callers (e.g. ``apply``) can keep
    operating on the same in-memory object instead of round-tripping
    through ``store.load()`` for a follow-up edit.

    Pass ``initial_state`` to skip the otherwise-mandatory ``store.load()``
    when the caller already has a fresh snapshot.
    """
    state = initial_state if initial_state is not None else store.load()
    state.last_apply_tool_version = tool_version

    completed = False
    try:
        for change in plan.changes:
            if change.action == Action.NO_CHANGE:
                continue
            kind, _, _ = change.key.partition(":")
            client = client_by_kind[kind]

            if change.action == Action.CREATE:
                assert change.desired is not None
                gam_id = client.create(change.desired)
                # Rebind the synthetic ``NEW:`` key to the real gam_id and
                # stamp it into the source YAML; otherwise the next plan
                # still sees a brand-new resource and tries to create a
                # duplicate.
                new_key = f"{kind}:{gam_id}"
                state.resources.pop(change.key, None)
                state.resources[new_key] = _entry(gam_id, change.desired)
                if root is not None and change.yaml_path is not None:
                    _write_gam_id_back(root / change.yaml_path, gam_id)
            elif change.action == Action.UPDATE:
                assert change.desired is not None and change.gam_id is not None
                client.update(change.gam_id, change.desired)
                state.resources[change.key] = _entry(change.gam_id, change.desired)
            elif change.action == Action.DELETE:
                assert change.gam_id is not None
                # GAM has no hard-delete; ``client.delete`` archives. Skip
                # the RPC when the remote is already ARCHIVED so apply does
                # not flood the API with idempotent no-ops while flushing
                # leftover rows from state.json.
                already_archived = getattr(change.current, "status", None) == "ARCHIVED"
                if not already_archived:
                    client.delete(change.gam_id)
                state.resources.pop(change.key, None)

            state.last_apply_at = datetime.now(tz=UTC)
            store.save(state)
        completed = True
    finally:
        # Only flush on exception — the in-loop save already covers the
        # happy path. Without the guard, every clean apply incurs one
        # extra atomic write of identical bytes.
        if not completed:
            store.save(state)
    return state


def _entry(gam_id: str, resource: Resource) -> ResourceEntry:
    cs = resource.checksum()
    return ResourceEntry(
        gam_id=gam_id,
        checksum_local=cs,
        checksum_remote=cs,
        last_modified_remote=datetime.now(tz=UTC),
        # Explicit so a future tightening of the schema default (e.g.
        # ``drift_acknowledged: bool = False``) does not silently turn
        # every fresh apply into an unacknowledged drift.
        drift_acknowledged=True,
    )


def _write_gam_id_back(yaml_path: Path, gam_id: str) -> None:
    """Insert ``_gam_id: '<id>'`` immediately after ``kind:`` in ``yaml_path``.

    Uses the shared round-trip loader so comments, ordering, and the
    ``!file`` reference style survive. A no-op when ``_gam_id`` is already
    present (e.g. a partially-applied CREATE that we are retrying).
    """
    data = _RT_YAML.load(yaml_path.read_text(encoding="utf-8"))
    if data is None or "_gam_id" in data:
        return
    keys = list(data.keys())
    insert_at = (keys.index("kind") + 1) if "kind" in keys else 0
    data.insert(insert_at, "_gam_id", str(gam_id))
    with yaml_path.open("w", encoding="utf-8") as f:
        _RT_YAML.dump(data, f)
