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


_VARIANT_TYPE_MAP = {
    "string_variable": "STRING",
    "url_variable": "URL",
    "list_string_variable": "LIST",
    "asset_variable": "ASSET",
    "long_variable": "STRING",  # no LONG in our model; degrade to STRING for v0.1
}


def _var_to_dict(v: Any) -> dict[str, Any]:
    """Convert a REST CreativeTemplateVariable (proto-plus oneof) into the dict shape
    that ``CreativeTemplate.TemplateVariable.from_remote`` expects.

    The REST schema uses a oneof over ``{string,url,list_string,asset,long}_variable``
    plus shared ``label`` / ``unique_display_name`` / ``description`` / ``required``
    fields. Our flat model has ``name`` / ``type`` / ``description`` / ``required`` /
    ``default``. The default value lives inside the variant subtype.
    """
    # Pick the active oneof variant via proto's WhichOneof if available;
    # otherwise probe each candidate.
    variant_name: str | None = None
    variant: Any = None
    pb = getattr(v, "_pb", None)
    if pb is not None:
        try:
            variant_name = pb.WhichOneof("variable_value_type")
        except Exception:  # pragma: no cover - safety net
            variant_name = None
    if variant_name is None:
        for cand in _VARIANT_TYPE_MAP:
            sub = getattr(v, cand, None)
            if sub is not None and getattr(sub, "_pb", None) is not None and sub._pb.ByteSize():
                variant_name = cand
                variant = sub
                break
    if variant is None and variant_name is not None:
        variant = getattr(v, variant_name, None)

    var_type = _VARIANT_TYPE_MAP.get(variant_name or "", "STRING")
    name = str(getattr(v, "unique_display_name", "") or getattr(v, "label", "")) or "(unnamed)"
    default_raw = getattr(variant, "default_value", None) if variant is not None else None
    default = str(default_raw) if default_raw not in (None, "") else None

    return {
        "name": name,
        "type": var_type,
        "required": bool(getattr(v, "required", False)),
        "description": str(v.description) if getattr(v, "description", None) else None,
        "default": default,
    }
