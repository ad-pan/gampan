---
"gampan": patch
---

Close the `gampan refresh` ⇒ `gampan apply` race that let an out-of-band
remote change slip past the drift pre-check.

Before this fix, `refresh` overwrote `state.checksum_remote` with the
freshly-fetched value, so the very next `apply` saw "no drift"
(state.checksum_remote already matched the remote) and silently
overwrote the change the operator had only just been warned about.

`ResourceEntry` now carries an extra `drift_acknowledged: bool = True`
flag and the apply pre-check counts a key as drifted when either:

* the live checksum no longer matches `state.checksum_remote`, **or**
* the checksums match but `drift_acknowledged == False`.

`refresh` flips the flag to `False` for any key whose remote moved.
`apply` flips it back to `True` once the operator has either applied
the YAML (executor's per-action `_entry()` rewrite covers CRUD'd keys;
the apply runner now also resets keys that were drifted but not part
of the plan, e.g. drift on resource A while the plan only changed
resource B). Existing state.json files without the field load as
`True` so prior installs behave unchanged.

`refresh` also gained a one-line "next step" hint pointing at the
three recovery paths (`gampan plan`, `gampan import`, `gampan apply
--allow-drift`).
