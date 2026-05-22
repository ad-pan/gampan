"""Pydantic v2 model for the GAM NativeStyle resource."""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from gampan.core.errors import GampanError


class LegacyTargetingError(GampanError):
    """Raised when a YAML carries gampan<=0.1.x's lossy
    ``targeting: {ad_units, custom}`` shape with non-empty content.

    The old shape silently dropped GAM's nested ``Targeting`` complex type
    (inventoryTargeting/customTargeting/geoTargeting/...) on import. Letting
    a populated legacy YAML round-trip through ``to_remote`` would replace
    the real remote targeting with an empty payload on the next apply.
    Refuse the load and ask the caller to re-import.
    """


class Size(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int
    height: int
    is_fluid: bool = False


class NativeStyle(BaseModel):
    """A GAM NativeStyle (`NativeStyleService`)."""

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "NativeStyle"

    name: str
    size: Size
    template_id: int
    html: str
    css: str
    # SOAP ``Targeting`` is a deep nested complex type
    # (inventoryTargeting/customTargeting/geoTargeting/...). v0.1 keeps the
    # entire payload verbatim so import → apply round-trips losslessly
    # without us re-implementing GAM's matchers; a friendlier user-facing
    # schema is tracked for v0.2. ``None`` means "no targeting object" —
    # rare in practice because GAM almost always returns the wrapper even
    # when every sub-field is empty.
    targeting: dict[str, Any] | None = None
    status: Literal["ACTIVE", "INACTIVE", "ARCHIVED"]

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_targeting(cls, data: Any) -> Any:
        # YAMLs written by gampan<=0.1.x carried ``targeting: {ad_units,
        # custom}``. Empty payloads (the only thing the old code could
        # produce) are silently rewritten to ``None`` because nothing was
        # ever encoded; any non-empty legacy payload would have been a lie
        # already, so refuse rather than apply a destructive empty
        # targeting to the remote.
        if not isinstance(data, dict):
            return data
        t = data.get("targeting")
        if isinstance(t, dict) and ("ad_units" in t or "custom" in t):
            has_payload = bool(t.get("ad_units")) or bool(t.get("custom"))
            if has_payload:
                raise LegacyTargetingError(
                    "YAML carries gampan<=0.1.x targeting shape "
                    "({ad_units, custom}) with content. That shape was "
                    "a lossy placeholder; re-run `gampan import` to refresh "
                    "the targeting from SOAP before applying."
                )
            data["targeting"] = None
        return data

    @classmethod
    def from_remote(cls, data: dict[str, Any]) -> NativeStyle:
        size_raw = data["size"] or {}
        # `isFluid` is a *top-level* field on the SOAP NativeStyle (the WSDL's
        # ``Size`` complex type only carries width/height/isAspectRatio). Read
        # it from the root, falling back to a nested location for backwards
        # compatibility with payloads emitted by gampan <= 0.1.0 that
        # mistakenly nested it under ``size``.
        is_fluid = data.get("isFluid")
        if is_fluid is None:
            is_fluid = size_raw.get("isFluid")
        targeting_raw = data.get("targeting")
        return cls(
            name=data["name"],
            size=Size(
                width=int(size_raw["width"]),
                height=int(size_raw["height"]),
                is_fluid=bool(is_fluid or False),
            ),
            template_id=int(data["creativeTemplateId"]),
            html=data.get("htmlSnippet") or "",
            css=data.get("cssSnippet") or "",
            targeting=targeting_raw if isinstance(targeting_raw, dict) else None,
            status=data.get("status") or "ACTIVE",
        )

    def to_remote(self) -> dict[str, Any]:
        # `isFluid` lives at the NativeStyle root in the SOAP WSDL — putting
        # it inside ``size`` (whose XSD doesn't declare the field) makes
        # googleads' SOAP packer raise KeyError('isFluid') during create/update.
        payload: dict[str, Any] = {
            "name": self.name,
            "size": {
                "width": self.size.width,
                "height": self.size.height,
            },
            "isFluid": self.size.is_fluid,
            "creativeTemplateId": self.template_id,
            "htmlSnippet": self.html,
            "cssSnippet": self.css,
            "status": self.status,
        }
        if self.targeting is not None:
            # Round-trip the SOAP `Targeting` payload verbatim so apply does
            # not overwrite remote targeting we never decoded into the model.
            payload["targeting"] = self.targeting
        return payload

    def checksum(self) -> str:
        canonical = json.dumps(self.to_remote(), sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
