"""Protocol (ABC) definitions decoupling core from concrete GAM impl."""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable


@runtime_checkable
class Resource(Protocol):
    """A GAM resource as a pydantic-like model.

    Implementations live in `gam/models/`.
    """

    kind: ClassVar[str]
    name: str

    @classmethod
    def from_remote(cls, data: dict[str, object]) -> Resource: ...

    def to_remote(self) -> dict[str, object]: ...

    def checksum(self) -> str:
        """Return ``sha256:<hex>`` over the canonical JSON (sort_keys=True, ensure_ascii=False)."""
        ...


@runtime_checkable
class Credentials(Protocol):
    """An authenticated principal for GAM API calls."""

    @property
    def principal(self) -> str: ...

    def get_token(self) -> str: ...


@runtime_checkable
class Client(Protocol):
    """CRUD facade over one GAM resource type, hiding SOAP/REST choice.

    `list` returns (gam_id, resource) tuples because identity lives in GAM,
    not in the model.
    """

    def list(self) -> list[tuple[str, Resource]]: ...

    def get(self, gam_id: str) -> Resource: ...

    def create(self, resource: Resource) -> str:
        """Create remote; return new gam_id."""
        ...

    def update(self, gam_id: str, resource: Resource) -> None: ...

    def delete(self, gam_id: str) -> None: ...
