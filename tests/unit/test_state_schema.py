# tests/unit/test_state_schema.py
from datetime import UTC, datetime

from gampan.core.state.schema import ResourceEntry, State


def test_state_roundtrip() -> None:
    s = State(
        network_code="21700000000",
        last_apply_at=datetime(2026, 4, 28, 5, 13, 22, tzinfo=UTC),
        last_apply_tool_version="gampan/0.1.0",
        resources={
            "native_style:article-card": ResourceEntry(
                gam_id="12345678",
                checksum_local="sha256:a3f0",
                checksum_remote="sha256:a3f0",
                last_modified_remote=datetime(2026, 4, 24, 11, 2, tzinfo=UTC),
            )
        },
    )
    data = s.model_dump_json()
    restored = State.model_validate_json(data)
    assert restored.network_code == "21700000000"
    assert restored.resources["native_style:article-card"].gam_id == "12345678"


def test_default_schema_version() -> None:
    s = State(network_code="0")
    assert s.schema_version == 1
    assert s.resources == {}
