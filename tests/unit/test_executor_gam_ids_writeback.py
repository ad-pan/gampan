"""Task 7 — env-keyed ``_gam_ids`` write-back from the executor.

Replaces the v1 scalar ``_gam_id`` form. The helper now takes ``env`` and
manages a dict block; legacy scalars are migrated transparently on the
next write-back.
"""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from gampan.core.engine.executor import stamp_gam_id_into_yaml


def _reload(path: Path) -> dict:
    return YAML(typ="safe").load(path.read_text(encoding="utf-8"))


def test_new_dict_form_added(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text("kind: NativeStyle\nname: foo\n", encoding="utf-8")
    stamp_gam_id_into_yaml(p, gam_id="943048", env="dev")

    data = _reload(p)
    assert "_gam_ids" in data
    assert isinstance(data["_gam_ids"], dict)
    assert data["_gam_ids"] == {"dev": "943048"}
    # No legacy scalar leaked back in.
    assert "_gam_id" not in data
    # The dict should sit right after ``kind:`` for human readability.
    keys = list(data.keys())
    assert keys.index("_gam_ids") == keys.index("kind") + 1


def test_existing_dict_extended(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text(
        "kind: NativeStyle\n_gam_ids:\n  dev: '943048'\nname: foo\n",
        encoding="utf-8",
    )
    stamp_gam_id_into_yaml(p, gam_id="961262", env="prod")

    data = _reload(p)
    assert data["_gam_ids"] == {"dev": "943048", "prod": "961262"}
    # The original name field survives the round-trip.
    assert data["name"] == "foo"


def test_scalar_gam_id_migrated_on_writeback(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text(
        "kind: NativeStyle\n_gam_id: '943048'\nname: foo\n",
        encoding="utf-8",
    )
    stamp_gam_id_into_yaml(p, gam_id="943048", env="dev")

    data = _reload(p)
    # Scalar form must be gone; dict form present.
    assert "_gam_id" not in data
    assert data["_gam_ids"] == {"dev": "943048"}
    # And the dict landed where the old scalar used to be (right after ``kind:``).
    keys = list(data.keys())
    assert keys.index("_gam_ids") == keys.index("kind") + 1
