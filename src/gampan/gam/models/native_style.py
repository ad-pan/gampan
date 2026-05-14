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
        size_raw = data["size"]
        targeting_raw = data.get("targeting", {})
        return cls(
            name=data["name"],
            size=Size(
                width=int(size_raw["width"]),
                height=int(size_raw["height"]),
                is_fluid=bool(size_raw.get("isFluid", False)),
            ),
            template_id=int(data["creativeTemplateId"]),
            html=data.get("htmlSnippet", ""),
            css=data.get("cssSnippet", ""),
            targeting=Targeting(
                ad_units=list(targeting_raw.get("adUnits", [])),
                custom=dict(targeting_raw.get("customTargeting", {})),
            ),
            status=data.get("status", "ACTIVE"),
        )

    def to_remote(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "size": {
                "width": self.size.width,
                "height": self.size.height,
                "isFluid": self.size.is_fluid,
            },
            "creativeTemplateId": self.template_id,
            "htmlSnippet": self.html,
            "cssSnippet": self.css,
            "targeting": {
                "adUnits": list(self.targeting.ad_units),
                "customTargeting": dict(self.targeting.custom),
            },
            "status": self.status,
        }

    def checksum(self) -> str:
        canonical = json.dumps(self.to_remote(), sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
