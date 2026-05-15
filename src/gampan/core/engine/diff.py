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


class FieldDiff(BaseModel):
    """A single field-level difference between current and desired state."""

    path: str  # e.g. "description" or "variables[2].default"
    before: Any  # current (remote) value; None means field absent
    after: Any  # desired value; None means field absent


class Change(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    action: Action
    key: str  # "<kind>:<name>"
    gam_id: str | None  # None for CREATE
    desired: Resource | None
    current: Resource | None
    diffs: list[FieldDiff] = []
    # Kept for backward compatibility — mirrors diffs as "<path> changed" strings.
    diff_summary: list[str] = []


def _key(r: Resource) -> str:
    return f"{r.kind}:{r.name}"


def _field_diff(
    a: dict[str, Any],
    b: dict[str, Any],
    prefix: str = "",
) -> list[FieldDiff]:
    """Recursively compute field-level diffs between dicts *a* (before) and *b* (after).

    For list fields, diffs are generated index-wise.  When lengths differ the
    extra / missing items are recorded as individual FieldDiff entries with
    before=None or after=None respectively.
    """
    out: list[FieldDiff] = []
    keys = sorted(set(a.keys()) | set(b.keys()))
    for k in keys:
        path = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        val_a = a.get(k)
        val_b = b.get(k)
        if val_a == val_b:
            continue
        if isinstance(val_a, dict) and isinstance(val_b, dict):
            out.extend(_field_diff(val_a, val_b, prefix=path))
        elif isinstance(val_a, list) and isinstance(val_b, list):
            out.extend(_list_diff(val_a, val_b, path))
        else:
            out.append(FieldDiff(path=path, before=val_a, after=val_b))
    return out


def _list_diff(a: list[Any], b: list[Any], prefix: str) -> list[FieldDiff]:
    """Diff two lists index-wise, descending into dicts where possible."""
    out: list[FieldDiff] = []
    max_len = max(len(a), len(b))
    for i in range(max_len):
        path = f"{prefix}[{i}]"
        if i >= len(a):
            out.append(FieldDiff(path=path, before=None, after=b[i]))
        elif i >= len(b):
            out.append(FieldDiff(path=path, before=a[i], after=None))
        elif a[i] != b[i]:
            if isinstance(a[i], dict) and isinstance(b[i], dict):
                out.extend(_field_diff(a[i], b[i], prefix=path))
            else:
                out.append(FieldDiff(path=path, before=a[i], after=b[i]))
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
                    diffs=[],
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
                        diffs=[],
                        diff_summary=[],
                    )
                )
            else:
                field_diffs = _field_diff(cur.to_remote(), r.to_remote())
                changes.append(
                    Change(
                        action=Action.UPDATE,
                        key=key,
                        gam_id=gam_id,
                        desired=r,
                        current=cur,
                        diffs=field_diffs,
                        diff_summary=[f"  {d.path} changed" for d in field_diffs],
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
                    diffs=[],
                    diff_summary=[],
                )
            )

    return changes
