# tests/unit/test_engine_executor.py
from pathlib import Path

import pytest

from gampan.core.engine.executor import execute_plan
from gampan.core.engine.planner import build_plan
from gampan.core.errors import GamApiError
from gampan.core.state.schema import State
from gampan.core.state.store import StateStore
from gampan.gam.models.native_style import NativeStyle, Size, Targeting


def _ns(name: str, html: str = "<div/>") -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html=html,
        css="",
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )


class FakeClient:
    def __init__(self) -> None:
        self.created: list = []
        self.updated: list = []
        self.deleted: list = []
        self._next_id = 100

    def list(self):
        return []

    def get(self, gam_id):
        raise NotImplementedError

    def create(self, resource) -> str:
        self._next_id += 1
        self.created.append((self._next_id, resource))
        return str(self._next_id)

    def update(self, gam_id, resource) -> None:
        self.updated.append((gam_id, resource))

    def delete(self, gam_id) -> None:
        self.deleted.append(gam_id)


def test_create_persists_state(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.save(State(network_code="0"))
    plan = build_plan(desired=[_ns("a")], current={})
    client_by_kind = {"NativeStyle": FakeClient()}

    execute_plan(plan, client_by_kind, store, tool_version="gampan/0.1.0")

    state = store.load()
    assert "NativeStyle:a" in state.resources
    assert state.resources["NativeStyle:a"].gam_id == "101"
    assert state.last_apply_tool_version == "gampan/0.1.0"


def test_failure_persists_partial_state(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.save(State(network_code="0"))

    class FailingClient(FakeClient):
        def create(self, resource):
            if resource.name == "b":
                raise GamApiError("boom")
            return super().create(resource)

    plan = build_plan(desired=[_ns("a"), _ns("b"), _ns("c")], current={})
    with pytest.raises(GamApiError):
        execute_plan(plan, {"NativeStyle": FailingClient()}, store, tool_version="t")

    state = store.load()
    # a was created and persisted; b failed; c never attempted
    assert "NativeStyle:a" in state.resources
    assert "NativeStyle:b" not in state.resources
    assert "NativeStyle:c" not in state.resources
