"""Shared fixtures for integration tests.

VCR cassette lookup:
  - Cassette files live in tests/integration/cassettes/<test_name>.yaml.
  - When a cassette file is absent the test is skipped (see per-test skip guards
    in test_import_e2e.py).
  - Set VCR_RECORD=once (or new/all) to record against a live GAM sandbox.

Secret redaction — cassettes are committed to git, so EVERY layer with potential
auth data gets filtered:
  - request headers: ``authorization``, ``x-goog-api-key``
  - request POST body (form-encoded): ``refresh_token``, ``access_token``,
    ``client_secret``, ``client_id`` (the OAuth token endpoint receives all
    of these as form params)
  - response JSON body: ``access_token``, ``id_token`` (issued during the
    recording session, expires in ~1h but redacted anyway for hygiene)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
import vcr as vcrlib

# Absolute path so cassettes survive tests that monkeypatch.chdir(tmp_path).
# Resolved relative to this conftest, not cwd, so editor-runs from anywhere work.
_CASSETTE_DIR = (Path(__file__).resolve().parent / "cassettes").resolve()

# Honour VCR_RECORD env var; default to "none" (playback-only) when absent.
_RECORD_MODE = os.environ.get("VCR_RECORD", "none")

_REDACTED = "REDACTED"


def _redact_response_body(response: dict[str, Any]) -> dict[str, Any]:
    """Replace access_token / id_token in a recorded JSON response body."""
    body = response.get("body", {})
    raw = body.get("string", b"") if isinstance(body, dict) else b""
    if not raw:
        return response
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    # Only attempt JSON redaction for plausibly-JSON payloads
    stripped = text.lstrip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return response
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return response
    if isinstance(parsed, dict):
        for k in ("access_token", "id_token"):
            if k in parsed:
                parsed[k] = _REDACTED
    redacted = json.dumps(parsed, separators=(",", ":")).encode("utf-8")
    response["body"] = {**body, "string": redacted}
    return response


_TOKEN_FORM_FIELDS = ("refresh_token", "access_token", "client_secret", "client_id")
_TOKEN_FIELD_RE = re.compile(
    rb"(?P<field>" + b"|".join(f.encode() for f in _TOKEN_FORM_FIELDS) + rb")=[^&\s]+",
)


def _redact_request_body(request: vcrlib.Request) -> vcrlib.Request:
    """Replace token-shaped form fields in a urlencoded POST body."""
    body = getattr(request, "body", None)
    if body is None:
        return request
    raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
    redacted = _TOKEN_FIELD_RE.sub(lambda m: m.group("field") + b"=" + _REDACTED.encode(), raw)
    if redacted != raw:
        request.body = redacted
    return request


vcr_default = vcrlib.VCR(
    cassette_library_dir=str(_CASSETTE_DIR),
    record_mode=_RECORD_MODE,
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["authorization", "x-goog-api-key"],
    before_record_request=_redact_request_body,
    before_record_response=_redact_response_body,
)


@pytest.fixture
def cassette(request: pytest.FixtureRequest) -> None:  # type: ignore[return]
    """Activate the VCR cassette named after the test function.

    The cassette file is <test_name>.yaml under tests/integration/cassettes/
    (resolved absolutely so monkeypatch.chdir doesn't relocate the write target).
    When in playback mode ("none") and the file does not exist, vcrpy raises
    CassetteNotFoundError which is caught and converted into a pytest skip so
    CI stays green while cassettes are absent.
    """
    name = request.node.name
    cassette_path = str(_CASSETTE_DIR / f"{name}.yaml")
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
