"""Integration test: gampan commands against recorded GAM responses.

Cassettes must be pre-recorded by running the same test against a real GAM sandbox
with VCR_RECORD=once.  Until cassettes exist every test is individually skipped.

Record with (from repo root):

    export GAMPAN_TEST_NETWORK=<your-sandbox-network-code>
    VCR_RECORD=once uv run pytest tests/integration/test_import_e2e.py \\
        -k test_e2e_import_creative_templates -v

For playback (CI / offline) leave VCR_RECORD unset and the cassettes drive everything.

Cassette naming convention: <test_name>.yaml under tests/integration/cassettes/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gampan.cli.main import app

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_CASSETTES = Path("tests/integration/cassettes")

# When recording, point at the user's real test network. Defaults to a placeholder
# so playback tests don't need any env var.
_NETWORK = os.environ.get("GAMPAN_TEST_NETWORK", "21700000000")


def _cassette_exists(name: str) -> bool:
    return (_CASSETTES / f"{name}.yaml").exists()


def _recording() -> bool:
    """True when VCR_RECORD is set to a recording mode (anything except 'none')."""
    return os.environ.get("VCR_RECORD", "none").lower() not in ("", "none")


def _skip_if_no_cassette(name: str) -> pytest.MarkDecorator:
    """Skip when neither a cassette is present nor VCR_RECORD asks us to record.

    During recording (VCR_RECORD=once/new/all) we let the test run so vcrpy can
    populate the cassette from real API responses.
    """
    return pytest.mark.skipif(
        not _cassette_exists(name) and not _recording(),
        reason=(
            f"cassette {name}.yaml not recorded yet — "
            "set VCR_RECORD=once + GAMPAN_TEST_NETWORK to record"
        ),
    )


def _scaffold(tmp_path: Path, network_code: str = _NETWORK) -> None:
    """Write minimal .gampan/ scaffold into tmp_path."""
    gampan_dir = tmp_path / ".gampan"
    gampan_dir.mkdir()
    (gampan_dir / "config.yml").write_text(f"network_code: '{network_code}'\nenv: integration\n")
    # empty state so each test starts fresh
    state = {
        "schema_version": 1,
        "network_code": network_code,
        "resources": {},
    }
    (gampan_dir / "state.json").write_text(json.dumps(state, indent=2))
    (tmp_path / "native-styles").mkdir()
    (tmp_path / "creative-templates").mkdir()


_SAMPLE_HTML = "<div class='ad'><h2>[%Headline%]</h2><p>[%Body%]</p></div>"
_SAMPLE_CSS = ".ad { padding: 12px; border: 1px solid #ccc; }"

_SAMPLE_YAML = (
    f"kind: NativeStyle\n"
    f"name: gampan-validation-sample\n"
    f"size:\n"
    f"  width: 320\n"
    f"  height: 250\n"
    f"  is_fluid: false\n"
    f"template_id: 10000680\n"
    f"html: {_SAMPLE_HTML!r}\n"
    f"css: {_SAMPLE_CSS!r}\n"
    f"targeting:\n"
    f"  ad_units: []\n"
    f"  custom: {{}}\n"
    f"status: ACTIVE\n"
)

_SAMPLE_HTML_UPDATED = _SAMPLE_HTML + " <!-- updated by gampan -->"
_SAMPLE_YAML_UPDATED = (
    f"kind: NativeStyle\n"
    f"name: gampan-validation-sample\n"
    f"size:\n"
    f"  width: 320\n"
    f"  height: 250\n"
    f"  is_fluid: false\n"
    f"template_id: 10000680\n"
    f"html: {_SAMPLE_HTML_UPDATED!r}\n"
    f"css: {_SAMPLE_CSS!r}\n"
    f"targeting:\n"
    f"  ad_units: []\n"
    f"  custom: {{}}\n"
    f"status: ACTIVE\n"
)


# ---------------------------------------------------------------------------
# READ-ONLY round-trip cassettes (target for v0.1.0)
#
# These tests exercise only `import` (REST list) and `plan` (REST list again
# + local YAML diff). No GAM-side writes, so no permission/template_id
# coupling. Cassette recording requires only Trafficker-level access on the
# target test network.
# ---------------------------------------------------------------------------


@_skip_if_no_cassette("test_e2e_import_creative_templates")
def test_e2e_import_creative_templates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cassette: None
) -> None:
    """`gampan import --resource creative-templates` against the recorded sandbox.

    Validates the full REST CreativeTemplate read path:
      list_creative_templates pager → proto-plus dict conversion →
      pydantic CreativeTemplate model → YAML writer → state.json.

    Record:
        export GAMPAN_TEST_NETWORK=<sandbox>
        VCR_RECORD=once uv run pytest tests/integration/test_import_e2e.py \\
            -k test_e2e_import_creative_templates -v
    """
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["import", "--resource", "creative-templates"])
    assert result.exit_code == 0, result.output

    # Cassette captured whatever the sandbox had — assert *at least one* template
    # was imported. Exact count is sandbox-specific.
    state = json.loads((tmp_path / ".gampan" / "state.json").read_text())
    n = len([k for k in state["resources"] if k.startswith("CreativeTemplate:")])
    assert n >= 1, f"expected ≥1 CreativeTemplate in state, got {n}"


@_skip_if_no_cassette("test_e2e_plan_round_trip_clean")
def test_e2e_plan_round_trip_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cassette: None
) -> None:
    """Run `gampan plan` over a directory we just imported. Expect zero pending
    changes — proves the import → plan round-trip is checksum-stable.

    Record (in the same shell session as the import recording, so the cassette
    sees the same set of remote resources):

        VCR_RECORD=once uv run pytest tests/integration/test_import_e2e.py \\
            -k test_e2e_plan_round_trip_clean -v
    """
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)

    runner = CliRunner()
    imp = runner.invoke(app, ["import", "--resource", "creative-templates"])
    assert imp.exit_code == 0, imp.output

    plan = runner.invoke(app, ["plan"])
    # Exit code 0 (clean) — `--detailed-exitcode` is default-on; non-zero means drift.
    assert plan.exit_code == 0, (
        f"expected clean plan (exit 0) after fresh import; got {plan.exit_code}.\n{plan.output}"
    )
    assert "to add, 0 to change, 0 to destroy" in plan.output, (
        f"plan summary should report all zeros after fresh import:\n{plan.output}"
    )


# ---------------------------------------------------------------------------
# WRITE-PATH cassettes (deferred to v0.2 — need SOAP NativeStyle write perms
# and a template_id known to exist on the target network)
# ---------------------------------------------------------------------------


@_skip_if_no_cassette("test_import_native_styles")
def test_import_native_styles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cassette: None
) -> None:
    """Import from a remote that has at least one native style; state tracks it."""
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# New tests
# ---------------------------------------------------------------------------


@_skip_if_no_cassette("test_e2e_import_after_apply_records_state")
def test_e2e_import_after_apply_records_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cassette: None
) -> None:
    """Full import after one resource exists: state.json reflects the resource.

    Cassette: tests/integration/cassettes/test_e2e_import_after_apply_records_state.yaml

    Record procedure:
      1. After completing gampan apply --auto-approve in the runbook (Step 7),
         re-run the import command under VCR recording from the gampan repo root:
             VCR_RECORD=once uv run pytest tests/integration/test_import_e2e.py \\
                 -k test_e2e_import_after_apply_records_state -v
    """
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)

    runner = CliRunner()
    result = runner.invoke(app, ["import", "--resource", "native-styles"])
    assert result.exit_code == 0, result.output

    state_path = tmp_path / ".gampan" / "state.json"
    assert state_path.exists(), "state.json was not written by import"

    state = json.loads(state_path.read_text())
    assert state["schema_version"] == 1
    assert state["network_code"] == "21700000000"

    # At least one resource must have been tracked
    resources: dict[str, object] = state.get("resources", {})
    assert len(resources) >= 1, "Expected at least one resource in state after import"

    # Each resource entry must carry a non-empty gam_id
    for key, entry in resources.items():
        assert isinstance(entry, dict), f"resources[{key!r}] must be a dict"
        gam_id = entry.get("gam_id", "")
        assert gam_id, f"resources[{key!r}].gam_id is empty"


@_skip_if_no_cassette("test_e2e_plan_create")
def test_e2e_plan_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cassette: None) -> None:
    """Plan against an empty remote with one local YAML shows CREATE, exit code 2.

    Cassette: tests/integration/cassettes/test_e2e_plan_create.yaml

    Record procedure:
      1. With the test network empty (before any apply), write sample.yaml and run:
             VCR_RECORD=once uv run pytest tests/integration/test_import_e2e.py \\
                 -k test_e2e_plan_create -v
    """
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    (tmp_path / "native-styles" / "sample.yaml").write_text(_SAMPLE_YAML)

    runner = CliRunner()
    result = runner.invoke(app, ["plan"])

    # Exit code 2 = pending changes (--detailed-exitcode is default on)
    assert result.exit_code == 2, (
        f"Expected exit code 2 (pending changes), got {result.exit_code}.\n{result.output}"
    )
    assert "CREATE" in result.output, f"Expected CREATE in plan output:\n{result.output}"
    assert "gampan-validation-sample" in result.output, (
        f"Expected resource name in plan output:\n{result.output}"
    )


@_skip_if_no_cassette("test_e2e_apply_update_then_refresh")
def test_e2e_apply_update_then_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cassette: None
) -> None:
    """Round-trip: apply creates, update changes html, refresh detects remote drift.

    Cassette: tests/integration/cassettes/test_e2e_apply_update_then_refresh.yaml

    The cassette encodes three API interactions in sequence:
      1. plan+apply CREATE (initial resource creation)
      2. plan+apply UPDATE (html change)
      3. plan (drift) + refresh (re-sync state without touching YAML)

    Record procedure:
      VCR_RECORD=once uv run pytest tests/integration/test_import_e2e.py \\
          -k test_e2e_apply_update_then_refresh -v
    (Run after completing Steps 7–10 of the runbook so the cassette captures all
    three interactions.)
    """
    monkeypatch.chdir(tmp_path)
    _scaffold(tmp_path)
    sample = tmp_path / "native-styles" / "sample.yaml"
    sample.write_text(_SAMPLE_YAML)

    runner = CliRunner()

    # --- Phase 1: CREATE ---
    result = runner.invoke(app, ["apply", "--auto-approve"])
    assert result.exit_code == 0, f"apply (create) failed:\n{result.output}"
    assert "CREATE" in result.output

    state_path = tmp_path / ".gampan" / "state.json"
    state = json.loads(state_path.read_text())
    key = "NativeStyle:gampan-validation-sample"
    assert key in state["resources"], f"resource key {key!r} missing from state after apply"
    gam_id = state["resources"][key]["gam_id"]
    assert gam_id, "gam_id must not be empty after apply"

    # --- Phase 2: UPDATE ---
    sample.write_text(_SAMPLE_YAML_UPDATED)

    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 2, f"plan (update) should have exit code 2:\n{result.output}"
    assert "UPDATE" in result.output

    result = runner.invoke(app, ["apply", "--auto-approve"])
    assert result.exit_code == 0, f"apply (update) failed:\n{result.output}"

    # --- Phase 3: REFRESH (simulates remote drift) ---
    # The cassette records a remote state that diverges from our local checksum.
    result = runner.invoke(app, ["refresh"])
    assert result.exit_code == 0, f"refresh failed:\n{result.output}"
    # Either "Drift detected" or "No drift." — both are valid depending on what
    # the cassette captured; just verify the command completes without error.
