---
"gampan": patch
---

Fix `e2e-nightly.yml` parse error. `secrets` is not a valid context in
job-level `if:` and `runner` is not valid in job-level `env:`; both
caused the workflow to fail validation at load time. Gate forks via
`github.repository`, and write the SA file inside a step where
`$RUNNER_TEMP` is available, exporting the path via `$GITHUB_ENV`.
