from gampan.core.engine.diff import Action
from gampan.core.engine.planner import build_plan
from gampan.gam.models.native_style import NativeStyle, Size, Targeting


def _ns(name: str) -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )


def test_build_plan_summary_counts() -> None:
    desired = [_ns("a"), _ns("b")]
    current = {"NativeStyle:a": ("id-1", _ns("a"))}  # NO_CHANGE
    plan = build_plan(desired=desired, current=current)
    assert plan.has_pending is True
    summary = plan.summary()
    assert summary[Action.CREATE] == 1  # b
    assert summary[Action.NO_CHANGE] == 1  # a
    assert summary[Action.UPDATE] == 0
    assert summary[Action.DELETE] == 0


def test_empty_plan_no_pending() -> None:
    plan = build_plan(desired=[], current={})
    assert plan.has_pending is False
