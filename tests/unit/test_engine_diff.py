# tests/unit/test_engine_diff.py
import pytest

from gampan.core.engine.diff import Action, FieldDiff, MissingRemoteError, diff_resources
from gampan.gam.models.creative_template import CreativeTemplate, TemplateVariable
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


def _ct(
    name: str, description: str = "", variables: list[TemplateVariable] | None = None
) -> CreativeTemplate:
    return CreativeTemplate(
        name=name,
        description=description,
        snippet="<div/>",
        variables=variables or [],
    )


def test_create_when_desired_only() -> None:
    changes = diff_resources(desired=[("NativeStyle:id-a", _ns("a"))], current={})
    assert len(changes) == 1
    assert changes[0].action == Action.CREATE
    assert changes[0].key == "NativeStyle:id-a"
    # CREATE produces no diffs (nothing to compare against)
    assert changes[0].diffs == []


def test_no_change_when_checksums_match() -> None:
    a = _ns("a")
    changes = diff_resources(
        desired=[("NativeStyle:id-1", a)],
        current={"NativeStyle:id-1": ("id-1", a)},
    )
    assert changes[0].action == Action.NO_CHANGE
    assert changes[0].diffs == []


def test_update_when_content_differs() -> None:
    a1 = _ns("a", html="<div/>")
    a2 = _ns("a", html="<span/>")
    changes = diff_resources(
        desired=[("NativeStyle:id-1", a2)],
        current={"NativeStyle:id-1": ("id-1", a1)},
    )
    assert changes[0].action == Action.UPDATE
    # New structured diffs
    paths = [d.path for d in changes[0].diffs]
    assert "htmlSnippet" in paths
    html_diff = next(d for d in changes[0].diffs if d.path == "htmlSnippet")
    assert isinstance(html_diff, FieldDiff)
    assert html_diff.before == "<div/>"
    assert html_diff.after == "<span/>"
    # Backward-compat diff_summary still works
    assert any("htmlSnippet" in line for line in changes[0].diff_summary)


def test_delete_when_only_in_current() -> None:
    a = _ns("a")
    changes = diff_resources(desired=[], current={"NativeStyle:id-1": ("id-1", a)})
    assert changes[0].action == Action.DELETE
    assert changes[0].diffs == []


def test_update_nested_field_diff() -> None:
    """Nested dict changes (e.g. size sub-fields) produce dotted paths."""
    a1 = _ns("a")
    # Change the size by rebuilding with a different width
    a2 = NativeStyle(
        name="a",
        size=Size(width=300, height=1, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        status="ACTIVE",
    )
    changes = diff_resources(
        desired=[("NativeStyle:id-1", a2)],
        current={"NativeStyle:id-1": ("id-1", a1)},
    )
    assert changes[0].action == Action.UPDATE
    paths = [d.path for d in changes[0].diffs]
    assert "size.width" in paths


def test_update_list_element_diff() -> None:
    """Changes inside a list element produce indexed paths."""
    v1 = TemplateVariable(name="cta", type="STRING", default="old")
    v2 = TemplateVariable(name="cta", type="STRING", default="new")
    ct1 = _ct("t", variables=[v1])
    ct2 = _ct("t", variables=[v2])
    changes = diff_resources(
        desired=[("CreativeTemplate:id-1", ct2)],
        current={"CreativeTemplate:id-1": ("id-1", ct1)},
    )
    assert changes[0].action == Action.UPDATE
    paths = [d.path for d in changes[0].diffs]
    # default changed inside variables[0]
    assert any("variables[0]" in p for p in paths)


def test_update_list_length_diff() -> None:
    """Adding a new list item produces a FieldDiff with before=None."""
    v1 = TemplateVariable(name="cta", type="STRING")
    v2 = TemplateVariable(name="img", type="URL")
    ct1 = _ct("t", variables=[v1])
    ct2 = _ct("t", variables=[v1, v2])
    changes = diff_resources(
        desired=[("CreativeTemplate:id-1", ct2)],
        current={"CreativeTemplate:id-1": ("id-1", ct1)},
    )
    assert changes[0].action == Action.UPDATE
    added = [d for d in changes[0].diffs if d.before is None]
    assert len(added) > 0


def test_strict_missing_remote_raises_for_tracked_yaml() -> None:
    """Imported YAML (key has a real gam_id) without a remote match must
    raise instead of CREATE — otherwise we'd clone the resource."""
    with pytest.raises(MissingRemoteError) as exc:
        diff_resources(
            desired=[("NativeStyle:943475", _ns("배너 광고 스타일"))],
            current={},
            strict_missing_remote=True,
        )
    assert "include_archived" in str(exc.value)
    assert "NativeStyle:943475" in str(exc.value)


def test_strict_missing_remote_still_allows_new_create() -> None:
    """User-authored YAML carries a synthetic ``NEW:`` key — the guard must
    let it through so brand-new resources can still be created."""
    changes = diff_resources(
        desired=[("NativeStyle:NEW:gampan-smoke-deadbeef", _ns("smoke"))],
        current={},
        strict_missing_remote=True,
    )
    assert len(changes) == 1
    assert changes[0].action == Action.CREATE


def test_strict_missing_remote_off_keeps_old_behaviour() -> None:
    """When the guard is disabled (caller passed --include-archived), tracked
    YAMLs with no remote fall back to CREATE just like the pre-guard code."""
    changes = diff_resources(
        desired=[("NativeStyle:943475", _ns("배너 광고 스타일"))],
        current={},
        strict_missing_remote=False,
    )
    assert len(changes) == 1
    assert changes[0].action == Action.CREATE
