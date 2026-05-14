.PHONY: install test validate lint typecheck build clean

install:
	uv sync --extra dev

test:
	uv run pytest

validate:
	uv run pytest tests/integration/ -v

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

typecheck:
	uv run mypy src

build:
	uv run python -m nuitka \
	  --standalone --onefile \
	  --output-dir=dist \
	  --output-filename=gampan \
	  --include-package=googleads \
	  --include-package=google.ads.admanager_v1 \
	  src/gampan/__main__.py

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache .mypy_cache
