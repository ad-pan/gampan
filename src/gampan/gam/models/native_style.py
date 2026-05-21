"""Pydantic v2 model for the GAM NativeStyle resource."""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class Size(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int
    height: int
    is_fluid: bool = False


class Targeting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ad_units: list[str] = Field(default_factory=list)
    custom: dict[str, list[str]] = Field(default_factory=dict)


class NativeStyle(BaseModel):
    """A GAM NativeStyle (`NativeStyleService`)."""

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "NativeStyle"

    name: str
    size: Size
    template_id: int
    html: str
    css: str
    targeting: Targeting
    status: Literal["ACTIVE", "INACTIVE", "ARCHIVED"]

    @classmethod
    def from_remote(cls, data: dict[str, Any]) -> NativeStyle:
        size_raw = data["size"] or {}
        # GAM may serialise `targeting` itself as None for unrestricted styles.
        targeting_raw = data.get("targeting") or {}
        # `isFluid` is a *top-level* field on the SOAP NativeStyle (the WSDL's
        # ``Size`` complex type only carries width/height/isAspectRatio). Read
        # it from the root, falling back to a nested location for backwards
        # compatibility with payloads emitted by gampan <= 0.1.0 that
        # mistakenly nested it under ``size``.
        is_fluid = data.get("isFluid")
        if is_fluid is None:
            is_fluid = size_raw.get("isFluid")
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
            targeting=Targeting(
                # GAM SOAP returns explicit `None` for empty repeated/map fields
                # rather than omitting them — coerce to safe empty values.
                ad_units=list(targeting_raw.get("adUnits") or []),
                custom=dict(targeting_raw.get("customTargeting") or {}),
            ),
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
        # SOAP ``Targeting`` is a deep nested type (inventoryTargeting/
        # customTargeting/geoTargeting/...) — the flat {adUnits, customTargeting}
        # shape we keep in the model and YAML is intentionally a v0.1
        # placeholder that only encodes "no targeting". For the empty case
        # we omit the field entirely so SOAP create/update succeeds; the
        # full mapping is tracked for v0.2.
        if self.targeting.ad_units or self.targeting.custom:
            payload["targeting"] = {
                "adUnits": list(self.targeting.ad_units),
                "customTargeting": dict(self.targeting.custom),
            }
        return payload

    def checksum(self) -> str:
        canonical = json.dumps(self.to_remote(), sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
