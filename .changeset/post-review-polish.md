---
"gampan": patch
---

Post-review polish across the apply/plan/import/refresh path. Behaviour-
preserving cleanup that picks up several findings from a three-agent
reuse/quality/efficiency review:

- **Error hierarchy**: `MissingRemoteError` and `CreativeTemplateReadOnlyError`
  now inherit from `GampanError` for parity with the rest of `core/errors.py`.
- **`NEW_KEY_MARKER` constant**: the `":NEW:"` synthetic-key sentinel is
  declared once in `diff.py` and reused by `plan._load_desired`'s key
  construction and `diff_resources`'s strict-missing-remote guard.
- **`detect_remote_drift` complexity**: loop now iterates the (small)
  `state_entries` map and probes `current`, instead of walking every
  remote resource (often hundreds) and discarding non-tracked rows.
- **`validate_v0_1_constraints` kind comparison**: compare `key.partition(":")[0]`
  against `CreativeTemplate.kind` instead of a hard-coded
  `"CreativeTemplate:"` prefix.
- **`execute_plan` state plumbing**: accepts an `initial_state` and
  returns the mutated `State`, so apply does not have to re-`load()`
  state.json after the executor saved it. The `finally` block only
  flushes when the loop raised mid-run, eliminating one duplicate
  atomic write per clean apply.
- **`_entry()` is explicit about `drift_acknowledged=True`** so a future
  schema default tightening cannot silently regress drift tracking.
- **Module-level ruamel loader**: `_write_gam_id_back` shares a single
  round-trip `YAML()` instead of constructing one per CREATE.
- **Apply scope matches plan**: `apply` now passes `_managed_kinds(...)`
  into `_load_current`, so it queries the same kinds plan does (the old
  call fell back to every client kind, widening the drift pre-check
  window and doing extra API I/O).
- **`_ack_drifted` single save**: drift-ack now mutates the in-memory
  state and the caller saves once at the end of apply, removing the
  load → patch → save → reload-after-executor → save cycle that
  collapsed two atomic writes into four.
- **`import` reuses the `Config` parser** via `plan._load_config`
  instead of re-implementing the YAML→dict path; gets `extra="forbid"`
  validation and `include_archived` defaulting for free.
- **`CONVENTION_DIRS` exported** from `core.fs.loader` and consumed by
  `import` so the canonical layout list lives in one place. Import
  also restricts its rename-orphan pre-scan to the directories that
  the active `--resource` filter actually cares about — a NativeStyle
  import no longer parses every CreativeTemplate YAML.
- **`refresh` honours `include_archived`** (config + new
  `--include-archived/--no-include-archived` flag) and skips the
  `store.save()` when nothing actually changed.
- **`import_cmd` top-level `slugify` import** rather than the
  per-iteration in-loop binding.

All 182 unit tests still pass; sandbox `init → import → plan →
refresh` smoke test on network `23353362843` is unchanged.
