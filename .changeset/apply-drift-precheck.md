---
"gampan": patch
---

`gampan apply` now refuses to run when the live remote checksum diverges
from the value recorded in `state.json`, surfacing out-of-band changes
(GAM UI edits, parallel applies, direct SDK calls) before they get
silently overwritten by the YAML state.

The check compares the fresh `list()` result against
`state.resources[key].checksum_remote`. Drift on any tracked key prints
the offending keys plus the recovery hint
(`gampan refresh && gampan plan`) and exits with code 1.

Operators who genuinely intend to overwrite the remote — e.g. recovering
from a botched out-of-band change — can pass `--allow-drift`. The flag
turns the abort into a `WARNING:` line and continues with apply. Keys
absent from `state.json`, or rows whose `checksum_remote` was never
populated, are skipped (drift can only be detected against a known prior
state).

GAM SOAP exposes no `lastModifiedDateTime` / `etag` field on
`NativeStyle`, so server-side optimistic locking is out of reach for
v0.1. This client-side TOCTOU check is the strongest safety net the API
allows; the residual window between `list()` and `update*` is on the
order of a few hundred milliseconds.
