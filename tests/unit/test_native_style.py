# tests/unit/test_native_style.py
import pytest

from gampan.gam.models.native_style import (
    LegacyTargetingError,
    NativeStyle,
    Size,
)


def test_build_from_dict() -> None:
    ns = NativeStyle(
        name="card",
        size=Size(width=320, height=250, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        targeting={"inventoryTargeting": {"targetedAdUnits": [{"adUnitId": "1", "includeDescendants": True}]}},
        status="ACTIVE",
    )
    assert ns.kind == "NativeStyle"
    assert ns.name == "card"
    assert ns.targeting is not None
    assert ns.targeting["inventoryTargeting"]["targetedAdUnits"][0]["adUnitId"] == "1"


def test_round_trip_through_remote_dict() -> None:
    """``Targeting`` is now opaque — whatever ``from_remote`` receives must
    survive ``to_remote`` byte-for-byte so apply never overwrites the
    remote payload with a partial reconstruction."""
    raw = {
        "id": "98765",
        "name": "card",
        "size": {"width": 320, "height": 250},
        "isFluid": False,
        "creativeTemplateId": 1,
        "htmlSnippet": "<div/>",
        "cssSnippet": "",
        "targeting": {
            "inventoryTargeting": {
                "targetedAdUnits": [{"adUnitId": "23311329516", "includeDescendants": True}],
                "excludedAdUnits": [],
                "targetedPlacementIds": [],
            },
            "geoTargeting": None,
            "customTargeting": None,
        },
        "status": "ACTIVE",
    }
    ns = NativeStyle.from_remote(raw)
    assert ns.template_id == 1
    out = ns.to_remote()
    assert out["creativeTemplateId"] == 1
    assert out["htmlSnippet"] == "<div/>"
    # round-trip preserved targeting verbatim
    assert out["targeting"] == raw["targeting"]


def test_checksum_stable() -> None:
    ns1 = NativeStyle(
        name="x",
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html="a",
        css="b",
        status="ACTIVE",
    )
    ns2 = NativeStyle(
        name="x",
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html="a",
        css="b",
        status="ACTIVE",
    )
    assert ns1.checksum() == ns2.checksum()


def test_empty_legacy_targeting_silently_migrates_to_none() -> None:
    """gampan<=0.1.x YAML carried ``targeting: {ad_units: [], custom: {}}``.
    The old shape never encoded anything, so empty payloads migrate to
    ``None`` silently — no data was ever lost."""
    ns = NativeStyle(
        name="x",
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html="",
        css="",
        targeting={"ad_units": [], "custom": {}},
        status="ACTIVE",
    )
    assert ns.targeting is None


def test_non_empty_legacy_targeting_raises() -> None:
    """A populated legacy payload is a lie — the YAML claims to have
    targeting that the old import never actually captured. Refuse rather
    than apply an empty SOAP targeting that would wipe the remote."""
    with pytest.raises(LegacyTargetingError):
        NativeStyle(
            name="x",
            size=Size(width=1, height=1, is_fluid=False),
            template_id=1,
            html="",
            css="",
            targeting={"ad_units": ["unit/a"], "custom": {}},
            status="ACTIVE",
        )
