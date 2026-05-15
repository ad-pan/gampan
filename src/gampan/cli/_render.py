"""Rich-based plan/apply output rendering."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from gampan.core.engine.diff import Action, Change
from gampan.core.engine.planner import Plan

# A single global console instance; callers may inject their own.
_console = Console()

# ── visual constants ──────────────────────────────────────────────────────────
_ACTION_PREFIX: dict[Action, str] = {
    Action.CREATE: "+",
    Action.UPDATE: "~",
    Action.DELETE: "-",
    Action.NO_CHANGE: "=",
}

_ACTION_STYLE: dict[Action, str] = {
    Action.CREATE: "bold green",
    Action.UPDATE: "bold yellow",
    Action.DELETE: "bold red",
    Action.NO_CHANGE: "bright_black",
}

_DIFF_BEFORE_STYLE = "red"
_DIFF_AFTER_STYLE = "green"

_VALUE_MAX = 80  # chars before truncation


# ── helpers ───────────────────────────────────────────────────────────────────


def _truncate(value: Any, max_len: int = _VALUE_MAX) -> str:
    """Render *value* as a string and truncate to *max_len* chars."""
    s = repr(value) if not isinstance(value, str) else value
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


def _multiline_truncate(value: Any, max_len: int = _VALUE_MAX) -> tuple[str, int]:
    """Return (first_line_truncated, extra_lines_count) for display purposes."""
    s = repr(value) if not isinstance(value, str) else value
    lines = s.splitlines()
    if not lines:
        return ("", 0)
    first = lines[0]
    extra = len(lines) - 1
    if len(first) > max_len:
        first = first[:max_len] + "…"
    return (first, extra)


def _render_change_row(c: Change, console: Console) -> None:
    """Print one change row (prefix + key, then field diffs for UPDATE)."""
    action = c.action
    prefix = _ACTION_PREFIX[action]
    style = _ACTION_STYLE[action]

    row = Text()
    row.append("  ")
    row.append(prefix, style=style)
    row.append("  ")
    row.append(c.key)
    console.print(row)

    if action == Action.UPDATE:
        for fd in c.diffs:
            # Field path header
            console.print(f"      [bold]{fd.path}:[/bold]")

            # before (-) line
            first_before, extra_before = _multiline_truncate(fd.before)
            before_text = Text()
            before_text.append("        - ", style=_DIFF_BEFORE_STYLE)
            before_text.append(f'"{first_before}"')
            if extra_before:
                plural = "s" if extra_before > 1 else ""
                before_text.append(f"  … ({extra_before} more line{plural} differ)", style="dim")
            console.print(before_text)

            # after (+) line
            first_after, extra_after = _multiline_truncate(fd.after)
            after_text = Text()
            after_text.append("        + ", style=_DIFF_AFTER_STYLE)
            after_text.append(f'"{first_after}"')
            if extra_after:
                plural = "s" if extra_after > 1 else ""
                after_text.append(f"  … ({extra_after} more line{plural} differ)", style="dim")
            console.print(after_text)


# ── public API ────────────────────────────────────────────────────────────────


def render_plan(
    plan: Plan,
    show_unchanged: bool = False,
    console: Console | None = None,
) -> None:
    """Print each change in the plan with rich formatting.

    Args:
        plan: The plan produced by ``build_plan``.
        show_unchanged: When *True*, also print NO_CHANGE rows (dim, no diff).
        console: Optional rich Console to write to (defaults to the module-level one).
    """
    con = console or _console
    for c in plan.changes:
        if c.action == Action.NO_CHANGE and not show_unchanged:
            continue
        _render_change_row(c, con)


def render_summary(plan: Plan, console: Console | None = None) -> None:
    """Print the one-liner tally: ``Plan: N to add, N to change, N to destroy. N unchanged.``

    Args:
        plan: The plan to summarise.
        console: Optional rich Console (defaults to module-level one).
    """
    con = console or _console
    summary = plan.summary()

    create_n = summary[Action.CREATE]
    update_n = summary[Action.UPDATE]
    delete_n = summary[Action.DELETE]
    no_change_n = summary[Action.NO_CHANGE]

    line = Text()
    line.append("\nPlan: ")
    line.append(str(create_n), style="bold green")
    line.append(" to add, ")
    line.append(str(update_n), style="bold yellow")
    line.append(" to change, ")
    line.append(str(delete_n), style="bold red")
    line.append(" to destroy. ")
    line.append(str(no_change_n), style="bright_black")
    line.append(" unchanged.", style="bright_black")

    con.print(line)


def render_summary_table(plan: Plan, console: Console | None = None) -> None:
    """Print a rich Table summarising the plan (4 rows, one per action).

    Use ``render_summary`` for the default one-liner.  This is the
    ``--summary-style=table`` variant.
    """
    con = console or _console
    summary = plan.summary()

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Action", style="bold")
    table.add_column("Count", justify="right")

    rows: list[tuple[str, str, str]] = [
        ("+ CREATE", str(summary[Action.CREATE]), "bold green"),
        ("~ UPDATE", str(summary[Action.UPDATE]), "bold yellow"),
        ("- DELETE", str(summary[Action.DELETE]), "bold red"),
        ("= NO_CHANGE", str(summary[Action.NO_CHANGE]), "bright_black"),
    ]
    for label, count, style in rows:
        table.add_row(Text(label, style=style), Text(count, style=style))

    con.print(table)
