"""Schema for `.gampan/state.json`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResourceEntry(BaseModel):
    """Per-resource entry tracking GAM id + drift checksums."""

    model_config = ConfigDict(extra="forbid")

    gam_id: str
    checksum_local: str
    checksum_remote: str
    last_modified_remote: datetime | None = None


class State(BaseModel):
    """The complete `.gampan/state.json` document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    network_code: str
    last_apply_at: datetime | None = None
    last_apply_tool_version: str | None = None
    resources: dict[str, ResourceEntry] = Field(default_factory=dict)
