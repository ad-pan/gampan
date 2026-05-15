# tests/unit/test_cli_render.py
"""Tests for the rich-based plan/apply output renderer."""

from __future__ import annotations

from rich.console import Console

from gampan.cli._render import render_plan, render_summary
from gampan.core.engine.diff import Action, Change, FieldDiff
from gampan.core.engine.planner import Plan
from gampan.gam.models.native_style import NativeStyle, Size, Targeting

# ── fixtures ──────────────────────────────────────────────────────────────────


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


def _capture_console(*, width: int = 120) -> Console:
    """Return a Console that records output (no ANSI, deterministic)."""
    return Console(record=True, highlight=False, no_color=True, width=width)


def _plan_with(*changes: Change) -> Plan:
    return Plan(changes=list(changes))


def _change(
    action: Action,
    key: str = "NativeStyle:test",
    diffs: list[FieldDiff] | None = None,
) -> Change:
    ns = _ns("test")
    return Change(
        action=action,
        key=key,
        gam_id=None if action == Action.CREATE else "id-1",
        desired=ns,
        current=None if action == Action.CREATE else ns,
        diffs=diffs or [],
        diff_summary=[],
    )


# ── CREATE ────────────────────────────────────────────────────────────────────


def test_create_row_shows_plus_prefix() -> None:
    console = _capture_console()
    plan = _plan_with(_change(Action.CREATE, key="NativeStyle:my-card"))
    render_plan(plan, console=console)
    text = console.export_text()
    assert "+" in text
    assert "NativeStyle:my-card" in text


# ── UPDATE with field diffs ───────────────────────────────────────────────────


def test_update_row_shows_tilde_prefix() -> None:
    console = _capture_console()
    plan = _plan_with(_change(Action.UPDATE, key="CreativeTemplate:standard-text-ad"))
    render_plan(plan, console=console)
    text = console.export_text()
    assert "~" in text
    assert "CreativeTemplate:standard-text-ad" in text


def test_update_row_shows_field_diffs() -> None:
    console = _capture_console()
    diffs = [FieldDiff(path="description", before="old desc", after="new desc")]
    plan = _plan_with(_change(Action.UPDATE, diffs=diffs))
    render_plan(plan, console=console)
    text = console.export_text()
    assert "description" in text
    assert "- " in text
    assert "old desc" in text
    assert "+ " in text
    assert "new desc" in text


def test_update_shows_before_and_after_markers() -> None:
    console = _capture_console()
    diffs = [FieldDiff(path="snippet", before="<b>old</b>", after="<b>new</b>")]
    plan = _plan_with(_change(Action.UPDATE, diffs=diffs))
    render_plan(plan, console=console)
    text = console.export_text()
    # both diff sides present
    assert "<b>old</b>" in text
    assert "<b>new</b>" in text


# ── DELETE ────────────────────────────────────────────────────────────────────


def test_delete_row_shows_minus_prefix() -> None:
    console = _capture_console()
    plan = _plan_with(_change(Action.DELETE, key="CreativeTemplate:archived-thing"))
    render_plan(plan, console=console)
    text = console.export_text()
    assert "-" in text
    assert "CreativeTemplate:archived-thing" in text


# ── NO_CHANGE visibility ──────────────────────────────────────────────────────


def test_no_change_hidden_by_default() -> None:
    console = _capture_console()
    plan = _plan_with(_change(Action.NO_CHANGE, key="NativeStyle:unchanged"))
    render_plan(plan, show_unchanged=False, console=console)
    text = console.export_text()
    assert "unchanged" not in text


def test_no_change_shown_with_flag() -> None:
    console = _capture_console()
    plan = _plan_with(_change(Action.NO_CHANGE, key="NativeStyle:unchanged"))
    render_plan(plan, show_unchanged=True, console=console)
    text = console.export_text()
    assert "NativeStyle:unchanged" in text
    # NO_CHANGE uses "=" prefix
    assert "=" in text


# ── long value truncation ─────────────────────────────────────────────────────


def test_long_value_truncated() -> None:
    long_val = "x" * 200
    console = _capture_console()
    diffs = [FieldDiff(path="snippet", before=long_val, after="short")]
    plan = _plan_with(_change(Action.UPDATE, diffs=diffs))
    render_plan(plan, console=console)
    text = console.export_text()
    # truncation marker should appear
    assert "…" in text
    # full 200-char value should NOT appear verbatim
    assert long_val not in text


# ── summary line ──────────────────────────────────────────────────────────────


def test_summary_one_liner_format() -> None:
    console = _capture_console()
    plan = _plan_with(
        _change(Action.CREATE),
        _change(Action.UPDATE),
        _change(Action.DELETE),
        _change(Action.NO_CHANGE),
    )
    render_summary(plan, console=console)
    text = console.export_text()
    assert "to add" in text
    assert "to change" in text
    assert "to destroy" in text
    assert "unchanged" in text


def test_summary_counts_match_plan() -> None:
    console = _capture_console()
    plan = _plan_with(
        _change(Action.CREATE),
        _change(Action.CREATE),
        _change(Action.UPDATE),
        _change(Action.NO_CHANGE),
    )
    render_summary(plan, console=console)
    text = console.export_text()
    # 2 to add, 1 to change, 0 to destroy, 1 unchanged
    assert "2" in text
    assert "1" in text
