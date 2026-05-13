# tests/unit/test_engine_diff.py
from gampan.core.engine.diff import Action, diff_resources
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


def test_create_when_desired_only() -> None:
    changes = diff_resources(desired=[_ns("a")], current={})
    assert len(changes) == 1
    assert changes[0].action == Action.CREATE
    assert changes[0].key == "NativeStyle:a"


def test_no_change_when_checksums_match() -> None:
    a = _ns("a")
    changes = diff_resources(desired=[a], current={"NativeStyle:a": ("id-1", a)})
    assert changes[0].action == Action.NO_CHANGE


def test_update_when_content_differs() -> None:
    a1 = _ns("a", html="<div/>")
    a2 = _ns("a", html="<span/>")
    changes = diff_resources(desired=[a2], current={"NativeStyle:a": ("id-1", a1)})
    assert changes[0].action == Action.UPDATE
    assert any("html" in line for line in changes[0].diff_summary)


def test_delete_when_only_in_current() -> None:
    a = _ns("a")
    changes = diff_resources(desired=[], current={"NativeStyle:a": ("id-1", a)})
    assert changes[0].action == Action.DELETE
