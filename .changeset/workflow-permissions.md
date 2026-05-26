---
"gampan": patch
---

Add top-level least-privilege `permissions: contents: read` to
`ci.yml`, `release.yml`, and `e2e-nightly.yml`. Resolves four
`actions/missing-workflow-permissions` CodeQL findings (medium).
The `release.yml` knope job retains its own job-level
`permissions: contents: write + pull-requests: write` to push the
release commit, tag, and PR; the override beats the top-level read.
