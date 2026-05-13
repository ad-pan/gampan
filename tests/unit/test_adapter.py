from unittest.mock import MagicMock

from gampan.gam.clients.adapter import build_client_map


def test_adapter_routes_by_kind() -> None:
    soap_factory = MagicMock(return_value="soap-client")
    rest_factory = MagicMock(return_value="rest-client")
    mapping = build_client_map(soap_factory=soap_factory, rest_factory=rest_factory)
    assert mapping["NativeStyle"] == "soap-client"
    assert mapping["CreativeTemplate"] == "rest-client"
