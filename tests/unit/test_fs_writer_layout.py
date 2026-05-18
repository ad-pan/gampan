"""Directory + filename-suffix routing for the writer.

Three resource types map to three (directory, suffix) pairs. Native ad
formats are CreativeTemplates with ``native_eligible=True`` — the model
is shared with regular creative templates, but they land in their own
directory with their own suffix so they don't get lost in the pile.
"""

from __future__ import annotations

from pathlib import Path

from gampan.core.fs.writer import write_resource
from gampan.gam.models.creative_template import CreativeTemplate
from gampan.gam.models.native_style import NativeStyle, Size, Targeting


def _ns(name: str = "card") -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=320, height=250, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )


def _ct(name: str = "interstitial", *, native_eligible: bool = False) -> CreativeTemplate:
    return CreativeTemplate(
        name=name,
        snippet="<div/>",
        native_eligible=native_eligible,
    )


def test_native_style_writes_to_native_styles_dir(tmp_path: Path) -> None:
    yaml_path, stem = write_resource(tmp_path, _ns(name="card"), gam_id="1")
    assert yaml_path == tmp_path / "native-styles" / "card.native-style.yaml"
    assert stem == "card"


def test_regular_creative_template_writes_to_creative_templates_dir(tmp_path: Path) -> None:
    yaml_path, _ = write_resource(tmp_path, _ct(name="interstitial"), gam_id="1")
    assert yaml_path == (tmp_path / "creative-templates" / "interstitial.creative-template.yaml")


def test_native_eligible_creative_template_writes_to_native_formats_dir(tmp_path: Path) -> None:
    """The whole point of the split: native formats land under native-formats/
    so the directory tells you what you're looking at."""
    yaml_path, _ = write_resource(
        tmp_path,
        _ct(name="feed-native", native_eligible=True),
        gam_id="42",
    )
    assert yaml_path == (tmp_path / "native-formats" / "feed-native.native-format.yaml")
    # And the regular creative-templates dir stays empty for this resource.
    assert not (tmp_path / "creative-templates" / "feed-native.native-format.yaml").exists()


def test_long_snippet_promoted_to_side_file_with_matching_suffix(tmp_path: Path) -> None:
    """Side files (.html / .css) inherit the kind-suffix so they sort next
    to their parent YAML and stay self-identifying when copied."""
    long_html = "<div>" + ("x" * 200) + "</div>"
    ns = NativeStyle(
        name="card",
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html=long_html,
        css="",
        targeting=Targeting(ad_units=[], custom={}),
        status="ACTIVE",
    )
    yaml_path, _ = write_resource(tmp_path, ns, gam_id="1")
    side = tmp_path / "native-styles" / "card.native-style.html"
    assert side.exists()
    assert side.read_text() == long_html
    # YAML body references the side file via the !file tag.
    assert "!file ./card.native-style.html" in yaml_path.read_text()
