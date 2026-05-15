# tests/unit/test_engine_diff.py
from gampan.core.engine.diff import Action, FieldDiff, diff_resources
from gampan.gam.models.creative_template import CreativeTemplate, TemplateVariable
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
    changes = diff_resources(desired=[_ns("a")], current={})
    assert len(changes) == 1
    assert changes[0].action == Action.CREATE
    assert changes[0].key == "NativeStyle:a"
    # CREATE produces no diffs (nothing to compare against)
    assert changes[0].diffs == []


def test_no_change_when_checksums_match() -> None:
    a = _ns("a")
    changes = diff_resources(desired=[a], current={"NativeStyle:a": ("id-1", a)})
    assert changes[0].action == Action.NO_CHANGE
    assert changes[0].diffs == []


def test_update_when_content_differs() -> None:
    a1 = _ns("a", html="<div/>")
    a2 = _ns("a", html="<span/>")
    changes = diff_resources(desired=[a2], current={"NativeStyle:a": ("id-1", a1)})
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
    changes = diff_resources(desired=[], current={"NativeStyle:a": ("id-1", a)})
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
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )
    changes = diff_resources(desired=[a2], current={"NativeStyle:a": ("id-1", a1)})
    assert changes[0].action == Action.UPDATE
    paths = [d.path for d in changes[0].diffs]
    assert "size.width" in paths


def test_update_list_element_diff() -> None:
    """Changes inside a list element produce indexed paths."""
    v1 = TemplateVariable(name="cta", type="STRING", default="old")
    v2 = TemplateVariable(name="cta", type="STRING", default="new")
    ct1 = _ct("t", variables=[v1])
    ct2 = _ct("t", variables=[v2])
    changes = diff_resources(desired=[ct2], current={"CreativeTemplate:t": ("id-1", ct1)})
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
    changes = diff_resources(desired=[ct2], current={"CreativeTemplate:t": ("id-1", ct1)})
    assert changes[0].action == Action.UPDATE
    added = [d for d in changes[0].diffs if d.before is None]
    assert len(added) > 0
