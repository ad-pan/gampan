"""Compute changes between desired (YAML) and current (state + remote)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from gampan.core.protocols import Resource


class Action(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NO_CHANGE = "NO_CHANGE"


class Change(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    action: Action
    key: str  # "<kind>:<name>"
    gam_id: str | None  # None for CREATE
    desired: Resource | None
    current: Resource | None
    diff_summary: list[str]


def _key(r: Resource) -> str:
    return f"{r.kind}:{r.name}"


def _field_diff(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Return short '<field> changed' lines for the differing keys."""
    out: list[str] = []
    keys = sorted(set(a.keys()) | set(b.keys()))
    for k in keys:
        if a.get(k) != b.get(k):
            out.append(f"  {k} changed")
    return out


def diff_resources(
    desired: list[Resource],
    current: dict[str, tuple[str, Resource]],  # key → (gam_id, model)
) -> list[Change]:
    """Produce ordered Change list. Order: CREATE, UPDATE, NO_CHANGE, DELETE."""
    changes: list[Change] = []
    desired_keys = {_key(r) for r in desired}

    for r in desired:
        key = _key(r)
        if key not in current:
            changes.append(
                Change(
                    action=Action.CREATE,
                    key=key,
                    gam_id=None,
                    desired=r,
                    current=None,
                    diff_summary=[],
                )
            )
        else:
            gam_id, cur = current[key]
            if r.checksum() == cur.checksum():
                changes.append(
                    Change(
                        action=Action.NO_CHANGE,
                        key=key,
                        gam_id=gam_id,
                        desired=r,
                        current=cur,
                        diff_summary=[],
                    )
                )
            else:
                changes.append(
                    Change(
                        action=Action.UPDATE,
                        key=key,
                        gam_id=gam_id,
                        desired=r,
                        current=cur,
                        diff_summary=_field_diff(cur.to_remote(), r.to_remote()),
                    )
                )

    for key, (gam_id, cur) in current.items():
        if key not in desired_keys:
            changes.append(
                Change(
                    action=Action.DELETE,
                    key=key,
                    gam_id=gam_id,
                    desired=None,
                    current=cur,
                    diff_summary=[],
                )
            )

    return changes
