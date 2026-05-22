"""Pydantic v2 model for the GAM CreativeTemplate resource."""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class Choice(BaseModel):
    """A single selectable option for a LIST (or constrained URL) TemplateVariable.

    Mirrors GAM's ``CreativeTemplateVariable.{ListString,Url}Variable.Choice``:
    the user-visible ``label`` may differ from the macro substitution ``value``.
    """

    model_config = ConfigDict(extra="forbid")
    label: str
    value: str


class TemplateVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["STRING", "URL", "LIST", "ASSET", "NUMBER"]
    required: bool = False
    description: str | None = None
    # ``default`` is the macro substitution literal. We keep it stringly-typed
    # across variants — NUMBER variables carry an int in the proto's
    # ``long_variable.default_value`` and we cast to str on import so the YAML
    # is uniform with STRING/URL/LIST defaults (and the existing checksum
    # input stays stable). ``gampan apply`` casts back where needed.
    default: str | None = None
    # LIST (and occasionally URL) variables carry a structured choice set.
    # We preserve it end-to-end so Storybook can render a real dropdown and
    # `gampan apply` can round-trip the template faithfully. Non-LIST/URL
    # variants leave this as None; LIST variants without choices are
    # admin-authored description-only variables (e.g. a TARGET_WINDOW
    # control that the operator fills in at trafficking time) — also None.
    choices: list[Choice] | None = None
    # GAM exposes `allowOtherChoice` only on list/url variants. STRING/ASSET/
    # NUMBER leave it as None so we don't pollute the YAML with an irrelevant
    # flag. LIST/URL variants always populate it (False by default).
    allow_other_choice: bool | None = None
    # ASSET variables may declare allowed MIME types (proto enum
    # ``AssetCreativeTemplateVariable.MimeType``: JPG/PNG/GIF, ...). We keep
    # the enum names verbatim so storybook-adpan can render a file-type
    # constraint without remapping to RFC mime strings. Proto-plus collapses
    # "field absent" and "explicit empty list" into ``[]``, so we treat
    # both as "any type allowed" and emit this field only when populated.
    mime_types: list[str] | None = None


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
    # Defaults to "" because native ad formats intentionally drop the snippet
    # (Google's auto-generated <table> layout) — see from_remote().
    snippet: str = ""
    variables: list[TemplateVariable] = Field(default_factory=list)
    status: Literal["ACTIVE", "INACTIVE", "DELETED"] = "ACTIVE"

    # Eligibility flags — GAM REST proto fields:
    #   interstitial            → is_interstitial   (renamed for clarity)
    #   native_eligible         → native_eligible
    #   native_video_eligible   → native_video_eligible
    #   safe_frame_compatible   → safe_frame_compatible
    # `native_eligible=True` is what marks a template as a "native ad format".
    is_interstitial: bool = False
    native_eligible: bool = False
    native_video_eligible: bool = False
    safe_frame_compatible: bool = False

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
        native_eligible = bool(data.get("native_eligible") or False)
        # Native ad formats ship with Google's stock <table> HTML snippet
        # that the GAM UI auto-generates. It is not user-editable today
        # (REST Beta has no create/update for CreativeTemplate) and pulling
        # it down adds noise to the repo, so we drop it on import. Regular
        # creative templates keep their snippet as authored.
        raw_snippet = data.get("snippet", "")
        snippet = "" if native_eligible else raw_snippet
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            type=raw_type,
            snippet=snippet,
            variables=[TemplateVariable(**v) for v in data.get("variables", [])],
            status=raw_status,
            is_interstitial=bool(data.get("is_interstitial") or False),
            native_eligible=native_eligible,
            native_video_eligible=bool(data.get("native_video_eligible") or False),
            safe_frame_compatible=bool(data.get("safe_frame_compatible") or False),
        )

    def to_remote(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "snippet": self.snippet,
            "variables": [v.model_dump(exclude_none=True) for v in self.variables],
            "status": self.status,
            "is_interstitial": self.is_interstitial,
            "native_eligible": self.native_eligible,
            "native_video_eligible": self.native_video_eligible,
            "safe_frame_compatible": self.safe_frame_compatible,
        }

    def checksum(self) -> str:
        canonical = json.dumps(self.to_remote(), sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
