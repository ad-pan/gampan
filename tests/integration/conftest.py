"""Shared fixtures for integration tests.

VCR cassette lookup:
  - Cassette files live in tests/integration/cassettes/<test_name>.yaml.
  - When a cassette file is absent the test is skipped (see per-test skip guards
    in test_import_e2e.py).
  - Set VCR_RECORD=once (or new/all) to record against a live GAM sandbox.

Secret redaction — cassettes are committed to git, so EVERY layer with potential
auth or org-identifying data gets filtered:

  - request headers: ``authorization``, ``x-goog-api-key``
  - request POST body (form-encoded): ``refresh_token``, ``access_token``,
    ``client_secret``, ``client_id``
  - response JSON body: ``access_token``, ``id_token``
  - any occurrence of the recording network code (from GAMPAN_TEST_NETWORK)
    is replaced with the placeholder ``0`` in request URLs AND response
    bodies, so cassettes don't leak which network was recorded against.
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
_CASSETTE_DIR = (Path(__file__).resolve().parent / "cassettes").resolve()

# Honour VCR_RECORD env var; default to "none" (playback-only) when absent.
_RECORD_MODE = os.environ.get("VCR_RECORD", "none")

# Network code captured at module import time so we can scrub it from cassettes.
# Playback always uses the placeholder.
_NETWORK_PLACEHOLDER = "0"
_RECORDING_NETWORK = os.environ.get("GAMPAN_TEST_NETWORK", _NETWORK_PLACEHOLDER)

_REDACTED = "REDACTED"


def _redact_response_body(response: dict[str, Any]) -> dict[str, Any]:
    """Replace access_token/id_token in JSON bodies and scrub the network code."""
    body = response.get("body", {})
    raw = body.get("string", b"") if isinstance(body, dict) else b""
    if not raw:
        return response
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    # JSON redaction
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            for k in ("access_token", "id_token"):
                if k in parsed:
                    parsed[k] = _REDACTED
            text = json.dumps(parsed, separators=(",", ":"))
    # Network-code scrub (URL paths inside resource names, etc.)
    if _RECORDING_NETWORK != _NETWORK_PLACEHOLDER:
        text = text.replace(_RECORDING_NETWORK, _NETWORK_PLACEHOLDER)
    response["body"] = {**body, "string": text.encode("utf-8")}
    return response


_TOKEN_FORM_FIELDS = ("refresh_token", "access_token", "client_secret", "client_id")
_TOKEN_FIELD_RE = re.compile(
    rb"(?P<field>" + b"|".join(f.encode() for f in _TOKEN_FORM_FIELDS) + rb")=[^&\s]+",
)


def _redact_request_body(request: vcrlib.Request) -> vcrlib.Request:
    """Scrub token-shaped form fields AND network code from URL+body."""
    if _RECORDING_NETWORK != _NETWORK_PLACEHOLDER and _RECORDING_NETWORK in request.uri:
        request.uri = request.uri.replace(_RECORDING_NETWORK, _NETWORK_PLACEHOLDER)
    body = getattr(request, "body", None)
    if body is not None:
        raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
        redacted = _TOKEN_FIELD_RE.sub(
            lambda m: m.group("field") + b"=" + _REDACTED.encode(),
            raw,
        )
        if _RECORDING_NETWORK != _NETWORK_PLACEHOLDER:
            redacted = redacted.replace(_RECORDING_NETWORK.encode(), _NETWORK_PLACEHOLDER.encode())
        if redacted != raw:
            request.body = redacted
    return request


vcr_default = vcrlib.VCR(
    cassette_library_dir=str(_CASSETTE_DIR),
    record_mode=_RECORD_MODE,
    match_on=["method", "scheme", "host", "port", "path", "query"],
    # x-goog-request-params carries the parent resource path (network code).
    # Stripping it keeps the network identity out of recorded cassettes.
    filter_headers=["authorization", "x-goog-api-key", "x-goog-request-params"],
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
