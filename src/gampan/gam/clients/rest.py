"""REST client (google-ads-admanager) for resources with REST coverage.

NOTE: The REST API Beta exposes only `list` and `get` for CreativeTemplate.
`create`, `update`, and `archive` are not in the beta yet (verified against
google-ads-admanager 0.9). v0.1 of gampan therefore treats CreativeTemplate
as read-only on the REST path; writes will require falling through to SOAP
in v0.2 (tracked in the runbook).
"""

from __future__ import annotations

from typing import Any

from gampan.core.protocols import Resource
from gampan.gam.clients._retry import retry_transient
from gampan.gam.models.creative_template import CreativeTemplate


class CreativeTemplateRestClient:
    """Implements core.protocols.Client (read-only subset) for CreativeTemplate."""

    def __init__(self, service: Any, network_path: str) -> None:
        self._svc = service
        self._parent = network_path

    @retry_transient
    def list(self) -> list[tuple[str, Resource]]:
        out: list[tuple[str, Resource]] = []
        pager = self._svc.list_creative_templates(parent=self._parent)
        for item in pager:
            raw = _proto_to_remote_dict(item)
            gam_id = str(raw["name"]).rsplit("/", 1)[-1]
            out.append((gam_id, CreativeTemplate.from_remote(raw)))
        return out

    @retry_transient
    def get(self, gam_id: str) -> Resource:
        resp = self._svc.get_creative_template(
            name=f"{self._parent}/creativeTemplates/{gam_id}",
        )
        return CreativeTemplate.from_remote(_proto_to_remote_dict(resp))

    def create(self, resource: Resource) -> str:
        raise NotImplementedError(
            "CreativeTemplate.create is not exposed by the GAM REST Beta. "
            "v0.1 of gampan treats CreativeTemplate as read-only. "
            "Manage creative templates via the GAM UI for now; tracked for v0.2."
        )

    def update(self, gam_id: str, resource: Resource) -> None:
        raise NotImplementedError(
            "CreativeTemplate.update is not exposed by the GAM REST Beta. "
            "v0.1 of gampan treats CreativeTemplate as read-only."
        )

    def delete(self, gam_id: str) -> None:
        raise NotImplementedError(
            "CreativeTemplate.delete (archive) is not exposed by the GAM REST Beta. "
            "v0.1 of gampan treats CreativeTemplate as read-only."
        )


def _proto_to_remote_dict(item: Any) -> dict[str, Any]:
    """Convert a proto-plus CreativeTemplate message into the dict shape
    that ``CreativeTemplate.from_remote`` expects.

    Handles:
    * Enum fields (status, type_) → string names instead of integers.
    * Repeated `variables` → list of dicts with string enum types.
    """
    # Field-by-field access is more predictable than dict round-tripping
    # because enums need explicit `.name` extraction.
    type_field = getattr(item, "type_", None) or getattr(item, "type", None)
    status_field = getattr(item, "status", None)
    raw: dict[str, Any] = {
        "name": str(item.name),
        "description": str(item.description) if item.description else "",
        "snippet": str(item.snippet) if item.snippet else "",
        "type": type_field.name if type_field else "USER_DEFINED",
        "status": status_field.name if status_field else "ACTIVE",
        "variables": [_var_to_dict(v) for v in item.variables],
    }
    # Drop None values from variables (cleaner output; pydantic accepts absent optional keys)
    for var in raw["variables"]:
        for k in ("description", "default"):
            if var.get(k) is None:
                var.pop(k, None)
    return raw


def _var_to_dict(v: Any) -> dict[str, Any]:
    """Convert a proto-plus CreativeTemplateVariable into a plain dict."""
    v_type_field = getattr(v, "type_", None) or getattr(v, "type", None)
    return {
        "name": str(v.name),
        "type": v_type_field.name if v_type_field is not None else "STRING",
        "required": bool(v.required) if hasattr(v, "required") else False,
        "description": str(v.description) if getattr(v, "description", None) else None,
        "default": str(v.default) if getattr(v, "default", None) else None,
    }
