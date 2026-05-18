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


def test_native_format_drops_snippet_on_from_remote() -> None:
    """Native ad formats ship with Google's auto-generated <table> HTML.
    It is read-only via REST Beta and pulling it down is noise, so
    from_remote() drops it. Checksum stays stable across imports because
    the snippet is uniformly empty for native formats."""
    raw = {
        "name": "native-content-ad",
        "description": "",
        "type": "STANDARD",
        "snippet": "<table><tr><td>[%headline%]</td></tr></table>" * 10,
        "variables": [],
        "status": "ACTIVE",
        "native_eligible": True,
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.snippet == "", "native format must not carry the HTML snippet"
    assert t.to_remote()["snippet"] == ""


def test_regular_creative_template_keeps_snippet() -> None:
    """Drop applies only to native formats — regular templates keep their HTML."""
    snippet = "<div>[%body%]</div>"
    raw = {
        "name": "interstitial",
        "description": "",
        "type": "CUSTOM",
        "snippet": snippet,
        "variables": [],
        "status": "ACTIVE",
        "native_eligible": False,
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.snippet == snippet


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
