import pytest

from gampan.core.errors import (
    AuthError,
    ConfigError,
    GamApiError,
    GamApiPermanentError,
    GamApiRetryableError,
    GampanError,
    SchemaError,
    StateError,
)


def test_all_errors_inherit_gampan_error() -> None:
    for cls in [ConfigError, AuthError, SchemaError, StateError, GamApiError]:
        assert issubclass(cls, GampanError)


def test_gam_api_subclasses() -> None:
    assert issubclass(GamApiRetryableError, GamApiError)
    assert issubclass(GamApiPermanentError, GamApiError)


def test_can_raise_and_catch() -> None:
    with pytest.raises(GampanError):
        raise SchemaError("bad yaml")
