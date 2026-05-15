"""Pydantic v2 model for the GAM CreativeTemplate resource."""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class TemplateVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["STRING", "URL", "LIST", "ASSET"]
    required: bool = False
    description: str | None = None
    default: str | None = None


_TYPE_VALUES = {"STANDARD", "CUSTOM"}
_STATUS_VALUES = {"ACTIVE", "INACTIVE", "DELETED"}


class CreativeTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "CreativeTemplate"

    name: str
    description: str = ""
    # Aligned to the REST API enum (STANDARD/CUSTOM). The SOAP API uses
    # USER_DEFINED/SYSTEM_DEFINED — when v0.2 adds the SOAP write path for
    # CreativeTemplate, the converter there must remap to these values.
    type: Literal["STANDARD", "CUSTOM"] = "CUSTOM"
    snippet: str
    variables: list[TemplateVariable] = Field(default_factory=list)
    status: Literal["ACTIVE", "INACTIVE", "DELETED"] = "ACTIVE"

    @classmethod
    def from_remote(cls, data: dict[str, Any]) -> CreativeTemplate:
        # Normalise UNSPECIFIED / unknown enum values to sensible defaults so
        # `import` is permissive about whatever Google's API hands back.
        raw_type = data.get("type", "CUSTOM")
        if raw_type not in _TYPE_VALUES:
            raw_type = "CUSTOM"
        raw_status = data.get("status", "ACTIVE")
        if raw_status not in _STATUS_VALUES:
            raw_status = "ACTIVE"
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            type=raw_type,
            snippet=data.get("snippet", ""),
            variables=[TemplateVariable(**v) for v in data.get("variables", [])],
            status=raw_status,
        )

    def to_remote(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "snippet": self.snippet,
            "variables": [v.model_dump(exclude_none=True) for v in self.variables],
            "status": self.status,
        }

    def checksum(self) -> str:
        canonical = json.dumps(self.to_remote(), sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
