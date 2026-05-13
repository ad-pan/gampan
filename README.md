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

## License

Apache 2.0. See [LICENSE](LICENSE).
