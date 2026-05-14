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

## Known limitations (v0.1.0-alpha)

- **Credentials not wired through to API calls.** v0.1.0-alpha resolves credentials for
  diagnostic purposes (`gampan info`, `gampan auth status`) but the underlying SOAP and REST
  client libraries currently use their own auth path (googleads YAML config for SOAP,
  google-auth ADC for REST). The resolved `Credentials` object from `gampan auth login` is
  not yet passed through to those library calls. This gap will be closed in v0.1.1, which
  will thread the resolved credentials into every API request.

## License

Apache 2.0. See [LICENSE](LICENSE).
