"""SOAP client (googleads-python-lib) for resources without REST coverage."""

from __future__ import annotations

from typing import Any, cast

from gampan.core.errors import GamApiPermanentError
from gampan.core.protocols import Resource
from gampan.gam.clients._retry import retry_transient
from gampan.gam.models.native_style import NativeStyle


def _to_dict(raw: Any) -> dict[str, Any]:
    """Convert a zeep CompoundValue (or already-a-dict) into a plain dict.

    ``dict(zeep_obj)`` is unreliable: depending on the zeep type and version
    its ``__iter__`` may yield 4-tuples or values-only, breaking the
    ``dict(iterable)`` constructor's expected ``(key, value)`` pairs. The
    canonical fix is ``zeep.helpers.serialize_object`` which recursively
    converts CompoundValue → dict and SOAP arrays → list.

    On a plain dict input (e.g. MagicMock-returned data in unit tests) it
    is effectively a deep copy and the result is also dict-shaped.
    """
    # Local import keeps `zeep` an implementation detail and avoids paying
    # the import cost at gampan startup when SOAP isn't used.
    from zeep.helpers import serialize_object

    return dict(serialize_object(raw, target_cls=dict))  # type: ignore[no-untyped-call]


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
            d = _to_dict(raw)
            out.append((str(d["id"]), NativeStyle.from_remote(d)))
        return out

    @retry_transient
    def get(self, gam_id: str) -> Resource:
        result = self._svc.getNativeStylesByStatement({"query": f"WHERE id = {gam_id}"})
        results = list(getattr(result, "results", []) or [])
        if not results:
            raise GamApiPermanentError(f"NativeStyle id={gam_id} not found")
        return NativeStyle.from_remote(_to_dict(results[0]))

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
