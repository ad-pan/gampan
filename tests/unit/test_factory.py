# tests/unit/test_factory.py
from unittest.mock import MagicMock, patch


def test_soap_factory_returns_native_style_client() -> None:
    with patch("gampan.gam.clients.factory.AdManagerClient") as adm:
        adm.LoadFromString.return_value.GetService.return_value = MagicMock()
        from gampan.gam.clients.factory import soap_client_factory

        client = soap_client_factory(network_code="42")
        assert client.__class__.__name__ == "NativeStyleSoapClient"


def test_rest_factory_returns_creative_template_client() -> None:
    with patch("gampan.gam.clients.factory.AdManagerServiceClient") as svc:
        svc.return_value = MagicMock()
        from gampan.gam.clients.factory import rest_client_factory

        client = rest_client_factory(network_code="42")
        assert client.__class__.__name__ == "CreativeTemplateRestClient"
