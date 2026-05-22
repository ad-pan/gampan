# tests/unit/test_engine_diff.py
import pytest

from gampan.core.engine.diff import (
    Action,
    Change,
    CreativeTemplateReadOnlyError,
    FieldDiff,
    MissingRemoteError,
    detect_remote_drift,
    diff_resources,
    validate_v0_1_constraints,
)
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


def test_detect_remote_drift_returns_keys_with_diverged_checksum() -> None:
    """Resources whose live checksum no longer matches the value recorded
    in state.json count as drifted — apply must surface that before
    overwriting the change."""
    same = _ns("same")
    changed_remote = _ns("changed", html="<remote/>")
    drifted = detect_remote_drift(
        state_entries={
            "NativeStyle:1": (same.checksum(), True),
            "NativeStyle:2": (_ns("changed", html="<local/>").checksum(), True),
        },
        current={
            "NativeStyle:1": ("1", same),
            "NativeStyle:2": ("2", changed_remote),
        },
    )
    assert drifted == ["NativeStyle:2"]


def test_detect_remote_drift_skips_unknown_keys() -> None:
    """A live resource that state has never seen (e.g. created out-of-band
    since the last import) is not drift — it's brand-new and surfaces as a
    normal DELETE/UPDATE candidate via diff_resources."""
    drifted = detect_remote_drift(
        state_entries={},
        current={"NativeStyle:99": ("99", _ns("brand-new"))},
    )
    assert drifted == []


def test_detect_remote_drift_skips_empty_recorded_checksum() -> None:
    """state.json rows that were never populated (empty ``checksum_remote``)
    cannot be drift-compared — skip them rather than false-positive."""
    drifted = detect_remote_drift(
        state_entries={"NativeStyle:1": ("", True)},
        current={"NativeStyle:1": ("1", _ns("a"))},
    )
    assert drifted == []


def test_detect_remote_drift_flags_unacknowledged_refresh() -> None:
    """Once ``refresh`` records the post-drift checksum, the checksum
    comparison alone would say "no drift" and ``apply`` would silently
    overwrite the change. ``drift_acknowledged=False`` keeps the abort
    path engaged until an operator deliberately resolves it."""
    a = _ns("a")
    drifted = detect_remote_drift(
        state_entries={
            "NativeStyle:1": (a.checksum(), False),  # refresh wrote new ck but operator did not ack
        },
        current={"NativeStyle:1": ("1", a)},
    )
    assert drifted == ["NativeStyle:1"]


def test_validate_v0_1_constraints_blocks_creative_template_writes() -> None:
    """CreativeTemplate UPDATE/CREATE/DELETE must be refused at plan time —
    GAM REST has no write verb so any such Change would crash the
    executor with NotImplementedError later. Catch it up front so the
    operator can revert the YAML."""
    bad = Change(
        action=Action.UPDATE,
        key="CreativeTemplate:42",
        gam_id="42",
        desired=_ct("touched", description="new"),
        current=_ct("touched", description="old"),
    )
    with pytest.raises(CreativeTemplateReadOnlyError) as exc:
        validate_v0_1_constraints([bad])
    assert "CreativeTemplate:42" in str(exc.value)
    assert "UPDATE" in str(exc.value)


def test_validate_v0_1_constraints_allows_no_change_creative_template() -> None:
    """NO_CHANGE on a CreativeTemplate is fine — the operator did not try
    to write anything, the row just shows up because the kind is managed."""
    ct = _ct("untouched")
    noop = Change(
        action=Action.NO_CHANGE,
        key="CreativeTemplate:42",
        gam_id="42",
        desired=ct,
        current=ct,
    )
    validate_v0_1_constraints([noop])  # must not raise


def test_validate_v0_1_constraints_passes_native_style_writes() -> None:
    """NativeStyle has full SOAP CRUD coverage in v0.1, so its writes must
    keep passing through unchanged."""
    ns_change = Change(
        action=Action.CREATE,
        key="NativeStyle:NEW:a-1",
        gam_id=None,
        desired=_ns("a"),
        current=None,
    )
    validate_v0_1_constraints([ns_change])  # must not raise


def test_detect_remote_drift_treats_acknowledged_match_as_clean() -> None:
    """Matching checksum + ``drift_acknowledged=True`` is the steady-state —
    apply must not abort in this case."""
    a = _ns("a")
    drifted = detect_remote_drift(
        state_entries={"NativeStyle:1": (a.checksum(), True)},
        current={"NativeStyle:1": ("1", a)},
    )
    assert drifted == []
