from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TransformInput:
    environment: str
    config: dict[str, Any]
    resources: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "environment": self.environment,
            "config": self.config,
            "resources": list(self.resources),
        }


@dataclass(frozen=True)
class TransformOutput:
    resources: list[dict[str, Any]]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TransformOutput":
        return cls(resources=list(payload.get("resources", [])))


@dataclass(frozen=True)
class BeforeApplyPlanAction:
    action: Literal["create", "update", "delete"]
    kind: str
    name: str
    post_transform_name: str
    gam_id: str | None
    changes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class BeforeApplyInput:
    environment: str
    config: dict[str, Any]
    plan: list[BeforeApplyPlanAction]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "environment": self.environment,
            "config": self.config,
            "plan": [asdict(a) for a in self.plan],
        }
