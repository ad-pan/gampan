# gampan

Declarative IaC CLI for Google Ad Manager. Version-control your NativeStyle and CreativeTemplate resources as YAML files; reconcile remote state with `plan` / `apply`.

> Status: **alpha (v0.1)** — feedback welcome.

Part of the [ad-pan](https://github.com/ad-pan) ecosystem.

## Install

```bash
# Homebrew (coming soon)
brew install ad-pan/tap/gampan

# pipx
pipx install gampan

# pip
pip install gampan
```

## Authentication

`gampan` ships with its own OAuth client baked in — just like `gcloud`, `gh`, and
`firebase`. You do not need to register a Google Cloud project or configure credentials
before running `gampan auth login`.

> **Enterprise / fork users**: if you want your own OAuth client for audit reasons, set
> `GAMPAN_OAUTH_CLIENT_ID` and `GAMPAN_OAUTH_CLIENT_SECRET` environment variables and
> they will take precedence over the built-in defaults.

> **Maintainers / first-time setup**: the baked-in defaults are currently placeholders
> (`TODO_REGISTER_OAUTH_CLIENT...`). Follow
> [docs/oauth-client-setup.md](docs/oauth-client-setup.md) to register the client and
> replace the constants (one-time commit). Until then, `gampan auth login` exits with a
> clear error pointing to that doc.

## Quickstart

```bash
# 1. Authenticate (browser-based, no gcloud SDK required)
gampan auth login

# 2. Scaffold a new repo
gampan init --network-code <YOUR_GAM_NETWORK_CODE>

# 3. Pull existing GAM resources into version control
gampan import

# 4. Edit YAML files. Then preview changes:
gampan plan

# 5. Apply
gampan apply
```

## Architecture

See [design spec](docs/specs/2026-04-28-gampan-design.md).

## Testing

| Command | What it runs |
|---|---|
| `mise run test` | Unit tests (no network required) |
| `make validate` | Cassette-driven integration tests (offline; skipped when cassettes absent) |
| `uv run pytest tests/integration -v -m e2e` | Integration tests against a real GAM test network (requires secrets) |

### First-time validation against a real GAM test network

Follow the step-by-step **[v0.1 validation runbook](docs/runbook-v0.1-validation.md)** to:

1. Authenticate with a Google account that has Ad Manager API access.
2. Bootstrap a free GAM test network (`gampan bootstrap-test-network`).
3. Run the full `plan` → `apply` → `refresh` cycle.
4. Record VCR cassettes so the integration tests can run offline.

### Nightly e2e in CI

The `.github/workflows/e2e-nightly.yml` workflow runs daily at 18:00 UTC and executes the same integration tests against a real GAM test network. It is **skipped automatically** when the required secrets (`GAMPAN_OAUTH_CLIENT_ID`, `GAMPAN_OAUTH_CLIENT_SECRET`, `GAMPAN_E2E_SA_JSON`, `GAMPAN_E2E_NETWORK_CODE`) are not configured — so forks and PRs from external contributors are unaffected.

## Known limitations (v0.1.0-alpha)

- **Integration test cassettes not yet committed.** The integration test harness is fully
  scaffolded and cassette-driven tests skip gracefully when cassette files are absent, so CI
  passes today. Cassettes are recorded by following the
  [runbook](docs/runbook-v0.1-validation.md) above. The nightly e2e workflow exercises the
  real-API path once secrets are configured in the repository settings.

## License

Apache 2.0. See [LICENSE](LICENSE).
