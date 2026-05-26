---
"gampan": patch
---

Fix the `release` workflow in `knope.toml`. `Command` steps are split via
shell-words (no real shell), so `&&` doesn't chain — every token after
the first `git add` was being treated as an argument to `git add`,
which then crashed with "error: unknown switch -m". Split the staging
and commit into two separate `Command` steps.
