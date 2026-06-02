from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResolvedResource:
    gam_id: str | None
    create_intent: bool
    envs: list[str] | None        # None ⇒ "participate in all declared envs"
    from_legacy_scalar: bool
    payload: dict[str, Any]       # raw dict with gampan-managed metadata stripped


_MANAGED_KEYS = ("_gam_ids", "_gam_id", "_envs")


def resolve_identity(raw: dict[str, Any], env: str) -> ResolvedResource:
    """Read gampan-managed metadata, decide identity, return a clean payload.

    Strips `_gam_ids`, `_gam_id`, `_envs` from the returned payload so the
    hook (and downstream stages) see a clean resource.
    """
    gam_ids_dict = raw.get("_gam_ids")
    scalar_gam_id = raw.get("_gam_id")
    envs = raw.get("_envs")

    gam_id: str | None = None
    from_scalar = False
    if isinstance(gam_ids_dict, dict):
        gam_id = gam_ids_dict.get(env)
    elif scalar_gam_id is not None:
        # legacy v1 scalar: same id in every env the resource participates in
        gam_id = str(scalar_gam_id)
        from_scalar = True

    payload = {k: v for k, v in raw.items() if k not in _MANAGED_KEYS}
    return ResolvedResource(
        gam_id=gam_id,
        create_intent=gam_id is None,
        envs=list(envs) if isinstance(envs, list) else None,
        from_legacy_scalar=from_scalar,
        payload=payload,
    )
