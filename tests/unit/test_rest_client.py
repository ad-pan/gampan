"""Tests for the REST client. Note: CreativeTemplate.create/update/delete
are not in the REST Beta — those methods raise NotImplementedError."""

from unittest.mock import MagicMock

import pytest

from gampan.gam.clients.rest import CreativeTemplateRestClient


def _proto_item(
    resource_path: str,
    display_name: str = "",
    snippet: str = "<div/>",
):
    """Mimic a proto-plus CreativeTemplate message with attribute access."""
    m = MagicMock()
    m.name = resource_path  # GAM resource path (identity)
    m.display_name = display_name  # user-friendly label (our model.name)
    m.description = "test"
    m.snippet = snippet
    # Enum-like: object with .name attribute
    m.type_ = MagicMock()
    m.type_.name = "CUSTOM"
    m.status = MagicMock()
    m.status.name = "ACTIVE"
    m.variables = []
    return m


def test_list_uses_display_name_for_model_name_and_id_for_gam_id() -> None:
    svc = MagicMock()
    svc.list_creative_templates.return_value = iter(
        [
            _proto_item("networks/123/creativeTemplates/ct-1", display_name="Standard Text Ad"),
            _proto_item("networks/123/creativeTemplates/ct-2", display_name="Premium Display"),
        ]
    )
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    items = c.list()
    assert len(items) == 2
    # gam_id comes from the resource path; model.name comes from display_name.
    assert items[0] == ("ct-1", items[0][1])
    assert items[0][1].name == "Standard Text Ad"
    assert items[1] == ("ct-2", items[1][1])
    assert items[1][1].name == "Premium Display"


def test_list_falls_back_to_numeric_id_when_display_name_empty() -> None:
    svc = MagicMock()
    svc.list_creative_templates.return_value = iter(
        [_proto_item("networks/123/creativeTemplates/ct-1", display_name="")]
    )
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    items = c.list()
    assert items[0][1].name == "ct-1"


def test_get_uses_full_resource_name() -> None:
    svc = MagicMock()
    svc.get_creative_template.return_value = _proto_item(
        "networks/123/creativeTemplates/ct-9",
        display_name="Standard Text Ad",
    )
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    t = c.get("ct-9")
    assert t.name == "Standard Text Ad"
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
    item.display_name = "Variant Test"
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


def _proto_list_variable(
    display_name: str,
    default: str,
    choices: list[tuple[str, str]],
    allow_other_choice: bool = False,
) -> MagicMock:
    """Mimic a proto-plus CreativeTemplateVariable with the list_string_variable oneof set."""
    v = MagicMock()
    v.unique_display_name = display_name
    v.label = display_name
    v.description = ""
    v.required = True
    for absent in ("string_variable", "url_variable", "asset_variable", "long_variable"):
        m = MagicMock()
        m._pb.ByteSize.return_value = 0
        setattr(v, absent, m)
    lsv = MagicMock()
    lsv._pb.ByteSize.return_value = 1
    lsv.default_value = default
    lsv.allow_other_choice = allow_other_choice
    proto_choices = []
    for label, value in choices:
        c = MagicMock()
        c.label = label
        c.value = value
        proto_choices.append(c)
    lsv.choices = proto_choices
    v.list_string_variable = lsv
    v._pb = None
    return v


def test_list_string_variable_captures_choices() -> None:
    """LIST variables carry a structured choices array — the import path must
    extract it so the on-disk YAML preserves the dropdown options."""
    item = MagicMock()
    item.name = "networks/123/creativeTemplates/ct-99"
    item.display_name = "Text Ad"
    item.description = ""
    item.snippet = "<div/>"
    item.type_ = MagicMock()
    item.type_.name = "CUSTOM"
    item.status = MagicMock()
    item.status.name = "ACTIVE"
    item.variables = [
        _proto_list_variable(
            "Targetwindow",
            default="_blank",
            choices=[("_blank", "_blank"), ("_top", "_top")],
            allow_other_choice=False,
        )
    ]

    svc = MagicMock()
    svc.list_creative_templates.return_value = iter([item])
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    template = c.list()[0][1]
    var = template.variables[0]
    assert var.type == "LIST"
    assert var.default == "_blank"
    assert var.allow_other_choice is False
    assert var.choices is not None
    assert [(ch.label, ch.value) for ch in var.choices] == [("_blank", "_blank"), ("_top", "_top")]
