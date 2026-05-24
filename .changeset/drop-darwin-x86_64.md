---
"gampan": minor
---

Drop prebuilt `gampan-darwin-x86_64` artifact from the release workflow.
Cross-compiling x86_64 from a `macos-14` (arm64) runner needs a
universal2 Python that neither `mise` nor `actions/setup-python`
provides, and `macos-13` is deprecated. Intel Mac users should install
via `pipx install gampan` or `pip install gampan` from PyPI.

The `ad-pan/homebrew-tap` formula needs a matching update to drop its
Intel branch after the next release.
