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


class CreativeTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[Literal["CreativeTemplate"]] = "CreativeTemplate"

    name: str
    description: str = ""
    type: Literal["USER_DEFINED", "SYSTEM_DEFINED"] = "USER_DEFINED"
    snippet: str
    variables: list[TemplateVariable] = Field(default_factory=list)
    status: Literal["ACTIVE", "INACTIVE", "ARCHIVED"] = "ACTIVE"

    @classmethod
    def from_remote(cls, data: dict[str, Any]) -> CreativeTemplate:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            type=data.get("type", "USER_DEFINED"),
            snippet=data.get("snippet", ""),
            variables=[TemplateVariable(**v) for v in data.get("variables", [])],
            status=data.get("status", "ACTIVE"),
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
