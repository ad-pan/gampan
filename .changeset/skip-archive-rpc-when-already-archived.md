---
"gampan": patch
---

`gampan apply` no longer issues an `ArchiveNativeStyles` RPC when the
remote already reports the resource as `ARCHIVED`. GAM's archive
action is idempotent, so the extra call was a no-op, but it added a
network round-trip per orphan row whenever a plan flushed leftover
archived resources from state.json. The executor's DELETE branch now
inspects `change.current.status` first; the state entry is still
removed so the next plan stops re-surfacing the row.
