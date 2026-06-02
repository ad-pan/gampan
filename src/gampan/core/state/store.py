"""Atomic read/write for `.gampan/state.json`."""

from __future__ import annotations

import os
from pathlib import Path

from gampan.core.errors import StateError
from gampan.core.state.schema import EnvironmentSlice, ResourceEntry, State


class StateStore:
    """Wraps a path to a state.json file with atomic write semantics."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> State:
        if not self.path.exists():
            raise StateError(f"state file not found: {self.path}")
        try:
            state = State.model_validate_json(self.path.read_text())
        except Exception as e:
            raise StateError(f"state file corrupted ({self.path}): {e}") from e
        return _migrate_v1_to_v2(state)

    def load_or_empty(self, network_code: str) -> State:
        if self.path.exists():
            return self.load()
        return State(network_code=network_code)

    def save(self, state: State) -> None:
        """Write atomically: tmp file + os.replace."""
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(state.model_dump_json(indent=2, exclude_none=True))
        os.replace(tmp, self.path)


def _migrate_v1_to_v2(state: State) -> State:
    """Lift v1 top-level resources into ``environments.default`` keyed by gam_id.

    v1 entries lacked the ``kind`` field (added in v2). Without it,
    ``scope_current_to_env`` treats ``entry.kind`` as falsy and filters
    every migrated entry out of multi-env plan/apply. Recover the kind
    from the v1 composite key (``NativeStyle:_gam_id:943048`` or
    ``NativeStyle:foo``) on the way in.

    No-op when ``schema_version`` is already >= 2.
    """
    if state.schema_version >= 2:
        return state
    migrated: dict[str, ResourceEntry] = {}
    for key, entry in state.resources.items():
        if entry.kind is None:
            kind_from_key = key.split(":", 1)[0] or None
            entry = entry.model_copy(update={"kind": kind_from_key})
        migrated[entry.gam_id] = entry
    default = EnvironmentSlice(
        last_apply_at=state.last_apply_at,
        last_apply_tool_version=state.last_apply_tool_version,
        resources=migrated,
    )
    return state.model_copy(
        update={
            "schema_version": 2,
            "environments": {"default": default},
            # v1 top-level fields are intentionally retained during the transitional
            # period so unmigrated callers (refresh.py, etc.) keep working. A
            # later cleanup task will remove them once every consumer reads from
            # `environments[<env>].resources` exclusively.
        }
    )
