.PHONY: deps test validate lint typecheck build release-build install clean

PREFIX ?= $(HOME)/.local

# Project setup
deps:
	uv sync --extra dev

# Quality
test:
	uv run pytest

validate:
	uv run pytest tests/integration/ -v

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

typecheck:
	uv run mypy src

# Shared nuitka args
NUITKA_BASE = uv run python -m nuitka \
	  --standalone --onefile \
	  --output-dir=dist \
	  --output-filename=gampan \
	  --include-package=googleads \
	  --include-package=google.ads.admanager_v1 \
	  --nofollow-import-to=mypy \
	  --nofollow-import-to=pytest \
	  --nofollow-import-to=_pytest \
	  --nofollow-import-to=coverage \
	  --nofollow-import-to=nuitka \
	  --nofollow-import-to=vcr \
	  --nofollow-import-to=respx \
	  src/gampan/__main__.py

# Dev build — fast iteration (~3 min)
build:
	$(NUITKA_BASE)

# Release build — slower (~15 min) but smaller binary via link-time optimization
release-build:
	$(NUITKA_BASE) --lto=yes

# Install built binary onto PATH (PREFIX defaults to ~/.local)
install: dist/gampan
	mkdir -p $(PREFIX)/bin
	cp dist/gampan $(PREFIX)/bin/gampan
	@echo "installed $(PREFIX)/bin/gampan"
	@echo "verify with: gampan version"

dist/gampan:
	$(MAKE) build

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache .mypy_cache
