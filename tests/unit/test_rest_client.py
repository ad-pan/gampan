"""Tests for the REST client. Note: CreativeTemplate.create/update/delete
are not in the REST Beta — those methods raise NotImplementedError."""

from unittest.mock import MagicMock

import pytest

from gampan.gam.clients.rest import CreativeTemplateRestClient


def _proto_item(name: str, snippet: str = "<div/>"):
    """Mimic a proto-plus CreativeTemplate message with attribute access."""
    m = MagicMock()
    m.name = name
    m.description = "test"
    m.snippet = snippet
    # Enum-like: object with .name attribute
    m.type_ = MagicMock()
    m.type_.name = "CUSTOM"
    m.status = MagicMock()
    m.status.name = "ACTIVE"
    m.variables = []
    return m


def test_list_iterates_pager_and_maps_to_models() -> None:
    svc = MagicMock()
    svc.list_creative_templates.return_value = iter(
        [
            _proto_item("networks/123/creativeTemplates/ct-1"),
            _proto_item("networks/123/creativeTemplates/ct-2"),
        ]
    )
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    items = c.list()
    assert len(items) == 2
    assert items[0][0] == "ct-1"
    assert items[0][1].name == "networks/123/creativeTemplates/ct-1"
    assert items[1][0] == "ct-2"


def test_get_uses_full_resource_name() -> None:
    svc = MagicMock()
    svc.get_creative_template.return_value = _proto_item("networks/123/creativeTemplates/ct-9")
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    t = c.get("ct-9")
    assert t.name == "networks/123/creativeTemplates/ct-9"
    svc.get_creative_template.assert_called_once_with(
        name="networks/123/creativeTemplates/ct-9",
    )


def test_create_raises_not_implemented() -> None:
    c = CreativeTemplateRestClient(MagicMock(), network_path="networks/123")
    with pytest.raises(NotImplementedError, match="REST Beta"):
        c.create(MagicMock())


def test_update_raises_not_implemented() -> None:
    c = CreativeTemplateRestClient(MagicMock(), network_path="networks/123")
    with pytest.raises(NotImplementedError, match="REST Beta"):
        c.update("ct-1", MagicMock())


def test_delete_raises_not_implemented() -> None:
    c = CreativeTemplateRestClient(MagicMock(), network_path="networks/123")
    with pytest.raises(NotImplementedError, match="REST Beta"):
        c.delete("ct-1")


def _proto_string_variable(display_name: str, default: str = "") -> MagicMock:
    """Mimic a proto-plus CreativeTemplateVariable with the string_variable oneof set."""
    v = MagicMock()
    v.unique_display_name = display_name
    v.label = display_name
    v.description = ""
    v.required = False
    # Other oneof variants absent (no _pb byte size → falls through)
    for absent in ("url_variable", "list_string_variable", "asset_variable", "long_variable"):
        m = MagicMock()
        m._pb.ByteSize.return_value = 0
        setattr(v, absent, m)
    # Active variant: string_variable
    sv = MagicMock()
    sv._pb.ByteSize.return_value = 1
    sv.default_value = default
    v.string_variable = sv
    # Disable the WhichOneof short-circuit so we exercise the probe path
    v._pb = None
    return v


def test_list_maps_oneof_variable_to_string_type() -> None:
    """REST variables use a oneof; verify string_variable maps to type=STRING."""
    item = MagicMock()
    item.name = "networks/123/creativeTemplates/ct-1"
    item.description = "t"
    item.snippet = "<div/>"
    item.type_ = MagicMock()
    item.type_.name = "CUSTOM"
    item.status = MagicMock()
    item.status.name = "ACTIVE"
    item.variables = [_proto_string_variable("headline", default="Hi")]

    svc = MagicMock()
    svc.list_creative_templates.return_value = iter([item])
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    items = c.list()
    assert len(items) == 1
    template = items[0][1]
    assert len(template.variables) == 1
    var = template.variables[0]
    assert var.name == "headline"
    assert var.type == "STRING"
    assert var.default == "Hi"
