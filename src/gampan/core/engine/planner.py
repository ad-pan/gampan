"""Wrap diff_resources output into a Plan with summary helpers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from gampan.core.engine.diff import Action, Change, diff_resources
from gampan.core.protocols import Resource


class Plan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    changes: list[Change]

    @property
    def has_pending(self) -> bool:
        return any(c.action != Action.NO_CHANGE for c in self.changes)

    def summary(self) -> dict[Action, int]:
        out = {a: 0 for a in Action}
        for c in self.changes:
            out[c.action] += 1
        return out


def build_plan(
    desired: list[tuple[str, Resource]],  # (state_key, model)
    current: dict[str, tuple[str, Resource]],  # state_key → (gam_id, model)
    *,
    strict_missing_remote: bool = False,
) -> Plan:
    return Plan(
        changes=diff_resources(
            desired, current, strict_missing_remote=strict_missing_remote
        )
    )
