---
"gampan": minor
---

Redesign the `release` workflow. The previous flow called `knope release`
from CI to produce the tag + GitHub release commit, then push to `main` —
but the `main` ruleset rejects direct pushes ("Changes must be made
through a pull request / merge queue"), so the workflow always failed at
the push step. knope-bot already handles release creation automatically
when the auto-generated release PR is merged. The CI job now triggers on
`release: published` (and `workflow_dispatch` with an explicit tag input
for manual re-uploads) and only builds + attaches per-arch onefile
binaries — no commit, no push, no fight with the ruleset.
