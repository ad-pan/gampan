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
    # ``True`` once an operator has consciously processed the
    # most recently observed remote state — i.e. an ``apply`` that
    # wrote the YAML to GAM, an ``import`` that pulled GAM into the
    # YAML, or the initial scaffold. ``refresh`` flips this to
    # ``False`` for any key whose remote checksum diverged so the
    # next ``apply`` cannot silently overwrite the drift just because
    # ``checksum_remote`` was already updated to the post-drift value.
    # Defaults to ``True`` so state.json files written by gampan
    # <= 0.1.x keep loading and behave like ack'd entries.
    drift_acknowledged: bool = True


class State(BaseModel):
    """The complete `.gampan/state.json` document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    network_code: str
    last_apply_at: datetime | None = None
    last_apply_tool_version: str | None = None
    resources: dict[str, ResourceEntry] = Field(default_factory=dict)
