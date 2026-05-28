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
    service.getNativeStylesByStatement.return_value = MagicMock(results=[], totalResultSetSize=0)
    NativeStyleSoapClient(service).list()
    statement = service.getNativeStylesByStatement.call_args.args[0]
    assert statement == {"query": "WHERE status != 'ARCHIVED'"}


def test_list_includes_archived_when_requested() -> None:
    """``include_archived=True`` drops the filter so callers managing
    archived YAML (or auditing) can see every NativeStyle."""
    service = MagicMock()
    service.getNativeStylesByStatement.return_value = MagicMock(results=[], totalResultSetSize=0)
    NativeStyleSoapClient(service).list(include_archived=True)
    statement = service.getNativeStylesByStatement.call_args.args[0]
    assert statement == {"query": ""}


def _archived_ns(name: str) -> NativeStyle:
    return NativeStyle(
        name=name,
        size=Size(width=1, height=1, is_fluid=False),
        template_id=1,
        html="<div/>",
        css="",
        status="ARCHIVED",
    )


def test_update_active_routes_status_via_perform_action() -> None:
    """Status transitions on NativeStyle must go through
    performNativeStyleAction — `updateNativeStyles` with a flipped status
    returns a SOAP payload googleads can't parse (KeyError 'logicalOperator').

    Activating must fire ActivateNativeStyles and strip `status` from the
    body update so the action is the sole source of truth for lifecycle.
    """
    service = MagicMock()
    c = NativeStyleSoapClient(service)
    c.update("990599", _ns("foo"))

    # Action fired with the right xsi_type + statement targeting the gam_id.
    service.performNativeStyleAction.assert_called_once_with(
        {"xsi_type": "ActivateNativeStyles"},
        {"query": "WHERE id = 990599"},
    )
    # Body update happened but with `status` stripped.
    service.updateNativeStyles.assert_called_once()
    [payload_list] = service.updateNativeStyles.call_args.args
    [payload] = payload_list
    assert payload["id"] == "990599"
    assert "status" not in payload
    assert payload["name"] == "foo"


def test_update_archived_routes_status_via_archive_action() -> None:
    """Setting a YAML's status to ARCHIVED through `update` (not via the
    `delete` path) must still route through performNativeStyleAction with
    ArchiveNativeStyles, not the body update."""
    service = MagicMock()
    c = NativeStyleSoapClient(service)
    c.update("990599", _archived_ns("foo"))

    service.performNativeStyleAction.assert_called_once_with(
        {"xsi_type": "ArchiveNativeStyles"},
        {"query": "WHERE id = 990599"},
    )
    [payload_list] = service.updateNativeStyles.call_args.args
    [payload] = payload_list
    assert "status" not in payload
