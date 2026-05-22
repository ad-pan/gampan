# tests/unit/test_cli_import.py
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app
from gampan.gam.models.native_style import NativeStyle, Size


def _ns(name: str = "card") -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=320, height=250, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        status="ACTIVE",
    )


def _init_repo(tmp_path: Path) -> None:
    (tmp_path / ".gampan").mkdir()
    (tmp_path / ".gampan" / "config.yml").write_text("network_code: '42'\nenv: dev\n")
    (tmp_path / "native-styles").mkdir()


def test_import_writes_yaml_and_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    fake_client = MagicMock()
    fake_client.list.return_value = [("999", _ns())]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output
    # NativeStyles land in native-styles/ with the .native-style.yaml suffix
    # so the file remains self-identifying even when flattened.
    yaml_path = tmp_path / "native-styles" / "card.native-style.yaml"
    assert yaml_path.exists()
    state_path = tmp_path / ".gampan" / "state.json"
    assert state_path.exists()
    # State key must use gam_id, not name
    assert "NativeStyle:999" in state_path.read_text()
    # _gam_id field must be embedded in the YAML
    assert "_gam_id: '999'" in yaml_path.read_text()


def test_import_korean_name_preserved_in_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Korean-only name is preserved in the slug (CJK support); state key still gam_id."""
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    fake_client = MagicMock()
    fake_client.list.return_value = [("777", _ns(name="한국어광고"))]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output
    # CJK passes through slugify unchanged; kind-suffix still appended.
    yaml_path = tmp_path / "native-styles" / "한국어광고.native-style.yaml"
    ns_dir = tmp_path / "native-styles"
    assert yaml_path.exists(), (
        f"expected 한국어광고.native-style.yaml, got: {list(ns_dir.iterdir())}"
    )
    # gam_id remains the canonical state identity
    state_path = tmp_path / ".gampan" / "state.json"
    assert "NativeStyle:777" in state_path.read_text()


def test_import_unrepresentable_name_falls_back_to_gam_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Names with NO letters/digits in any script (e.g. only punctuation/emoji)
    do still fall back to gam_id."""
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    fake_client = MagicMock()
    fake_client.list.return_value = [("777", _ns(name="!!!@@@"))]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "native-styles" / "777.native-style.yaml").exists()


def test_import_removes_orphan_yaml_after_remote_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a remote resource is renamed (same ``_gam_id``, new slug)
    ``import`` writes the YAML under the new slug *and* deletes the
    stale old-slug YAML + its ``.html`` / ``.css`` side files so the
    next plan does not trip ``validate_no_duplicates``."""
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)

    # Seed: imitate a prior import that wrote ``old-name`` files for gam_id 555.
    ns_dir = tmp_path / "native-styles"
    (ns_dir / "old-name.native-style.yaml").write_text(
        "kind: NativeStyle\n_gam_id: '555'\nname: old-name\n", encoding="utf-8"
    )
    (ns_dir / "old-name.native-style.html").write_text("<div/>", encoding="utf-8")
    (ns_dir / "old-name.native-style.css").write_text(".x{}", encoding="utf-8")

    fake_client = MagicMock()
    fake_client.list.return_value = [("555", _ns(name="new-name"))]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output
    assert (ns_dir / "new-name.native-style.yaml").exists()
    # Orphan YAML + side files cleaned up
    assert not (ns_dir / "old-name.native-style.yaml").exists()
    assert not (ns_dir / "old-name.native-style.html").exists()
    assert not (ns_dir / "old-name.native-style.css").exists()
    # Audit line surfaces the removal so the operator notices
    assert "Removed orphan YAML" in result.output


def test_import_leaves_user_authored_yaml_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """User-authored YAML (no ``_gam_id`` field yet) must never be deleted
    by ``import`` — only previously-imported files participate in
    rename-orphan cleanup."""
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)

    ns_dir = tmp_path / "native-styles"
    # Author a brand-new local YAML — no _gam_id yet.
    (ns_dir / "draft.native-style.yaml").write_text(
        "kind: NativeStyle\nname: draft-only\n", encoding="utf-8"
    )

    fake_client = MagicMock()
    fake_client.list.return_value = [("888", _ns(name="other"))]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output
    # Imported file landed
    assert (ns_dir / "other.native-style.yaml").exists()
    # Local draft survived
    assert (ns_dir / "draft.native-style.yaml").exists()


def test_import_duplicate_slug_appends_gam_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two resources with the same slug get unique filenames via -{gam_id} suffix."""
    monkeypatch.chdir(tmp_path)
    _init_repo(tmp_path)
    fake_client = MagicMock()
    # Both "Card Ad" and "card-ad" slugify to "card-ad"
    fake_client.list.return_value = [
        ("101", _ns(name="Card Ad")),
        ("102", _ns(name="card-ad")),
    ]
    with patch(
        "gampan.cli.import_cmd.build_clients",
        return_value={"NativeStyle": fake_client},
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output
    ns_dir = tmp_path / "native-styles"
    # `Path.stem` strips only the trailing `.yaml`, leaving e.g.
    # ``card-ad.native-style`` — strip the kind-suffix so we can assert on
    # the slug part alone.
    slug_stems = {p.stem.removesuffix(".native-style") for p in ns_dir.glob("*.yaml")}
    assert "card-ad" in slug_stems
    assert "card-ad-102" in slug_stems
    state = json.loads((tmp_path / ".gampan" / "state.json").read_text())
    assert "NativeStyle:101" in state["resources"]
    assert "NativeStyle:102" in state["resources"]
