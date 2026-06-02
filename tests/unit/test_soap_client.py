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


def test_update_status_only_calls_perform_action_only() -> None:
    """When the diff is purely a status transition (the un-archive case
    that surfaced the 'logicalOperator' parse bug), only fire the
    lifecycle action — do NOT call ``updateNativeStyles`` because it has
    nothing to update on the body side and its empty-update response
    trips zeep's deserialiser.
    """
    service = MagicMock()
    NativeStyleSoapClient(service).update(
        "990599", _ns("foo"), changed_paths=["status"]
    )

    service.performNativeStyleAction.assert_called_once_with(
        {"xsi_type": "ActivateNativeStyles"},
        {"query": "WHERE id = 990599"},
    )
    service.updateNativeStyles.assert_not_called()


def test_update_archive_via_update_status_only() -> None:
    """Setting a YAML's status to ARCHIVED through ``update`` (not via the
    ``delete`` path) routes through performNativeStyleAction; no body call.
    """
    service = MagicMock()
    NativeStyleSoapClient(service).update(
        "990599", _archived_ns("foo"), changed_paths=["status"]
    )

    service.performNativeStyleAction.assert_called_once_with(
        {"xsi_type": "ArchiveNativeStyles"},
        {"query": "WHERE id = 990599"},
    )
    service.updateNativeStyles.assert_not_called()


def test_update_body_only_skips_perform_action() -> None:
    """When no status path is in the diff, the lifecycle action is not
    called — only body fields go through ``updateNativeStyles`` (with
    ``status`` stripped so the body payload owns nothing lifecycle-related).
    """
    service = MagicMock()
    NativeStyleSoapClient(service).update(
        "990599", _ns("foo"), changed_paths=["css", "html"]
    )

    service.performNativeStyleAction.assert_not_called()
    service.updateNativeStyles.assert_called_once()
    [payload_list] = service.updateNativeStyles.call_args.args
    [payload] = payload_list
    assert payload["id"] == "990599"
    assert "status" not in payload  # status is never in the body payload
    assert payload["name"] == "foo"


def test_update_status_and_body_calls_both() -> None:
    """A combined status + body diff exercises both endpoints — action for
    lifecycle, body call for the field changes."""
    service = MagicMock()
    NativeStyleSoapClient(service).update(
        "990599", _ns("foo"), changed_paths=["status", "css"]
    )

    service.performNativeStyleAction.assert_called_once()
    service.updateNativeStyles.assert_called_once()


def test_update_legacy_no_changed_paths_calls_both_conservatively() -> None:
    """Legacy callers that don't pass ``changed_paths`` get the v1 behaviour
    — fire both endpoints conservatively. This is the pre-fix shape, kept so
    no caller silently regresses, but the executor now always passes paths.
    """
    service = MagicMock()
    NativeStyleSoapClient(service).update("990599", _ns("foo"))  # no kwarg

    service.performNativeStyleAction.assert_called_once()
    service.updateNativeStyles.assert_called_once()
