---
"gampan": patch
---

CI now blocks pull requests that don't add a ``.changeset/*.md``
entry, so the next auto-generated Release PR always has something
to roll up. Test-only / chore-only PRs can register an empty
changeset (``pnpm dlx @changesets/cli --empty``) to opt out of the
changelog while still passing the check.
