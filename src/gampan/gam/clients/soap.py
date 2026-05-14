"""SOAP client (googleads-python-lib) for resources without REST coverage."""

from __future__ import annotations

from typing import Any, cast

from gampan.core.errors import GamApiPermanentError
from gampan.core.protocols import Resource
from gampan.gam.clients._retry import retry_transient
from gampan.gam.models.native_style import NativeStyle


class NativeStyleSoapClient:
    """Implements core.protocols.Client for the NativeStyle resource."""

    def __init__(self, service: Any) -> None:
        """`service` is `ad_manager_client.GetService('NativeStyleService')`."""
        self._svc = service

    @retry_transient
    def list(self) -> list[tuple[str, Resource]]:
        result = self._svc.getNativeStylesByStatement({"query": ""})
        out: list[tuple[str, Resource]] = []
        for raw in getattr(result, "results", []) or []:
            d = dict(raw)
            out.append((str(d["id"]), NativeStyle.from_remote(d)))
        return out

    @retry_transient
    def get(self, gam_id: str) -> Resource:
        result = self._svc.getNativeStylesByStatement({"query": f"WHERE id = {gam_id}"})
        results = list(getattr(result, "results", []) or [])
        if not results:
            raise GamApiPermanentError(f"NativeStyle id={gam_id} not found")
        return NativeStyle.from_remote(dict(results[0]))

    @retry_transient
    def create(self, resource: Resource) -> str:
        ns = cast(NativeStyle, resource)
        created = self._svc.createNativeStyles([ns.to_remote()])
        return str(created[0]["id"])

    @retry_transient
    def update(self, gam_id: str, resource: Resource) -> None:
        ns = cast(NativeStyle, resource)
        payload = ns.to_remote()
        payload["id"] = gam_id
        self._svc.updateNativeStyles([payload])

    @retry_transient
    def delete(self, gam_id: str) -> None:
        # GAM uses status archival rather than DELETE for many resources;
        # mirror that by calling the performNativeStyleAction "ArchiveNativeStyles".
        self._svc.performNativeStyleAction(
            {"xsi_type": "ArchiveNativeStyles"},
            {"query": f"WHERE id = {gam_id}"},
        )
