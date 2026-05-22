"""Unit tests for the JSON Schema validation tripwire."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gampan.core.errors import SchemaError
from gampan.core.fs import schema_validation
from gampan.core.fs.schema_validation import (
    _load_registry,
    _validator_for,
    resolve_schema_dir,
    validate_resource,
)

# Minimal hand-rolled schemas mirroring the emit format. Kept here so the
# unit tests don't depend on the sibling schema repo being checked out.
_ENVELOPE = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "ResourceEnvelope.json",
    "type": "object",
    "properties": {"kind": {"type": "string"}},
    "required": ["kind"],
}
_NATIVE = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "NativeStyle.json",
    "type": "object",
    "properties": {
        "kind": {"type": "string", "const": "NativeStyle"},
        "name": {"type": "string"},
        "template_id": {"type": "integer"},
    },
    "required": ["kind", "name", "template_id"],
    "allOf": [{"$ref": "ResourceEnvelope.json"}],
}


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """Reset module-level caches between tests so each gets a clean slate."""
    _load_registry.cache_clear()
    _validator_for.cache_clear()
    schema_validation._MISSING_WARNED.clear()


def _write_schemas(schema_dir: Path) -> None:
    schema_dir.mkdir(parents=True, exist_ok=True)
    (schema_dir / "ResourceEnvelope.json").write_text(json.dumps(_ENVELOPE))
    (schema_dir / "NativeStyle.json").write_text(json.dumps(_NATIVE))


def test_resolve_schema_dir_env_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    monkeypatch.setenv("ADPAN_SCHEMA_DIR", str(schema_dir))
    assert resolve_schema_dir(tmp_path) == schema_dir


def test_resolve_schema_dir_env_relative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    monkeypatch.setenv("ADPAN_SCHEMA_DIR", "schemas")
    assert resolve_schema_dir(tmp_path) == schema_dir.resolve()


def test_resolve_schema_dir_sibling_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADPAN_SCHEMA_DIR", raising=False)
    repo_root = tmp_path / "gampan"
    repo_root.mkdir()
    sibling = tmp_path / "schema" / "tsp-output" / "json-schema"
    sibling.mkdir(parents=True)
    assert resolve_schema_dir(repo_root) == sibling.resolve()


def test_resolve_schema_dir_missing_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ADPAN_SCHEMA_DIR", raising=False)
    assert resolve_schema_dir(tmp_path / "gampan") is None


def test_validate_resource_passes_on_valid_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_dir = tmp_path / "schemas"
    _write_schemas(schema_dir)
    monkeypatch.setenv("ADPAN_SCHEMA_DIR", str(schema_dir))

    data = {
        "kind": "NativeStyle",
        "name": "card",
        "template_id": 1,
        "__source__": "native-styles/card.yaml",
    }
    validate_resource(data, tmp_path)


def test_validate_resource_raises_on_missing_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_dir = tmp_path / "schemas"
    _write_schemas(schema_dir)
    monkeypatch.setenv("ADPAN_SCHEMA_DIR", str(schema_dir))

    data = {
        "kind": "NativeStyle",
        "name": "card",
        # template_id missing
        "__source__": "native-styles/card.yaml",
    }
    with pytest.raises(SchemaError) as exc:
        validate_resource(data, tmp_path)
    assert "native-styles/card.yaml" in str(exc.value)
    assert "template_id" in str(exc.value)


def test_validate_resource_raises_on_wrong_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_dir = tmp_path / "schemas"
    _write_schemas(schema_dir)
    monkeypatch.setenv("ADPAN_SCHEMA_DIR", str(schema_dir))

    data = {
        "kind": "NativeStyle",
        "name": "card",
        "template_id": "not-an-int",
        "__source__": "x.yaml",
    }
    with pytest.raises(SchemaError) as exc:
        validate_resource(data, tmp_path)
    assert "template_id" in str(exc.value)


def test_validate_resource_skips_when_schema_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("ADPAN_SCHEMA_DIR", raising=False)
    # Even a payload that would fail (missing required `template_id`) must not
    # raise when the schema dir cannot be resolved — dev ergonomics.
    data = {"kind": "NativeStyle", "name": "card"}
    validate_resource(data, tmp_path / "gampan")  # no raise


def test_validate_resource_skips_unknown_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema_dir = tmp_path / "schemas"
    _write_schemas(schema_dir)
    monkeypatch.setenv("ADPAN_SCHEMA_DIR", str(schema_dir))

    # No schema file for UnknownKind — must not raise (Pydantic handles it
    # downstream, or the kind is genuinely unsupported).
    validate_resource({"kind": "UnknownKind", "anything": True}, tmp_path)


def test_validate_resource_ignores_source_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`__source__` is loader-injected metadata; schema must not see it."""
    # Make the schema strict by forbidding additional props.
    strict = dict(_NATIVE)
    strict["additionalProperties"] = False
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    (schema_dir / "ResourceEnvelope.json").write_text(json.dumps(_ENVELOPE))
    (schema_dir / "NativeStyle.json").write_text(json.dumps(strict))
    monkeypatch.setenv("ADPAN_SCHEMA_DIR", str(schema_dir))

    data = {
        "kind": "NativeStyle",
        "name": "card",
        "template_id": 1,
        "__source__": "x.yaml",
    }
    validate_resource(data, tmp_path)  # would fail without the strip
