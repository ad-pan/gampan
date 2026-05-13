"""User-side `.gampan/config.yml` schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Config(BaseModel):
    """Parsed `.gampan/config.yml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    network_code: str
    env: str = "default"
    default_dry_run: bool = False
    sources: dict[str, list[str]] | list[str] | None = None
