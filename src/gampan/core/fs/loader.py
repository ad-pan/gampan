"""Glob + YAML → raw dicts (kind-discriminated) for the engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gampan.core.errors import SchemaError
from gampan.core.fs.config import Config
from gampan.core.fs.refs import make_yaml

CONVENTION_MAP = {
    "native_style": "native-styles",
    "creative_template": "creative-templates",
}


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
    for dirname in CONVENTION_MAP.values():
        for yaml_path in sorted((repo_root / dirname).glob("*.yaml")):
            data = _read_yaml(yaml_path, repo_root)
            if "kind" not in data:
                raise SchemaError(f"{yaml_path}: missing `kind` field")
            out.append(data)
    return out


def _load_flat(repo_root: Path, globs: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pattern in globs:
        for yaml_path in sorted(repo_root.glob(pattern)):
            data = _read_yaml(yaml_path, repo_root)
            if "kind" not in data:
                raise SchemaError(f"{yaml_path}: missing `kind` field (flat layout requires it)")
            out.append(data)
    return out


def _load_per_kind(repo_root: Path, mapping: dict[str, list[str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for kind, globs in mapping.items():
        for pattern in globs:
            for yaml_path in sorted(repo_root.glob(pattern)):
                data = _read_yaml(yaml_path, repo_root)
                data.setdefault("kind", _snake_to_pascal(kind))
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
    """Raise SchemaError on any `<kind>:<name>` collision across files."""
    seen: dict[str, str] = {}
    for item in raw:
        key = f"{item['kind']}:{item['name']}"
        if key in seen:
            raise SchemaError(
                f"duplicate resource identity '{key}' "
                f"(previously seen as '{seen[key]}', now also as '{item.get('__source__', '?')}')"
            )
        seen[key] = item.get("__source__", "?")
