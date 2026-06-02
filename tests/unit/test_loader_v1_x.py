"""Tests for v1.x YAML loader: _gam_ids dict + scalar _gam_id compat."""

from __future__ import annotations

from pathlib import Path

import pytest

from gampan.core.errors import SchemaError
from gampan.core.fs.config import Config, Environment
from gampan.core.fs.loader import load_all


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_loader_reads_gam_ids_dict(tmp_path: Path) -> None:
    _write(
        tmp_path / "native-styles" / "article-card.yaml",
        """kind: NativeStyle
name: article-card
_gam_ids:
  dev: "943048"
  prod: "961262"
size: {width: 1, height: 1, is_fluid: false}
template_id: 1
html: "<div/>"
css: ""
status: ACTIVE
""",
    )
    out = load_all(
        tmp_path,
        Config(
            network_code="217",
            environments={"dev": Environment(), "prod": Environment()},
        ),
    )
    [item] = out
    assert item["_gam_ids"] == {"dev": "943048", "prod": "961262"}
    assert "_gam_id" not in item


def test_loader_accepts_scalar_gam_id_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path / "native-styles" / "article-card.yaml",
        """kind: NativeStyle
_gam_id: "943048"
name: article-card
size: {width: 1, height: 1, is_fluid: false}
template_id: 1
html: "<div/>"
css: ""
status: ACTIVE
""",
    )
    out = load_all(tmp_path, Config(network_code="217"))
    [item] = out
    # Scalar surfaced as both keys so migration can rewrite on next apply.
    assert item["_gam_id"] == "943048"
    captured = capsys.readouterr()
    assert "scalar `_gam_id` is deprecated" in captured.out


def test_loader_rejects_undeclared_env_in_gam_ids(tmp_path: Path) -> None:
    _write(
        tmp_path / "native-styles" / "foo.yaml",
        """kind: NativeStyle
name: foo
_gam_ids: { staging: "1" }
size: {width: 1, height: 1, is_fluid: false}
template_id: 1
html: "<div/>"
css: ""
status: ACTIVE
""",
    )
    with pytest.raises(SchemaError, match="staging"):
        load_all(
            tmp_path,
            Config(
                network_code="217",
                environments={"dev": Environment(), "prod": Environment()},
            ),
        )
