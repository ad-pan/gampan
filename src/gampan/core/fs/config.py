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
    # When False (default), `gampan import` and `gampan plan` skip ARCHIVED
    # remote resources entirely. Set True to manage them — needed when a
    # NativeStyle YAML carries ``status: ARCHIVED`` so plan can still resolve
    # the remote counterpart instead of erroring with a "filtered by
    # include_archived" guard. CLI flags ``--include-archived`` /
    # ``--no-include-archived`` override this per-invocation.
    include_archived: bool = False
