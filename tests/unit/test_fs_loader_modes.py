# tests/unit/test_fs_loader_modes.py
from pathlib import Path

import pytest

from gampan.core.errors import SchemaError
from gampan.core.fs.config import Config
from gampan.core.fs.loader import load_all, validate_no_duplicates

NS_YAML = (
    "kind: NativeStyle\nname: {name}\nsize:\n  width: 320\n  height: 250\n  is_fluid: false\n"
    "template_id: 1\nhtml: '<div/>'\ncss: ''\n"
    "targeting:\n  ad_units: []\n  custom: {{}}\nstatus: ACTIVE\n"
)


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_per_kind_explicit_mode(tmp_path: Path) -> None:
    _write(tmp_path / "ads/native/a.yaml", NS_YAML.format(name="a"))
    _write(tmp_path / "ads/native/b.yaml", NS_YAML.format(name="b"))
    cfg = Config(network_code="0", sources={"native_style": ["ads/native/*.yaml"]})
    raw = load_all(tmp_path, cfg)
    assert {r["name"] for r in raw} == {"a", "b"}


def test_flat_mode(tmp_path: Path) -> None:
    _write(tmp_path / "resources/x.yaml", NS_YAML.format(name="x"))
    cfg = Config(network_code="0", sources=["resources/*.yaml"])
    raw = load_all(tmp_path, cfg)
    assert raw[0]["name"] == "x"


def test_duplicate_kind_name_collision(tmp_path: Path) -> None:
    _write(tmp_path / "a/one.yaml", NS_YAML.format(name="dup"))
    _write(tmp_path / "b/two.yaml", NS_YAML.format(name="dup"))
    cfg = Config(network_code="0", sources=["**/*.yaml"])
    raw = load_all(tmp_path, cfg)
    with pytest.raises(SchemaError) as ei:
        validate_no_duplicates(raw)
    assert "duplicate" in str(ei.value).lower()
    assert "dup" in str(ei.value)
