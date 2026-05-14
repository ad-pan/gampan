# tests/unit/test_factory.py
from unittest.mock import MagicMock, patch

import pytest

from gampan.gam.auth import Credentials

_EXTRAS_BY_STRATEGY: dict[str, dict[str, str]] = {
    "env": {"sa_path": "/fake/sa.json"},
    "keychain": {"refresh_token": "rtoken", "client_id": "cid", "client_secret": "csec"},
    "gcloud": {},
}


def _make_creds(strategy: str = "gcloud") -> Credentials:  # type: ignore[type-arg]
    """Return a minimal Credentials fixture with correct _extra for *strategy*."""
    return Credentials(
        principal="test@example.com",
        _token_provider=lambda: "tok",
        _strategy=strategy,  # type: ignore[arg-type]
        _extra=_EXTRAS_BY_STRATEGY[strategy],
    )


def test_soap_factory_returns_native_style_client() -> None:
    creds = _make_creds()
    mock_google_creds = MagicMock()
    with (
        patch("gampan.gam.auth._google_adc_credentials", return_value=mock_google_creds),
        patch("gampan.gam.clients.factory.googleads_oauth2") as mock_oauth2,
        patch("gampan.gam.clients.factory.AdManagerClient") as adm,
    ):
        mock_oauth2.GoogleCredentialsClient.return_value = MagicMock()
        adm.return_value.GetService.return_value = MagicMock()
        from gampan.gam.clients.factory import soap_client_factory

        client = soap_client_factory(network_code="42", creds=creds)
        assert client.__class__.__name__ == "NativeStyleSoapClient"
        mock_oauth2.GoogleCredentialsClient.assert_called_once_with(mock_google_creds)


def test_rest_factory_returns_creative_template_client() -> None:
    creds = _make_creds()
    mock_google_creds = MagicMock()
    with (
        patch("gampan.gam.auth._google_adc_credentials", return_value=mock_google_creds),
        patch("gampan.gam.clients.factory.AdManagerServiceClient") as svc,
    ):
        svc.return_value = MagicMock()
        from gampan.gam.clients.factory import rest_client_factory

        client = rest_client_factory(network_code="42", creds=creds)
        assert client.__class__.__name__ == "CreativeTemplateRestClient"
        svc.assert_called_once_with(credentials=mock_google_creds)


@pytest.mark.parametrize("strategy", ["env", "keychain", "gcloud"])
def test_factory_passes_google_creds_to_soap(strategy: str) -> None:
    """Smoke-test that both factories forward whatever to_google_credentials() returns."""
    creds = _make_creds(strategy=strategy)
    sentinel = MagicMock(name="sentinel_google_creds")

    # Patch all three underlying helper functions; only the matching strategy's
    # helper will be called, but patching all ensures no real network/disk access.
    with (
        patch("gampan.gam.auth._google_adc_credentials", return_value=sentinel),
        patch("gampan.gam.auth._google_service_account_credentials", return_value=sentinel),
        patch("gampan.gam.auth._google_oauth2_credentials", return_value=sentinel),
        patch("gampan.gam.clients.factory.googleads_oauth2") as mock_oauth2,
        patch("gampan.gam.clients.factory.AdManagerClient") as adm,
    ):
        mock_oauth2.GoogleCredentialsClient.return_value = MagicMock()
        adm.return_value.GetService.return_value = MagicMock()
        from gampan.gam.clients.factory import soap_client_factory

        soap_client_factory(network_code="99", creds=creds)
        mock_oauth2.GoogleCredentialsClient.assert_called_once_with(sentinel)
