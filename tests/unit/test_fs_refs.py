from pathlib import Path

import pytest
from ruamel.yaml import YAML

from gampan.core.errors import SchemaError
from gampan.core.fs.refs import make_yaml


def test_file_tag_loads_side_file(tmp_path: Path) -> None:
    side = tmp_path / "snippet.html"
    side.write_text("<h1>hi</h1>")
    src = tmp_path / "doc.yaml"
    src.write_text("html: !file ./snippet.html\n")

    yaml = make_yaml(base_dir=tmp_path)
    data = yaml.load(src.read_text())
    assert data["html"] == "<h1>hi</h1>"


def test_file_tag_missing_raises(tmp_path: Path) -> None:
    src = tmp_path / "doc.yaml"
    src.write_text("html: !file ./missing.html\n")

    yaml = make_yaml(base_dir=tmp_path)
    with pytest.raises(SchemaError) as ei:
        yaml.load(src.read_text())
    assert "missing.html" in str(ei.value)


def test_file_tag_traversal_blocked(tmp_path: Path) -> None:
    src = tmp_path / "doc.yaml"
    src.write_text("html: !file /etc/passwd\n")

    yaml = make_yaml(base_dir=tmp_path)
    with pytest.raises(SchemaError) as ei:
        yaml.load(src.read_text())
    assert "outside base_dir" in str(ei.value)
