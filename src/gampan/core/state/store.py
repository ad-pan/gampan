"""Atomic read/write for `.gampan/state.json`."""

from __future__ import annotations

import os
from pathlib import Path

from gampan.core.errors import StateError
from gampan.core.state.schema import State


class StateStore:
    """Wraps a path to a state.json file with atomic write semantics."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> State:
        if not self.path.exists():
            raise StateError(f"state file not found: {self.path}")
        try:
            return State.model_validate_json(self.path.read_text())
        except Exception as e:
            raise StateError(f"state file corrupted ({self.path}): {e}") from e

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
