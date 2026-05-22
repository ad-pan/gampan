---
"gampan": patch
---

Adopt [knope](https://knope.tech) as the release-automation CLI in
place of the ``@changesets/cli`` + ``package.json`` anchor pattern.
``knope.toml`` declares ``pyproject.toml`` as the canonical
versioned file and reuses the existing ``.changeset/*.md`` entries
verbatim (knope's on-disk format is compatible with the NodeJS
Changesets one). Mise pulls knope via the cargo binstall backend so
the same binary is available locally and in CI without a Rust
toolchain. Follow-up PRs swap the release / CI workflows over to
knope's ``release`` and ``prepare-release`` commands and drop the
``package.json`` / ``@changesets/cli`` plumbing.
