# tests/unit/test_state_store.py
from pathlib import Path

import pytest

from gampan.core.errors import StateError
from gampan.core.state.schema import State
from gampan.core.state.store import StateStore


def test_write_and_read(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = StateStore(path)
    s = State(network_code="0")
    store.save(s)
    restored = store.load()
    assert restored.network_code == "0"


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "absent.json")
    s = store.load_or_empty(network_code="42")
    assert s.network_code == "42"
    assert s.resources == {}


def test_corrupt_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("not json {{")
    store = StateStore(path)
    with pytest.raises(StateError):
        store.load()


def test_atomic_write_no_partial_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.save(State(network_code="0"))
    # Simulate a crash mid-write
    original = path.read_text()

    def boom(*_a, **_kw):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        store.save(State(network_code="999"))
    assert path.read_text() == original
