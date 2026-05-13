"""REST client (google-ads-admanager) for resources with REST coverage."""

from __future__ import annotations

from typing import Any

from gampan.gam.clients._retry import retry_transient
from gampan.gam.models.creative_template import CreativeTemplate


class CreativeTemplateRestClient:
    """Implements core.protocols.Client for the CreativeTemplate resource."""

    def __init__(self, service: Any, network_path: str) -> None:
        """`service` is `AdManagerServiceClient(...)`; `network_path` is 'networks/{code}'."""
        self._svc = service
        self._parent = network_path

    @retry_transient
    def list(self) -> list[tuple[str, CreativeTemplate]]:
        out: list[tuple[str, CreativeTemplate]] = []
        page_token = ""
        while True:
            resp = self._svc.list_creative_templates(parent=self._parent, page_token=page_token)
            for raw in resp.creative_templates:
                d = dict(raw)
                gam_id = str(d["name"]).rsplit("/", 1)[-1]
                out.append((gam_id, CreativeTemplate.from_remote(d)))
            page_token = getattr(resp, "next_page_token", "")
            if not page_token:
                break
        return out

    @retry_transient
    def get(self, gam_id: str) -> CreativeTemplate:
        resp = self._svc.get_creative_template(name=f"{self._parent}/creativeTemplates/{gam_id}")
        return CreativeTemplate.from_remote(dict(resp))

    @retry_transient
    def create(self, resource: CreativeTemplate) -> str:
        resp = self._svc.create_creative_template(
            parent=self._parent, creative_template=resource.to_remote()
        )
        return str(resp.name).rsplit("/", 1)[-1]

    @retry_transient
    def update(self, gam_id: str, resource: CreativeTemplate) -> None:
        body = resource.to_remote()
        body["name"] = f"{self._parent}/creativeTemplates/{gam_id}"
        self._svc.update_creative_template(creative_template=body)

    @retry_transient
    def delete(self, gam_id: str) -> None:
        # REST exposes archive; treat as delete from the user's POV.
        self._svc.archive_creative_template(name=f"{self._parent}/creativeTemplates/{gam_id}")
