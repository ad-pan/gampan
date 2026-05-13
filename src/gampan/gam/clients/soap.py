"""SOAP client (googleads-python-lib) for resources without REST coverage."""

from __future__ import annotations

from typing import Any

from gampan.core.errors import GamApiPermanentError
from gampan.gam.models.native_style import NativeStyle


class NativeStyleSoapClient:
    """Implements core.protocols.Client for the NativeStyle resource."""

    def __init__(self, service: Any) -> None:
        """`service` is `ad_manager_client.GetService('NativeStyleService')`."""
        self._svc = service

    def list(self) -> list[tuple[str, NativeStyle]]:
        result = self._svc.getNativeStylesByStatement({"query": ""})
        out: list[tuple[str, NativeStyle]] = []
        for raw in getattr(result, "results", []) or []:
            d = dict(raw)
            out.append((str(d["id"]), NativeStyle.from_remote(d)))
        return out

    def get(self, gam_id: str) -> NativeStyle:
        result = self._svc.getNativeStylesByStatement({"query": f"WHERE id = {gam_id}"})
        results = list(getattr(result, "results", []) or [])
        if not results:
            raise GamApiPermanentError(f"NativeStyle id={gam_id} not found")
        return NativeStyle.from_remote(dict(results[0]))

    def create(self, resource: NativeStyle) -> str:
        created = self._svc.createNativeStyles([resource.to_remote()])
        return str(created[0]["id"])

    def update(self, gam_id: str, resource: NativeStyle) -> None:
        payload = resource.to_remote()
        payload["id"] = gam_id
        self._svc.updateNativeStyles([payload])

    def delete(self, gam_id: str) -> None:
        # GAM uses status archival rather than DELETE for many resources;
        # mirror that by calling the performNativeStyleAction "ArchiveNativeStyles".
        self._svc.performNativeStyleAction(
            {"xsi_type": "ArchiveNativeStyles"},
            {"query": f"WHERE id = {gam_id}"},
        )
