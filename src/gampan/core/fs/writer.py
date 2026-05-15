"""Write Resource models back to YAML + side files.

Long snippet fields (html / css / snippet) are promoted to sibling side files
referenced from the YAML via a real ``!file`` tag (not a quoted string), so
that the loader's ``!file`` constructor expands them back to identical content
on the next read.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.representer import RoundTripRepresenter
from ruamel.yaml.scalarstring import LiteralScalarString

from gampan.core.protocols import Resource

_KIND_TO_DIR = {
    "NativeStyle": "native-styles",
    "CreativeTemplate": "creative-templates",
}


class FileRef:
    """Marker for a ``!file <relpath>`` YAML tag the writer emits."""

    __slots__ = ("relpath",)

    def __init__(self, relpath: str) -> None:
        self.relpath = relpath


def _represent_fileref(representer: RoundTripRepresenter, data: FileRef) -> Any:
    return representer.represent_scalar("!file", data.relpath)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")


def write_resource(repo_root: Path, resource: Resource) -> Path:
    """Write the YAML + any side files, returning the YAML path."""
    dir_name = _KIND_TO_DIR[resource.kind]
    target_dir = repo_root / dir_name
    target_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = target_dir / f"{slugify(resource.name)}.yaml"

    payload = resource.to_remote()
    # Promote html/snippet/css to side files for editor support
    side_files = _emit_side_files(target_dir, slugify(resource.name), payload)

    yaml = YAML()
    yaml.default_flow_style = False
    # Disable line wrapping so ruamel never picks folded (`>`) style, which
    # collapses consecutive whitespace and breaks round-trip fidelity.
    yaml.width = 2**31 - 1
    yaml.representer.add_representer(FileRef, _represent_fileref)
    data = _to_user_yaml(resource.kind, resource.name, payload, side_files)
    data = _normalise_strings(data)
    with yaml_path.open("w") as f:
        yaml.dump(data, f)
    return yaml_path


def _normalise_strings(value: Any) -> Any:
    """Walk the payload and force ``LiteralScalarString`` for multi-line strings
    so newlines and indentation are preserved verbatim.

    Single-line strings are left as plain ``str``: combined with
    ``yaml.width = max`` this keeps ruamel from picking folded (``>``) style,
    which would collapse consecutive whitespace and break round-trip fidelity.
    """
    if isinstance(value, FileRef):
        return value
    if isinstance(value, str):
        if "\n" in value:
            return LiteralScalarString(value)
        return value
    if isinstance(value, dict):
        return {k: _normalise_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise_strings(v) for v in value]
    return value


def _emit_side_files(dir_path: Path, slug: str, payload: dict[str, Any]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for field in ("htmlSnippet", "cssSnippet", "snippet"):
        if field in payload and isinstance(payload[field], str) and len(payload[field]) > 80:
            ext = "html" if field != "cssSnippet" else "css"
            side = dir_path / f"{slug}.{ext}"
            side.write_text(payload[field])
            out[field] = side
    return out


def _to_user_yaml(
    kind: str, name: str, payload: dict[str, Any], side_files: dict[str, Path]
) -> dict[str, Any]:
    user: dict[str, Any] = {"kind": kind, "name": name}
    if kind == "NativeStyle":
        user["size"] = {
            "width": payload["size"]["width"],
            "height": payload["size"]["height"],
            "is_fluid": payload["size"]["isFluid"],
        }
        user["template_id"] = payload["creativeTemplateId"]
        user["html"] = _ref_or_inline("htmlSnippet", payload, side_files)
        user["css"] = _ref_or_inline("cssSnippet", payload, side_files)
        user["targeting"] = {
            "ad_units": payload["targeting"]["adUnits"],
            "custom": payload["targeting"]["customTargeting"],
        }
        user["status"] = payload["status"]
    elif kind == "CreativeTemplate":
        user["description"] = payload.get("description", "")
        user["type"] = payload["type"]
        user["snippet"] = _ref_or_inline("snippet", payload, side_files)
        user["variables"] = payload.get("variables", [])
        user["status"] = payload["status"]
    return user


def _ref_or_inline(field: str, payload: dict[str, Any], side_files: dict[str, Path]) -> Any:
    """Return a FileRef when a side file exists, else the inline value.

    The FileRef serialises as ``!file <relpath>`` (a real YAML tag) so the
    loader's matching constructor inlines the file content on read.
    """
    if field in side_files:
        return FileRef(f"./{side_files[field].name}")
    return payload.get(field, "")
