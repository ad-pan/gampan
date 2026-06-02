"""Protocol (ABC) definitions decoupling core from concrete GAM impl."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, Protocol, Self, runtime_checkable


@runtime_checkable
class Resource(Protocol):
    """A GAM resource as a pydantic-like model.

    Implementations live in `gam/models/`.
    """

    kind: ClassVar[str]
    name: str

    @classmethod
    def from_remote(cls, data: dict[str, Any]) -> Self: ...

    def to_remote(self) -> dict[str, Any]: ...

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

    def list(self, *, include_archived: bool = False) -> list[tuple[str, Resource]]:
        """Return ``(gam_id, resource)`` pairs.

        ``include_archived=False`` (default) instructs the implementation to
        skip resources whose lifecycle status is ARCHIVED. Backends that lack
        a meaningful archive distinction may treat the flag as a no-op.
        """
        ...

    def get(self, gam_id: str) -> Resource: ...

    def create(self, resource: Resource) -> str:
        """Create remote; return new gam_id."""
        ...

    def update(
        self,
        gam_id: str,
        resource: Resource,
        *,
        # ``Sequence`` (not ``list``) to dodge a name clash inside this
        # Protocol — ``list`` inside the class body resolves to the ``.list``
        # method above and trips mypy ``[valid-type]``.
        changed_paths: Sequence[str] | None = None,
    ) -> None:
        """Apply *resource* to the remote at *gam_id*.

        ``changed_paths`` carries the dot-paths of fields the diff engine
        flagged as changed (e.g. ``["status"]``, ``["css", "html"]``).
        Clients use it to call only the GAM endpoints whose concern matches
        the change set — e.g. ``NativeStyle`` lifecycle (``status``) lives
        on ``performNativeStyleAction`` while body fields live on
        ``updateNativeStyles``. Calling the body endpoint with no body
        change tickles a zeep response-parsing bug.

        Legacy callers may pass ``None`` to preserve v1 behaviour (call
        every endpoint conservatively).
        """
        ...

    def delete(self, gam_id: str) -> None: ...
