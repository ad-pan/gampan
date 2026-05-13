import contextlib

from gampan.core.errors import GamApiPermanentError, GamApiRetryableError
from gampan.gam.clients._retry import retry_transient


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    @retry_transient
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise GamApiRetryableError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_does_not_retry_permanent() -> None:
    calls = {"n": 0}

    @retry_transient
    def boom():
        calls["n"] += 1
        raise GamApiPermanentError("nope")

    with contextlib.suppress(GamApiPermanentError):
        boom()
    assert calls["n"] == 1
