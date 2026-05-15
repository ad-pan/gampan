"""Execute a Plan against typed Clients, persisting state after each action."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from gampan.core.engine.diff import Action
from gampan.core.engine.planner import Plan
from gampan.core.protocols import Client, Resource
from gampan.core.state.schema import ResourceEntry
from gampan.core.state.store import StateStore


def execute_plan(
    plan: Plan,
    client_by_kind: Mapping[str, Client],
    store: StateStore,
    tool_version: str,
) -> None:
    state = store.load()
    state.last_apply_tool_version = tool_version

    try:
        for change in plan.changes:
            if change.action == Action.NO_CHANGE:
                continue
            kind, _, _ = change.key.partition(":")
            client = client_by_kind[kind]

            if change.action == Action.CREATE:
                assert change.desired is not None
                gam_id = client.create(change.desired)
                state.resources[change.key] = _entry(gam_id, change.desired)
            elif change.action == Action.UPDATE:
                assert change.desired is not None and change.gam_id is not None
                client.update(change.gam_id, change.desired)
                state.resources[change.key] = _entry(change.gam_id, change.desired)
            elif change.action == Action.DELETE:
                assert change.gam_id is not None
                client.delete(change.gam_id)
                state.resources.pop(change.key, None)

            state.last_apply_at = datetime.now(tz=UTC)
            store.save(state)
    finally:
        # Final save even if the loop raised — captures everything completed so far.
        store.save(state)


def _entry(gam_id: str, resource: Resource) -> ResourceEntry:
    cs = resource.checksum()
    return ResourceEntry(
        gam_id=gam_id,
        checksum_local=cs,
        checksum_remote=cs,
        last_modified_remote=datetime.now(tz=UTC),
    )
