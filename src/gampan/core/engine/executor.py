"""Execute a Plan against typed Clients, persisting state after each action."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from ruamel.yaml import YAML

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
    root: Path | None = None,
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
                # Rebind the state key from the synthetic ``NEW:`` slug to
                # the real gam_id so subsequent plans match the YAML by
                # identity, not by "I've never seen this before".
                new_key = f"{kind}:{gam_id}"
                state.resources.pop(change.key, None)
                state.resources[new_key] = _entry(gam_id, change.desired)
                # Stamp the gam_id back into the source YAML for the same
                # reason — without it, _load_desired still treats the file
                # as a brand-new resource on the next run.
                if root is not None and change.yaml_path is not None:
                    _write_gam_id_back(root / change.yaml_path, gam_id)
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


def _write_gam_id_back(yaml_path: Path, gam_id: str) -> None:
    """Insert ``_gam_id: '<id>'`` immediately after ``kind:`` in ``yaml_path``.

    Uses ruamel's round-trip loader so comments, ordering, and the
    ``!file`` reference style survive. A no-op when ``_gam_id`` is already
    present (e.g. a partially-applied CREATE that we are retrying).
    """
    yaml = YAML()  # round-trip mode preserves user formatting
    yaml.preserve_quotes = True
    data = yaml.load(yaml_path.read_text(encoding="utf-8"))
    if data is None or "_gam_id" in data:
        return
    # Rebuild the mapping with ``_gam_id`` right after ``kind`` for
    # readability — ruamel's CommentedMap accepts ``insert(index, key,
    # value)`` to splice without losing trailing comments.
    keys = list(data.keys())
    insert_at = (keys.index("kind") + 1) if "kind" in keys else 0
    data.insert(insert_at, "_gam_id", str(gam_id))
    with yaml_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
