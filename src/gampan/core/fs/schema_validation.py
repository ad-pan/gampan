"""Cross-language schema validation against `@ad-pan/schema` JSON Schemas.

Pydantic remains the Python-side source of truth. This module is a parallel
tripwire: it validates each loaded resource dict against the canonical JSON
Schema emitted from TypeSpec at ``@ad-pan/schema``. If the two ever drift
(e.g. a field added to Pydantic but not mirrored in TypeSpec), validation
fails loudly at load time.

Resolution strategy for the schema directory:

1. ``ADPAN_SCHEMA_DIR`` env var, if set (absolute or repo-root-relative).
2. Sibling checkout at ``../schema/tsp-output/json-schema`` (relative to
   the gampan repo root).
3. Missing: emit a single structlog warning and skip validation. This
   keeps gampan buildable on a fresh checkout before the schema repo has
   been ``npm run build``-ed.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gampan.core.errors import SchemaError

_log = structlog.get_logger(__name__)

# Internal sentinel for "we already warned; don't keep yelling".
_MISSING_WARNED: dict[str, bool] = {}

# Fields gampan injects at load time that are not part of the canonical
# wire schema. They must be tolerated by validation without forcing the
# JSON Schema to know about them.
_LOADER_INJECTED_FIELDS: tuple[str, ...] = ("__source__",)


def resolve_schema_dir(repo_root: Path) -> Path | None:
    """Return the directory containing emitted JSON Schemas, or None."""
    env = os.environ.get("ADPAN_SCHEMA_DIR")
    if env:
        candidate = Path(env)
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        return candidate if candidate.is_dir() else None

    # Sibling repo layout: <workspace>/gampan and <workspace>/schema.
    sibling = (repo_root / ".." / "schema" / "tsp-output" / "json-schema").resolve()
    if sibling.is_dir():
        return sibling
    return None


@lru_cache(maxsize=1)
def _load_registry(schema_dir_str: str) -> tuple[Registry[Any], dict[str, dict[str, Any]]]:
    """Build a ``referencing`` Registry over every ``*.json`` in the schema dir.

    Returns the registry plus a ``{$id: schema}`` index so callers can look up
    the root schema for a given kind without re-reading the filesystem.
    """
    schema_dir = Path(schema_dir_str)
    index: dict[str, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[Any]]] = []
    for path in sorted(schema_dir.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            schema = json.load(f)
        schema_id = schema.get("$id", path.name)
        index[schema_id] = schema
        # Cross-file $refs in the emitted schemas are bare filenames
        # (e.g. "Size.json"), so we register each resource under its $id.
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        resources.append((schema_id, resource))
    registry: Registry[Any] = Registry().with_resources(resources)
    return registry, index


@lru_cache(maxsize=32)
def _validator_for(schema_dir_str: str, kind: str) -> Draft202012Validator | None:
    """Return a validator for the given kind, or None if no schema file exists."""
    registry, index = _load_registry(schema_dir_str)
    schema = index.get(f"{kind}.json")
    if schema is None:
        return None
    return Draft202012Validator(schema, registry=registry)


def validate_resource(data: dict[str, Any], repo_root: Path) -> None:
    """Validate ``data`` against the JSON Schema for its ``kind``.

    No-op when:
      - schema dir cannot be resolved (warns once)
      - there is no schema file matching the ``kind``

    Raises ``SchemaError`` on validation failure, citing the source file
    and the JSON path within the document.
    """
    schema_dir = resolve_schema_dir(repo_root)
    if schema_dir is None:
        key = str(repo_root)
        if not _MISSING_WARNED.get(key):
            _MISSING_WARNED[key] = True
            _log.warning(
                "adpan_schema_dir_missing",
                hint=(
                    "Set ADPAN_SCHEMA_DIR or place the schema repo as a sibling "
                    "checkout (../schema). Skipping JSON Schema validation."
                ),
            )
        return

    kind = data.get("kind")
    if not isinstance(kind, str):
        # Caller (loader) is responsible for the missing-kind error path;
        # we only validate when there is a kind to look up.
        return

    validator = _validator_for(str(schema_dir), kind)
    if validator is None:
        # Unknown kind on the schema side — not our error to raise. Pydantic
        # will reject it downstream, or it will simply be unsupported.
        return

    # Strip loader-injected fields for validation purposes; restore after.
    to_check = {k: v for k, v in data.items() if k not in _LOADER_INJECTED_FIELDS}

    errors: list[ValidationError] = sorted(
        validator.iter_errors(to_check), key=lambda e: list(e.absolute_path)
    )
    if not errors:
        return

    source = data.get("__source__", "<unknown>")
    lines = [f"{source}: JSON Schema validation failed against {kind}.json"]
    for err in errors:
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        lines.append(f"  - at '{path}': {err.message}")
    raise SchemaError("\n".join(lines))
