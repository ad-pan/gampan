"""Glob + YAML → raw dicts (kind-discriminated) for the engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gampan.core.errors import SchemaError
from gampan.core.fs.config import Config
from gampan.core.fs.refs import make_yaml
from gampan.core.fs.schema_validation import validate_resource

# Per-kind config-key mapping used by the per_kind layout. Native formats are
# CreativeTemplates with ``native_eligible=True``, not a distinct Kind, so they
# do not appear here.
CONVENTION_MAP = {
    "native_style": "native-styles",
    "creative_template": "creative-templates",
}

# Directories scanned in convention mode. Each may contain mixed kinds — the
# loader trusts the ``kind:`` field in the YAML body, the directory and
# filename suffix are organisational hints. Exported (no leading underscore)
# so the import CLI can walk the same set when scanning for rename-orphan
# YAMLs.
CONVENTION_DIRS: tuple[str, ...] = (
    "creative-templates",
    "native-formats",
    "native-styles",
)
# Back-compat alias for the prior private name; remove once no internal
# caller references it.
_CONVENTION_DIRS = CONVENTION_DIRS


def load_all(repo_root: Path, config: Config) -> list[dict[str, Any]]:
    """Discover and parse YAML files per the config's layout mode.

    Returns a list of raw dicts with `kind` always present. Pydantic
    deserialization happens downstream in `gam/models/`.
    """
    if config.sources is None:
        return _load_convention(repo_root)
    if isinstance(config.sources, list):
        return _load_flat(repo_root, config.sources)
    return _load_per_kind(repo_root, config.sources)


def _load_convention(repo_root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for dirname in _CONVENTION_DIRS:
        for yaml_path in sorted((repo_root / dirname).glob("*.yaml")):
            data = _read_yaml(yaml_path, repo_root)
            if "kind" not in data:
                raise SchemaError(f"{yaml_path}: missing `kind` field")
            validate_resource(data, repo_root)
            out.append(data)
    return out


def _load_flat(repo_root: Path, globs: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pattern in globs:
        for yaml_path in sorted(repo_root.glob(pattern)):
            data = _read_yaml(yaml_path, repo_root)
            if "kind" not in data:
                raise SchemaError(f"{yaml_path}: missing `kind` field (flat layout requires it)")
            validate_resource(data, repo_root)
            out.append(data)
    return out


def _load_per_kind(repo_root: Path, mapping: dict[str, list[str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kind, globs in mapping.items():
        for pattern in globs:
            for yaml_path in sorted(repo_root.glob(pattern)):
                data = _read_yaml(yaml_path, repo_root)
                data.setdefault("kind", _snake_to_pascal(kind))
                validate_resource(data, repo_root)
                out.append(data)
    return out


def _read_yaml(path: Path, repo_root: Path) -> dict[str, Any]:
    yaml = make_yaml(base_dir=path.parent)
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"))
    except SchemaError:
        raise
    except Exception as e:
        raise SchemaError(f"{path}: parse error: {e}") from e
    if not isinstance(raw, dict):
        raise SchemaError(f"{path}: expected a YAML mapping at root, got {type(raw).__name__}")
    raw["__source__"] = str(path.relative_to(repo_root))
    return raw


def _snake_to_pascal(s: str) -> str:
    return "".join(part.capitalize() for part in s.split("_"))


def validate_no_duplicates(raw: list[dict[str, Any]]) -> None:
    """Raise SchemaError on any duplicate resource identity across files.

    Identity is the imported gam_id (``_gam_id`` field) when present, since
    GAM allows multiple resources to share the same user-facing name. For
    user-authored YAMLs (no ``_gam_id`` yet), fall back to ``<kind>:<name>``
    — a true name collision in unimported state IS a real conflict.
    """
    seen: dict[str, str] = {}
    for item in raw:
        gam_id = item.get("_gam_id")
        key = f"{item['kind']}:_gam_id:{gam_id}" if gam_id else f"{item['kind']}:{item['name']}"
        if key in seen:
            raise SchemaError(
                f"duplicate resource identity '{key}' "
                f"(previously seen as '{seen[key]}', now also as '{item.get('__source__', '?')}')"
            )
        seen[key] = item.get("__source__", "?")
