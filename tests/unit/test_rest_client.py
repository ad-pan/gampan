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


def _proto_long_variable(display_name: str, default: int | None = None) -> MagicMock:
    """Mimic a proto-plus CreativeTemplateVariable with the long_variable oneof set."""
    v = MagicMock()
    v.unique_display_name = display_name
    v.label = display_name
    v.description = ""
    v.required = True
    for absent in ("string_variable", "url_variable", "list_string_variable", "asset_variable"):
        m = MagicMock()
        m._pb.ByteSize.return_value = 0
        setattr(v, absent, m)
    lv = MagicMock()
    lv._pb.ByteSize.return_value = 1
    # proto-plus surfaces long defaults as ints (or 0 when unset). Use 0
    # for the "no default" case because the variant must still expose the
    # attribute — the rest client treats 0 as a real value, not "absent".
    lv.default_value = default if default is not None else ""
    v.long_variable = lv
    v._pb = None
    return v


def _proto_asset_variable(
    display_name: str,
    mime_types: list[str] | None = None,
) -> MagicMock:
    """Mimic a proto-plus CreativeTemplateVariable with the asset_variable oneof set."""
    v = MagicMock()
    v.unique_display_name = display_name
    v.label = display_name
    v.description = ""
    v.required = True
    for absent in ("string_variable", "url_variable", "list_string_variable", "long_variable"):
        m = MagicMock()
        m._pb.ByteSize.return_value = 0
        setattr(v, absent, m)
    av = MagicMock()
    av._pb.ByteSize.return_value = 1
    av.default_value = ""
    proto_mts = []
    for name in mime_types or []:
        m = MagicMock()
        m.name = name
        proto_mts.append(m)
    av.mime_types = proto_mts
    v.asset_variable = av
    v._pb = None
    return v


def test_long_variable_maps_to_number_type() -> None:
    """LONG variables (GAM's Number type) must surface as type=NUMBER on the
    flat model — previously they were silently degraded to STRING, losing
    the type signal storybook-adpan needs to render a numeric input."""
    item = MagicMock()
    item.name = "networks/123/creativeTemplates/ct-50"
    item.display_name = "Flash Overlay"
    item.description = ""
    item.snippet = "<div/>"
    item.type_ = MagicMock()
    item.type_.name = "CUSTOM"
    item.status = MagicMock()
    item.status.name = "ACTIVE"
    item.variables = [
        _proto_long_variable("Creativezindex", default=2147483640),
        _proto_long_variable("Width", default=None),
    ]

    svc = MagicMock()
    svc.list_creative_templates.return_value = iter([item])
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    template = c.list()[0][1]
    zindex, width = template.variables
    assert zindex.type == "NUMBER"
    # Long default is an int on the proto; rest client casts to str for
    # uniformity with the other variants.
    assert zindex.default == "2147483640"
    assert width.type == "NUMBER"
    # default_value="" on the proto means absent — should not surface a default.
    assert width.default is None


def test_asset_variable_captures_mime_types() -> None:
    """ASSET variables may declare allowed MIME types — we preserve the
    proto enum names verbatim and emit them in a deterministic
    (alphabetical) order so YAML imports stay stable across the
    non-deterministic ordering GAM's REST endpoint returns. Variables
    without a constraint must not surface an empty list (proto-plus
    collapses absent and explicit-empty)."""
    item = MagicMock()
    item.name = "networks/123/creativeTemplates/ct-70"
    item.display_name = "Image Banner"
    item.description = ""
    item.snippet = "<div/>"
    item.type_ = MagicMock()
    item.type_.name = "CUSTOM"
    item.status = MagicMock()
    item.status.name = "ACTIVE"
    item.variables = [
        _proto_asset_variable("Imagefile", mime_types=["JPG", "PNG", "GIF"]),
        _proto_asset_variable("AnyAsset", mime_types=None),
    ]

    svc = MagicMock()
    svc.list_creative_templates.return_value = iter([item])
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    template = c.list()[0][1]
    constrained, unconstrained = template.variables
    assert constrained.type == "ASSET"
    assert constrained.mime_types == ["GIF", "JPG", "PNG"]
    assert unconstrained.type == "ASSET"
    assert unconstrained.mime_types is None


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


def _proto_empty_asset_variable(display_name: str) -> MagicMock:
    """Real GAM REST returns `asset_variable: {}` for File variables without
    mime_types. The submessage IS set in the proto (HasField=True) but its
    ByteSize is 0. Old dispatch missed this and fell through to STRING.
    """
    v = MagicMock()
    v.unique_display_name = display_name
    v.label = display_name
    v.description = ""
    v.required = True
    for absent in ("string_variable", "url_variable", "list_string_variable", "long_variable"):
        m = MagicMock()
        m._pb.ByteSize.return_value = 0
        setattr(v, absent, m)
    av = MagicMock()
    av._pb.ByteSize.return_value = 0  # set-but-empty
    av.default_value = ""
    av.mime_types = []
    v.asset_variable = av
    # Real proto _pb with HasField surfacing only asset_variable.
    real_pb = MagicMock()
    real_pb.WhichOneof.return_value = None  # not modelled as oneof in this proto
    real_pb.HasField.side_effect = lambda f: f == "asset_variable"
    v._pb = real_pb
    return v


def test_empty_asset_variable_recognised_as_ASSET() -> None:
    from gampan.gam.clients.rest import _var_to_dict

    result = _var_to_dict(_proto_empty_asset_variable("PROFILE_IMAGE"))
    assert result["type"] == "ASSET", f"expected ASSET, got {result['type']}"
    assert result["name"] == "PROFILE_IMAGE"
