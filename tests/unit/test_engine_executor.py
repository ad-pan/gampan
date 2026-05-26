# tests/unit/test_engine_executor.py
from pathlib import Path

import pytest

from gampan.core.engine.executor import execute_plan
from gampan.core.engine.planner import build_plan
from gampan.core.errors import GamApiError
from gampan.core.state.schema import State
from gampan.core.state.store import StateStore
from gampan.gam.models.native_style import NativeStyle, Size


def _ns(name: str, html: str = "<div/>") -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html=html,
        css="",
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
    """CREATE rebinds the synthetic ``NEW:`` state key to the assigned
    gam_id so the next `plan` matches the YAML by identity instead of
    treating it as another fresh CREATE candidate."""
    store = StateStore(tmp_path / "state.json")
    store.save(State(network_code="0"))
    plan = build_plan(desired=[("NativeStyle:NEW:a-test", _ns("a"))], current={})
    client_by_kind = {"NativeStyle": FakeClient()}

    execute_plan(plan, client_by_kind, store, tool_version="gampan/0.1.0")

    state = store.load()
    # The pre-rebind key must not linger — that's the whole point of the
    # rebind; otherwise re-running plan double-counts the resource.
    assert "NativeStyle:NEW:a-test" not in state.resources
    assert "NativeStyle:101" in state.resources
    assert state.resources["NativeStyle:101"].gam_id == "101"
    assert state.last_apply_tool_version == "gampan/0.1.0"


def test_create_writes_gam_id_back_into_yaml(tmp_path: Path) -> None:
    """When ``root`` is supplied and the change carries a ``yaml_path``,
    CREATE stamps ``_gam_ids[env]`` into the source file so subsequent
    imports recognise the resource by id. Single-env apply paths currently
    write under the ``default`` env until Task 13 plumbs ``--env`` through."""
    from gampan.core.engine.diff import Action, Change
    from gampan.core.engine.planner import Plan

    yaml_dir = tmp_path / "native-styles"
    yaml_dir.mkdir()
    yaml_file = yaml_dir / "a.native-style.yaml"
    yaml_file.write_text(
        "kind: NativeStyle\nname: a\nsize:\n  width: 1\n  height: 1\n  is_fluid: false\n"
        "template_id: 1\nhtml: '<div/>'\ncss: ''\n"
        "targeting:\n  ad_units: []\n  custom: {}\nstatus: ACTIVE\n",
        encoding="utf-8",
    )
    store = StateStore(tmp_path / "state.json")
    store.save(State(network_code="0"))

    plan = Plan(
        changes=[
            Change(
                action=Action.CREATE,
                key="NativeStyle:NEW:a-test",
                gam_id=None,
                desired=_ns("a"),
                current=None,
                yaml_path="native-styles/a.native-style.yaml",
            )
        ]
    )

    execute_plan(
        plan,
        {"NativeStyle": FakeClient()},
        store,
        tool_version="gampan/0.1.0",
        root=tmp_path,
    )

    body = yaml_file.read_text(encoding="utf-8")
    # v1.x writes the env-keyed dict; the legacy scalar form is gone.
    assert "_gam_ids:" in body
    assert "default: '101'" in body
    # ``_gam_ids`` should sit right after ``kind:`` so the file stays
    # readable and matches what ``gampan import`` would have written.
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    assert lines[0] == "kind: NativeStyle"
    assert lines[1] == "_gam_ids:"
    assert lines[2] == "default: '101'"


def test_delete_skips_rpc_when_remote_already_archived(tmp_path: Path) -> None:
    """SOAP archive is idempotent but a redundant RPC is still noise. When
    the remote already reports ARCHIVED, the executor must skip the call
    yet still drop the row from state.json so plan stops re-surfacing it."""
    from gampan.core.engine.diff import Action, Change
    from gampan.core.engine.planner import Plan

    archived = _ns("zombie")
    archived = archived.model_copy(update={"status": "ARCHIVED"})

    store = StateStore(tmp_path / "state.json")
    store.save(State(network_code="0"))

    plan = Plan(
        changes=[
            Change(
                action=Action.DELETE,
                key="NativeStyle:777",
                gam_id="777",
                desired=None,
                current=archived,
            )
        ]
    )
    client = FakeClient()
    execute_plan(plan, {"NativeStyle": client}, store, tool_version="t")

    # No archive RPC for an already-archived row
    assert client.deleted == []
    # State entry still removed so the next plan stops complaining
    state = store.load()
    assert "NativeStyle:777" not in state.resources


def test_delete_still_archives_when_remote_active(tmp_path: Path) -> None:
    """Sanity check: the skip only fires for ARCHIVED. ACTIVE / INACTIVE
    rows must still issue the archive RPC."""
    from gampan.core.engine.diff import Action, Change
    from gampan.core.engine.planner import Plan

    active = _ns("live")
    store = StateStore(tmp_path / "state.json")
    store.save(State(network_code="0"))

    plan = Plan(
        changes=[
            Change(
                action=Action.DELETE,
                key="NativeStyle:888",
                gam_id="888",
                desired=None,
                current=active,
            )
        ]
    )
    client = FakeClient()
    execute_plan(plan, {"NativeStyle": client}, store, tool_version="t")

    assert client.deleted == ["888"]


def test_failure_persists_partial_state(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.save(State(network_code="0"))

    class FailingClient(FakeClient):
        def create(self, resource):
            if resource.name == "b":
                raise GamApiError("boom")
            return super().create(resource)

    plan = build_plan(
        desired=[
            ("NativeStyle:NEW:a-test", _ns("a")),
            ("NativeStyle:NEW:b-test", _ns("b")),
            ("NativeStyle:NEW:c-test", _ns("c")),
        ],
        current={},
    )
    with pytest.raises(GamApiError):
        execute_plan(plan, {"NativeStyle": FailingClient()}, store, tool_version="t")

    state = store.load()
    # a was created and persisted under its rebound key; b failed; c never attempted
    assert "NativeStyle:101" in state.resources
    assert "NativeStyle:NEW:a-test" not in state.resources
    assert "NativeStyle:NEW:b-test" not in state.resources
    assert "NativeStyle:NEW:c-test" not in state.resources
