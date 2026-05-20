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
            # gam_id is the trailing numeric id on the GAM resource path;
            # display_name is the user-friendly label and drives our model's `name`.
            gam_id = str(item.name).rsplit("/", 1)[-1]
            raw = _proto_to_remote_dict(item)
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

    The proto's ``name`` is a GAM resource path
    (``networks/<n>/creativeTemplates/<id>``). The user-friendly label is
    in ``display_name``. We use ``display_name`` for our model's ``name``
    field — the gam_id (already on each state.json entry) carries identity.
    Fallback to the numeric id when ``display_name`` is empty.

    Handles:
    * Enum fields (status, type_) → string names instead of integers.
    * Repeated `variables` → list of dicts with string enum types.
    """
    type_field = getattr(item, "type_", None) or getattr(item, "type", None)
    status_field = getattr(item, "status", None)
    display = str(getattr(item, "display_name", "") or "").strip()
    if not display:
        display = str(item.name).rsplit("/", 1)[-1]
    raw: dict[str, Any] = {
        "name": display,
        "description": str(item.description) if item.description else "",
        "snippet": str(item.snippet) if item.snippet else "",
        "type": type_field.name if type_field else "CUSTOM",
        "status": status_field.name if status_field else "ACTIVE",
        "variables": [_var_to_dict(v) for v in item.variables],
        # Eligibility flags. Proto field for `is_interstitial` is `interstitial`
        # (without the `is_` prefix); the rest match.
        "is_interstitial": bool(getattr(item, "interstitial", False)),
        "native_eligible": bool(getattr(item, "native_eligible", False)),
        "native_video_eligible": bool(getattr(item, "native_video_eligible", False)),
        "safe_frame_compatible": bool(getattr(item, "safe_frame_compatible", False)),
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
    "long_variable": "NUMBER",
}

# Subset of variants that carry a structured `choices` array + `allow_other_choice`
# flag. Other variants (string/asset/long) don't expose these fields on the
# REST oneof, so we don't probe for them.
_VARIANTS_WITH_CHOICES = {"list_string_variable", "url_variable"}


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
        except (ValueError, Exception):
            variant_name = None
        # The google-ads-admanager generated proto models variant subtypes as
        # PLAIN optional message fields, not a oneof. WhichOneof returns None
        # even when one IS set — including the important case of an empty
        # asset_variable (File variable with no mime_type constraints).
        # HasField correctly reports presence for both set-empty and
        # set-with-content submessages.
        if variant_name is None:
            for cand in _VARIANT_TYPE_MAP:
                try:
                    if pb.HasField(cand):
                        variant_name = cand
                        break
                except ValueError:
                    continue
    # ByteSize probe fallback for test mocks that don't carry a real _pb.
    # Real GAM responses don't take this path — _pb is always present.
    if variant_name is None:
        for cand in _VARIANT_TYPE_MAP:
            sub = getattr(v, cand, None)
            if sub is None:
                continue
            sub_pb = getattr(sub, "_pb", None)
            if sub_pb is None:
                continue
            try:
                if sub_pb.ByteSize():
                    variant_name = cand
                    variant = sub
                    break
            except Exception:
                continue
    if variant is None and variant_name is not None:
        variant = getattr(v, variant_name, None)

    var_type = _VARIANT_TYPE_MAP.get(variant_name or "", "STRING")
    name = str(getattr(v, "unique_display_name", "") or getattr(v, "label", "")) or "(unnamed)"
    default_raw = getattr(variant, "default_value", None) if variant is not None else None
    # NUMBER variables carry an int (proto ``long_variable.default_value``); the
    # value ``0`` is meaningful (e.g. zero-pixel border) so we explicitly keep
    # it instead of treating it as "absent" the way we do for empty strings.
    if default_raw is None:
        default = None
    elif isinstance(default_raw, (int, float)) and not isinstance(default_raw, bool):
        default = str(default_raw)
    elif default_raw == "":
        default = None
    else:
        default = str(default_raw)

    # Extract structured choices for variants that expose them. The variant
    # subtype has a repeated `choices` field (each {label, value}) plus
    # `allow_other_choice`. Absent or empty choices leave the flat fields
    # at their defaults so we don't pollute YAML with empty lists.
    choices: list[dict[str, str]] | None = None
    allow_other_choice: bool | None = None
    if variant is not None and variant_name in _VARIANTS_WITH_CHOICES:
        raw_choices = getattr(variant, "choices", None) or []
        extracted = [
            {
                "label": str(getattr(c, "label", "") or ""),
                "value": str(getattr(c, "value", "") or ""),
            }
            for c in raw_choices
        ]
        if extracted:
            choices = extracted
        allow_other_choice = bool(getattr(variant, "allow_other_choice", False))

    # ASSET variables may declare allowed MIME types via the proto enum
    # ``AssetCreativeTemplateVariable.MimeType`` (JPG/PNG/GIF, ...). We
    # preserve enum *names* — not RFC mime strings — so the YAML stays
    # stable across SDK enum-number reshuffles and round-trips identically
    # on apply. proto-plus collapses "field absent" and "explicit empty
    # list" into ``[]``; we emit the field only when populated to keep
    # the YAML quiet for the common any-type-allowed case.
    mime_types: list[str] | None = None
    if variant is not None and variant_name == "asset_variable":
        raw_mt = getattr(variant, "mime_types", None) or []
        extracted_mt: list[str] = []
        for m in raw_mt:
            # proto-plus exposes enums as objects with `.name`; allow
            # raw strings too in case a future SDK surfaces them flat.
            nm = getattr(m, "name", None)
            extracted_mt.append(str(nm) if nm is not None else str(m))
        if extracted_mt:
            mime_types = extracted_mt

    out: dict[str, Any] = {
        "name": name,
        "type": var_type,
        "required": bool(getattr(v, "required", False)),
        "description": str(v.description) if getattr(v, "description", None) else None,
        "default": default,
    }
    if choices is not None:
        out["choices"] = choices
    if allow_other_choice is not None:
        out["allow_other_choice"] = allow_other_choice
    if mime_types is not None:
        out["mime_types"] = mime_types
    return out
