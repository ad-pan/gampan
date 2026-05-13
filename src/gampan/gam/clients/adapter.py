"""Per-resource routing: pick SOAP or REST client per kind."""

from __future__ import annotations

from collections.abc import Callable

from gampan.core.protocols import Client


def build_client_map(
    soap_factory: Callable[[], Client],
    rest_factory: Callable[[], Client],
) -> dict[str, Client]:
    """Map each resource kind to its current best client.

    Today:
      - NativeStyle → SOAP (no REST coverage)
      - CreativeTemplate → REST

    When Google ships NativeStyle in REST, change ONE line here.
    """
    return {
        "NativeStyle": soap_factory(),
        "CreativeTemplate": rest_factory(),
    }
