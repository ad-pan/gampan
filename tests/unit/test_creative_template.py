from gampan.gam.models.creative_template import (
    Choice,
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


def test_list_variable_choices_round_trip() -> None:
    """LIST variables carry a `choices` array + `allow_other_choice` flag.
    The structured options drive Storybook dropdowns and `gampan apply`
    round-trips; losing them is the bug this test guards against."""
    raw = {
        "name": "text-ad",
        "description": "",
        "type": "STANDARD",
        "snippet": "<div/>",
        "variables": [
            {
                "name": "Targetwindow",
                "type": "LIST",
                "required": True,
                "default": "_blank",
                "choices": [
                    {"label": "_blank", "value": "_blank"},
                    {"label": "_top", "value": "_top"},
                ],
                "allow_other_choice": False,
            },
        ],
        "status": "ACTIVE",
    }
    t = CreativeTemplate.from_remote(raw)
    var = t.variables[0]
    assert var.choices == [Choice(label="_blank", value="_blank"), Choice(label="_top", value="_top")]
    assert var.allow_other_choice is False
    out = t.to_remote()
    assert out["variables"][0]["choices"] == [
        {"label": "_blank", "value": "_blank"},
        {"label": "_top", "value": "_top"},
    ]
    assert out["variables"][0]["allow_other_choice"] is False


def test_number_variable_round_trip() -> None:
    """NUMBER variables (proto ``long_variable``) carry an integer default
    that we serialise as a string for uniformity with the other variants."""
    raw = {
        "name": "flash-overlay",
        "description": "",
        "type": "STANDARD",
        "snippet": "<div/>",
        "variables": [
            {
                "name": "Creativezindex",
                "type": "NUMBER",
                "required": True,
                "default": "2147483640",
            },
            # NUMBER without a default (e.g. width/height fields the user must
            # always supply) — should round-trip with no ``default`` key in
            # the serialised payload.
            {
                "name": "Width",
                "type": "NUMBER",
                "required": True,
            },
        ],
        "status": "ACTIVE",
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.variables[0].type == "NUMBER"
    assert t.variables[0].default == "2147483640"
    assert t.variables[1].type == "NUMBER"
    assert t.variables[1].default is None
    out = t.to_remote()
    assert out["variables"][0]["type"] == "NUMBER"
    assert out["variables"][0]["default"] == "2147483640"
    assert "default" not in out["variables"][1]


def test_asset_variable_mime_types_round_trip() -> None:
    """ASSET variables may declare allowed MIME types — we keep the proto
    enum names verbatim (``JPG``/``PNG``/``GIF``) so storybook-adpan can
    drive a file-type constraint without remapping."""
    raw = {
        "name": "image-banner",
        "description": "",
        "type": "STANDARD",
        "snippet": "<div/>",
        "variables": [
            {
                "name": "Imagefile",
                "type": "ASSET",
                "required": True,
                "mime_types": ["JPG", "PNG", "GIF"],
            },
        ],
        "status": "ACTIVE",
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.variables[0].type == "ASSET"
    assert t.variables[0].mime_types == ["JPG", "PNG", "GIF"]
    out = t.to_remote()
    assert out["variables"][0]["mime_types"] == ["JPG", "PNG", "GIF"]


def test_asset_variable_without_mime_types_excluded_from_payload() -> None:
    """ASSET variables without a ``mime_types`` constraint should not emit
    an empty list — keeps the YAML quiet for the common any-type case."""
    raw = {
        "name": "image-banner-anytype",
        "description": "",
        "type": "STANDARD",
        "snippet": "<div/>",
        "variables": [{"name": "Imagefile", "type": "ASSET", "required": True}],
        "status": "ACTIVE",
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.variables[0].mime_types is None
    out = t.to_remote()
    assert "mime_types" not in out["variables"][0]


def test_non_list_variable_has_no_choices_field() -> None:
    """STRING/ASSET variants don't expose `choices` on the REST oneof —
    we leave `choices` as None and exclude it from the serialised payload."""
    raw = {
        "name": "plain",
        "description": "",
        "type": "CUSTOM",
        "snippet": "<div/>",
        "variables": [{"name": "headline", "type": "STRING", "required": True}],
        "status": "ACTIVE",
    }
    t = CreativeTemplate.from_remote(raw)
    assert t.variables[0].choices is None
    assert t.variables[0].allow_other_choice is None
    # `to_remote()` excludes None via model_dump(exclude_none=True) — so
    # STRING variables produce a clean payload without an empty `choices`
    # or an irrelevant `allow_other_choice` flag.
    out = t.to_remote()
    assert "choices" not in out["variables"][0]
    assert "allow_other_choice" not in out["variables"][0]
