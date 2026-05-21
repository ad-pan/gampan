---
"gampan": patch
---

`gampan apply` now rebinds CREATE results back into both state.json and
the source YAML so subsequent `plan` runs recognise the new resource by
its real `gam_id` instead of treating it as another fresh CREATE
candidate.

Before this change, `executor` stored the resource under its synthetic
`<Kind>:NEW:<slug>-<hash>` planning key and left the YAML untouched.
The next `gampan plan` therefore:

- read the YAML, regenerated the `NEW:` key (no `_gam_id` present), and
  classified it as CREATE again, while
- observing the freshly-created remote resource as unmanaged → DESTROY.

Workflow was unusable past the first apply without manually editing
each YAML.

The fix threads the YAML source path from `_load_desired` through
`build_plan` / `diff_resources` as a new `Change.yaml_path`. On CREATE,
`execute_plan` now:

- pops the synthetic `NEW:` entry and writes a `<Kind>:<gam_id>` state
  entry instead, and
- stamps `_gam_id: '<id>'` into the YAML immediately after `kind:`
  using ruamel's round-trip writer so existing comments, ordering, and
  `!file` references survive.

The YAML rewrite is opt-in: callers that pass `root=None` (used by the
existing executor unit tests) skip the file write while still
benefitting from the state-key rebind.
