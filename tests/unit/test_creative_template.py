from gampan.gam.models.creative_template import (
    CreativeTemplate,
    TemplateVariable,
)


def test_build_and_checksum() -> None:
    t = CreativeTemplate(
        name="interstitial",
        description="x",
        type="USER_DEFINED",
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
        "type": "USER_DEFINED",
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
