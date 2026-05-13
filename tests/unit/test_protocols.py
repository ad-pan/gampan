from typing import ClassVar

from gampan.core.protocols import Client, Credentials, Resource


class FakeResource:
    kind: ClassVar[str] = "Fake"
    name: str = "x"

    @classmethod
    def from_remote(cls, data: dict) -> "FakeResource":
        r = cls()
        r.name = data["name"]
        return r

    def to_remote(self) -> dict:
        return {"name": self.name}

    def checksum(self) -> str:
        return "abc"


def test_fake_resource_satisfies_protocol() -> None:
    r: Resource = FakeResource()  # static-typer satisfaction; runtime no-op
    assert r.kind == "Fake"
    assert r.to_remote() == {"name": "x"}
    assert r.checksum() == "abc"


class FakeCreds:
    @property
    def principal(self) -> str:
        return "test@example.com"

    def get_token(self) -> str:
        return "token-abc"


def test_credentials_protocol() -> None:
    c: Credentials = FakeCreds()
    assert c.principal == "test@example.com"
    assert c.get_token() == "token-abc"


class FakeClient:
    def list(self) -> list[tuple[str, Resource]]:
        return []

    def get(self, gam_id: str) -> Resource:
        return FakeResource()

    def create(self, resource: Resource) -> str:
        return "new-id"

    def update(self, gam_id: str, resource: Resource) -> None:
        return None

    def delete(self, gam_id: str) -> None:
        return None


def test_client_protocol() -> None:
    c: Client = FakeClient()
    assert c.list() == []
    assert c.create(FakeResource()) == "new-id"
