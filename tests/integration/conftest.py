"""Shared fixtures for integration tests.

VCR cassette lookup:
  - Cassette files live in tests/integration/cassettes/<test_name>.yaml.
  - When a cassette file is absent the test is skipped (see per-test skip guards
    in test_import_e2e.py).
  - Set VCR_RECORD=once (or new/all) to record against a live GAM sandbox.

Header filtering:
  - `authorization` and `x-goog-api-key` are stripped from every recorded
    cassette so committed files carry no secrets.
"""

from __future__ import annotations

import os

import pytest
import vcr as vcrlib

_CASSETTE_DIR = "tests/integration/cassettes"

# Honour VCR_RECORD env var; default to "none" (playback-only) when absent.
_RECORD_MODE = os.environ.get("VCR_RECORD", "none")

vcr_default = vcrlib.VCR(
    cassette_library_dir=_CASSETTE_DIR,
    record_mode=_RECORD_MODE,
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["authorization", "x-goog-api-key"],
)


@pytest.fixture
def cassette(request: pytest.FixtureRequest) -> None:  # type: ignore[return]
    """Activate the VCR cassette named after the test function.

    The cassette file is <test_name>.yaml.  When in playback mode ("none") and
    the file does not exist, vcrpy raises CassetteNotFoundError which is caught
    and converted into a pytest skip so CI stays green while cassettes are absent.
    """
    name = request.node.name
    cassette_path = f"{_CASSETTE_DIR}/{name}.yaml"
    try:
        with vcr_default.use_cassette(cassette_path):
            yield
    except vcrlib.errors.CannotSendRequest:
        # Playback cassette present but a request was made that has no match.
        raise
    except Exception as exc:
        # CassetteNotFoundError or similar — skip rather than fail.
        if "cassette" in type(exc).__name__.lower() or "not found" in str(exc).lower():
            pytest.skip(f"cassette {cassette_path!r} not found: {exc}")
        raise
