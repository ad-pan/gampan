"""Custom `!file` YAML tag for inlining side files."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from gampan.core.errors import SchemaError


def make_yaml(base_dir: Path) -> YAML:
    """Return a YAML loader that resolves `!file <relpath>` against `base_dir`."""
    yaml = YAML(typ="safe", pure=True)

    def file_constructor(loader, node):  # type: ignore[no-untyped-def]
        relpath = loader.construct_scalar(node)
        target = (base_dir / relpath).resolve()
        base_resolved = base_dir.resolve()
        if not str(target).startswith(str(base_resolved)):
            raise SchemaError(f"!file path '{relpath}' resolves outside base_dir")
        if not target.exists():
            raise SchemaError(f"!file path '{relpath}' does not exist (looked at {target})")
        return target.read_text()

    yaml.constructor.add_constructor("!file", file_constructor)
    return yaml
