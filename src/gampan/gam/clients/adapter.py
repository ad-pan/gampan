"""Per-resource routing: pick SOAP or REST client per kind."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from gampan.core.protocols import Client


class _LazyClientMap(Mapping[str, Client]):
    """dict-like that materialises each Client only when the kind is accessed.

    Constructing the SOAP client warms the zeep WSDL cache and (on a cold
    cache) makes an HTTP request — paying that cost for `gampan import
    --resource creative-templates` (REST only) is wasteful and makes cassette
    playback brittle. Same for REST when only SOAP is needed.
    """

    def __init__(self, factories: Mapping[str, Callable[[], Client]]) -> None:
        self._factories = dict(factories)
        self._cache: dict[str, Client] = {}

    def __getitem__(self, key: str) -> Client:
        if key not in self._cache:
            if key not in self._factories:
                raise KeyError(key)
            self._cache[key] = self._factories[key]()
        return self._cache[key]

    def __iter__(self) -> Any:
        return iter(self._factories)

    def __len__(self) -> int:
        return len(self._factories)

    def __contains__(self, key: object) -> bool:
        return key in self._factories


def build_client_map(
    soap_factory: Callable[[], Client],
    rest_factory: Callable[[], Client],
) -> Mapping[str, Client]:
    """Map each resource kind to its current best client.

    Today:
      - NativeStyle → SOAP (no REST coverage)
      - CreativeTemplate → REST

    Construction is lazy: a factory only fires the first time its kind is
    accessed, so REST-only commands skip the SOAP WSDL fetch entirely.

    When Google ships NativeStyle in REST, change ONE line here.
    """
    return _LazyClientMap(
        {
            "NativeStyle": soap_factory,
            "CreativeTemplate": rest_factory,
        }
    )
