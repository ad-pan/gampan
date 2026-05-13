# tests/unit/test_native_style.py
from gampan.gam.models.native_style import NativeStyle, Size, Targeting


def test_build_from_dict() -> None:
    ns = NativeStyle(
        name="card",
        size=Size(width=320, height=250, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        targeting=Targeting(ad_units=["unit/a"], custom={}),
        status="ACTIVE",
    )
    assert ns.kind == "NativeStyle"
    assert ns.name == "card"


def test_round_trip_through_remote_dict() -> None:
    raw = {
        "id": "98765",
        "name": "card",
        "size": {"width": 320, "height": 250, "isFluid": False},
        "creativeTemplateId": 1,
        "htmlSnippet": "<div/>",
        "cssSnippet": "",
        "targeting": {"adUnits": ["unit/a"], "customTargeting": {}},
        "status": "ACTIVE",
    }
    ns = NativeStyle.from_remote(raw)
    assert ns.template_id == 1
    out = ns.to_remote()
    assert out["creativeTemplateId"] == 1
    assert out["htmlSnippet"] == "<div/>"


def test_checksum_stable() -> None:
    ns1 = NativeStyle(
        name="x",
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html="a",
        css="b",
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )
    ns2 = NativeStyle(
        name="x",
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html="a",
        css="b",
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )
    assert ns1.checksum() == ns2.checksum()
