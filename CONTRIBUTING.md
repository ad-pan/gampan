# Contributing to gampan

Thanks for your interest!

## Developer setup

```bash
mise install
uv sync --extra dev
uv run pytest
```

## DCO sign-off

All commits must be signed off (`git commit -s`) attesting to the [Developer Certificate of Origin](https://developercertificate.org/).

## Changesets

We use [changesets](https://github.com/changesets/changesets). Every user-facing change requires a changeset:

```bash
pnpm dlx @changesets/cli add
```

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). We follow the [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
