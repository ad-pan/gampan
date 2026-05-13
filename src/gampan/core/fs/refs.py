"""Custom `!file` YAML tag for inlining side files."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from gampan.core.errors import SchemaError


def make_yaml(base_dir: Path) -> YAML:
    """Return a YAML loader that resolves `!file <relpath>` against `base_dir`."""
    yaml = YAML(typ="safe", pure=True)
    base_resolved = base_dir.resolve()

    def file_constructor(loader, node):  # type: ignore[no-untyped-def]
        relpath = loader.construct_scalar(node)
        target = (base_resolved / relpath).resolve()
        if not target.is_relative_to(base_resolved):
            raise SchemaError(f"!file path '{relpath}' resolves outside base_dir")
        if not target.exists():
            raise SchemaError(f"!file path '{relpath}' does not exist (looked at {target})")
        return target.read_text(encoding="utf-8")

    yaml.constructor.add_constructor("!file", file_constructor)
    return yaml
