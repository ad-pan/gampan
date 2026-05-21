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
    # Repo-relative source path for the YAML that produced this change, when
    # the change originates from a desired-side YAML (CREATE / UPDATE /
    # NO_CHANGE). DELETE rows never carry a path — the YAML is gone. The
    # executor uses this on CREATE to stamp ``_gam_id`` back into the file
    # so the next ``plan`` recognises the newly-imported resource by id
    # instead of treating it as another fresh CREATE candidate.
    yaml_path: str | None = None


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


class MissingRemoteError(ValueError):
    """Raised when a YAML carries a real ``_gam_id`` but the remote lookup
    returned no matching resource. Almost always means the resource was
    filtered out by ``include_archived=False`` — flipping the flag (or
    ``--include-archived`` on the CLI) is the standard recovery."""


def diff_resources(
    desired: list[tuple[str, Resource]],  # (state_key, model)
    current: dict[str, tuple[str, Resource]],  # state_key → (gam_id, model)
    *,
    strict_missing_remote: bool = False,
    desired_yaml_paths: dict[str, str] | None = None,
) -> list[Change]:
    """Produce ordered Change list. Order: CREATE, UPDATE, NO_CHANGE, DELETE.

    ``desired`` is a list of ``(state_key, resource)`` pairs where
    ``state_key`` is ``"{kind}:{gam_id}"`` for imported resources or a
    synthetic ``"{kind}:NEW:..."`` key for user-authored ones.  This decouples
    identity from the display name so Korean / duplicate names don't collide.

    ``strict_missing_remote`` guards against the ``include_archived=False``
    foot-gun: when an imported YAML (one whose ``state_key`` carries a real
    gam_id, not the ``NEW:`` prefix) has no matching remote, the caller almost
    certainly filtered it out. Re-creating it would clone the resource under
    a new gam_id, so we raise instead and ask the caller to opt back in.

    ``desired_yaml_paths`` maps each desired ``state_key`` to its
    repo-relative source path; the executor needs this on CREATE to stamp
    ``_gam_id`` back into the YAML so the resource is recognised by id on
    the next ``plan``.
    """
    changes: list[Change] = []
    desired_keys = {key for key, _ in desired}
    paths = desired_yaml_paths or {}

    for key, r in desired:
        if key not in current:
            if strict_missing_remote and ":NEW:" not in key:
                raise MissingRemoteError(
                    f"{key}: tracked in YAML but absent from the remote lookup. "
                    "ARCHIVED resources are filtered by default — rerun with "
                    "`--include-archived` (or set `include_archived: true` in "
                    ".gampan/config.yml) if this resource is intentionally archived."
                )
            changes.append(
                Change(
                    action=Action.CREATE,
                    key=key,
                    gam_id=None,
                    desired=r,
                    current=None,
                    diffs=[],
                    diff_summary=[],
                    yaml_path=paths.get(key),
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
                        yaml_path=paths.get(key),
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
                        yaml_path=paths.get(key),
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
