import pytest
import vcr

vcr_default = vcr.VCR(
    cassette_library_dir="tests/integration/cassettes",
    record_mode="once",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["authorization", "x-goog-api-key"],
)


@pytest.fixture
def cassette(request):
    name = request.node.name
    with vcr_default.use_cassette(f"{name}.yaml"):
        yield
