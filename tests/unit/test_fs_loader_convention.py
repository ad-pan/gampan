# tests/unit/test_fs_loader_convention.py
from pathlib import Path

from gampan.core.fs.config import Config
from gampan.core.fs.loader import load_all


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_convention_mode_loads_native_styles(tmp_path: Path) -> None:
    _write(
        tmp_path / "native-styles" / "card.yaml",
        "kind: NativeStyle\n"
        "name: card\n"
        "size:\n  width: 320\n  height: 250\n  is_fluid: false\n"
        "template_id: 1\n"
        "html: '<div/>'\n"
        "css: ''\n"
        "targeting:\n  ad_units: []\n  custom: {}\n"
        "status: ACTIVE\n",
    )
    cfg = Config(network_code="000", env="dev", sources=None)
    raw = load_all(tmp_path, cfg)
    assert len(raw) == 1
    assert raw[0]["kind"] == "NativeStyle"
    assert raw[0]["name"] == "card"
