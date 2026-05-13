"""Tests for CreativeTemplateRestClient."""

from unittest.mock import MagicMock

from gampan.gam.clients.rest import CreativeTemplateRestClient
from gampan.gam.models.creative_template import CreativeTemplate, TemplateVariable


def _t() -> CreativeTemplate:
    return CreativeTemplate(
        name="t",
        type="USER_DEFINED",
        snippet="<div/>",
        variables=[TemplateVariable(name="h", type="STRING")],
    )


def test_list_paginates_and_maps() -> None:
    svc = MagicMock()
    svc.list_creative_templates.return_value = MagicMock(
        creative_templates=[
            {
                "name": "networks/123/creativeTemplates/ct-1",
                "snippet": "<div/>",
                "variables": [],
                "status": "ACTIVE",
                "type": "USER_DEFINED",
            }
        ],
        next_page_token="",
    )
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    items = c.list()
    assert len(items) == 1
    gam_id, model = items[0]
    assert gam_id == "ct-1"
    assert model.name == "networks/123/creativeTemplates/ct-1"


def test_create_returns_id_from_response() -> None:
    svc = MagicMock()
    resp = MagicMock()
    resp.name = "networks/123/creativeTemplates/ct-123"
    svc.create_creative_template.return_value = resp
    c = CreativeTemplateRestClient(svc, network_path="networks/123")
    new_id = c.create(_t())
    assert new_id == "ct-123"
