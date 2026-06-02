"""User-side `.gampan/config.yml` schema."""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, model_validator

_log = structlog.get_logger(__name__)


class Environment(BaseModel):
    """One named environment under `environments:` in `.gampan/config.yml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    vars: dict[str, Any] = Field(default_factory=dict)


class HookSubconfig(BaseModel):
    """Per-subcommand hook override (e.g. `transform`, `before-apply`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str


class HookConfig(BaseModel):
    """`hook:` block in `.gampan/config.yml`.

    Keys with dashes ("before-apply", "reverse-transform") are accepted as
    YAML aliases; Python attribute access uses the underscore form.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    # Fallback path used for any subcommand without its own block (spec §5.1 / §6.2).
    path: str | None = None
    transform: HookSubconfig | None = None
    reverse_transform: HookSubconfig | None = Field(default=None, alias="reverse-transform")
    before_apply: HookSubconfig | None = Field(default=None, alias="before-apply")


class Config(BaseModel):
    """Parsed `.gampan/config.yml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    network_code: str
    # v1 legacy. Kept so existing configs still load, but emits a deprecation
    # warning on construction and is otherwise ignored — use `environments:`
    # in v1.x.
    env: str | None = None
    default_dry_run: bool = False
    sources: dict[str, list[str]] | list[str] | None = None
    # When False (default), `gampan import` and `gampan plan` skip ARCHIVED
    # remote resources entirely. Set True to manage them — needed when a
    # NativeStyle YAML carries ``status: ARCHIVED`` so plan can still resolve
    # the remote counterpart instead of erroring with a "filtered by
    # include_archived" guard. CLI flags ``--include-archived`` /
    # ``--no-include-archived`` override this per-invocation.
    include_archived: bool = False

    environments: dict[str, Environment] = Field(default_factory=dict)
    hook: HookConfig | None = None

    @model_validator(mode="after")
    def _warn_on_legacy_env(self) -> Config:
        if self.env is not None:
            _log.warning(
                "the `env:` field is deprecated in v1.x and ignored; "
                "declare `environments:` instead"
            )
        return self
