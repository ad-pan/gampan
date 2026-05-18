from gampan.gam.models.creative_template import (
    CreativeTemplate,
    TemplateVariable,
)


def test_build_and_checksum() -> None:
    t = CreativeTemplate(
        name="interstitial",
        description="x",
        type="CUSTOM",
        snippet="<div/>",
        variables=[
            TemplateVariable(name="headline", type="STRING", required=True),
            TemplateVariable(name="cta_text", type="STRING", required=False, default="ok"),
        ],
        status="ACTIVE",
    )
    assert t.kind == "CreativeTemplate"
    assert t.checksum().startswith("sha256:")


def test_round_trip_through_remote_dict() -> None:
    raw = {
        "name": "interstitial",
        "description": "x",
        "type": "CUSTOM",
        "snippet": "<div/>",
        "variables": [
            {"name": "headline", "type": "STRING", "required": True},
        ],
        "status": "ACTIVE",
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.variables[0].name == "headline"
    out = t.to_remote()
    assert out["variables"][0]["required"] is True


def test_eligibility_flags_default_false() -> None:
    """Missing flags in remote payload → all four eligibility bools default to False."""
    raw = {
        "name": "plain",
        "description": "",
        "type": "CUSTOM",
        "snippet": "<div/>",
        "variables": [],
        "status": "ACTIVE",
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.is_interstitial is False
    assert t.native_eligible is False
    assert t.native_video_eligible is False
    assert t.safe_frame_compatible is False
    out = t.to_remote()
    # All four keys present in the serialised payload (drives checksum stability).
    assert out["is_interstitial"] is False
    assert out["native_eligible"] is False
    assert out["native_video_eligible"] is False
    assert out["safe_frame_compatible"] is False


def test_native_video_flags_round_trip() -> None:
    """A native-video creative template (Google's `native-video-content-ad`)
    round-trips all four eligibility flags."""
    raw = {
        "name": "native-video-content-ad",
        "description": "",
        "type": "STANDARD",
        "snippet": "<div/>",
        "variables": [],
        "status": "ACTIVE",
        "is_interstitial": False,
        "native_eligible": True,
        "native_video_eligible": True,
        "safe_frame_compatible": True,
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.native_eligible is True
    assert t.native_video_eligible is True
    assert t.safe_frame_compatible is True
    # Checksum must include the flags (otherwise drift detection is blind to them)
    cs1 = t.checksum()
    t2 = CreativeTemplate.from_remote({**raw, "native_eligible": False})
    cs2 = t2.checksum()
    assert cs1 != cs2, "flipping a flag must change the checksum"
