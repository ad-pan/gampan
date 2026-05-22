# tests/unit/test_soap_client.py
from unittest.mock import MagicMock

from gampan.gam.clients.soap import NativeStyleSoapClient
from gampan.gam.models.native_style import NativeStyle, Size


def _ns(name: str) -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        status="ACTIVE",
    )


def test_list_translates_remote_dicts_to_models() -> None:
    service = MagicMock()
    service.getNativeStylesByStatement.return_value = MagicMock(
        results=[
            {
                "id": "111",
                "name": "a",
                "size": {"width": 1, "height": 1, "isFluid": False},
                "creativeTemplateId": 1,
                "htmlSnippet": "<div/>",
                "cssSnippet": "",
                "targeting": {"adUnits": [], "customTargeting": {}},
                "status": "ACTIVE",
            }
        ],
        totalResultSetSize=1,
    )
    c = NativeStyleSoapClient(service)
    items = c.list()
    assert len(items) == 1
    gam_id, model = items[0]
    assert gam_id == "111"
    assert model.name == "a"


def test_create_returns_new_gam_id() -> None:
    service = MagicMock()
    service.createNativeStyles.return_value = [{"id": "999"}]
    c = NativeStyleSoapClient(service)
    new_id = c.create(_ns("a"))
    assert new_id == "999"


def test_list_filters_archived_by_default() -> None:
    """``include_archived=False`` adds the SOAP PQL filter so ARCHIVED rows
    never reach gampan — that's the only thing keeping them out of plan."""
    service = MagicMock()
    service.getNativeStylesByStatement.return_value = MagicMock(
        results=[], totalResultSetSize=0
    )
    NativeStyleSoapClient(service).list()
    statement = service.getNativeStylesByStatement.call_args.args[0]
    assert statement == {"query": "WHERE status != 'ARCHIVED'"}


def test_list_includes_archived_when_requested() -> None:
    """``include_archived=True`` drops the filter so callers managing
    archived YAML (or auditing) can see every NativeStyle."""
    service = MagicMock()
    service.getNativeStylesByStatement.return_value = MagicMock(
        results=[], totalResultSetSize=0
    )
    NativeStyleSoapClient(service).list(include_archived=True)
    statement = service.getNativeStylesByStatement.call_args.args[0]
    assert statement == {"query": ""}
