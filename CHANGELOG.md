## 0.1.1 (2026-05-26)

### Features

- refuse CreativeTemplate write intents at plan time
- clean up orphan YAML after remote rename
- drift pre-check + refresh-ack flag
- include_archived toggle for plan/apply/import
- capture NUMBER variables and ASSET mime_types on import
- capture LIST variable choices on import
- validate loaded YAML against @ad-pan/schema as a drift tripwire
- drop the GAM-supplied HTML snippet on import
- route native formats to native-formats/, add kind-suffix to filenames
- surface native_eligible + 3 sibling flags
- slugify preserves CJK and other non-Latin scripts
- rich-rendered plan/apply output with field-level diffs
- emit structured FieldDiff records in Change.diffs
- print diff_summary lines under each UPDATE row
- fall back to getAllNetworks when account already linked
- file-based credential storage by default (gcloud/gh pattern)
- register gampan OAuth client (ad-pan GCP project)
- gampan bootstrap-test-network
- wire resolved credentials through SOAP/REST factories
- exponential-backoff retry for transient 5xx (tenacity)
- gampan refresh
- gampan apply (confirm prompt + --auto-approve)
- gampan plan (text + --json, --detailed-exitcode)
- factories for SOAP and REST
- gampan import (NativeStyle + CreativeTemplate)
- gampan info (--offline / --json)
- gampan auth login/logout/status
- gampan init
- typer app + logging + command stubs
- adapter routing per kind
- CreativeTemplateRestClient
- NativeStyleSoapClient (list/get/create/update/delete)

#### Drop prebuilt `gampan-darwin-x86_64` artifact from the release workflow.

Cross-compiling x86_64 from a `macos-14` (arm64) runner needs a
universal2 Python that neither `mise` nor `actions/setup-python`
provides, and `macos-13` is deprecated. Intel Mac users should install
via `pipx install gampan` or `pip install gampan` from PyPI.

The `ad-pan/homebrew-tap` formula needs a matching update to drop its
Intel branch after the next release.

#### Initial alpha release: `init`, `auth login/logout/status`, `info`,

`import`, `plan`, `apply`, `refresh`, `version`. Supports NativeStyle
(SOAP) and CreativeTemplate (REST). Built-in OAuth via
`google-auth-oauthlib`. Single-binary distribution via Nuitka.

#### Redesign the `release` workflow. The previous flow called `knope release`

from CI to produce the tag + GitHub release commit, then push to `main` —
but the `main` ruleset rejects direct pushes ("Changes must be made
through a pull request / merge queue"), so the workflow always failed at
the push step. knope-bot already handles release creation automatically
when the auto-generated release PR is merged. The CI job now triggers on
`release: published` (and `workflow_dispatch` with an explicit tag input
for manual re-uploads) and only builds + attaches per-arch onefile
binaries — no commit, no push, no fight with the ruleset.

### Fixes

- split compound git add+commit step into two Commands
- skip archive RPC when remote is already ARCHIVED
- preserve SOAP Targeting opaquely + refuse legacy shape
- rebind CREATE results into state key and YAML
- place isFluid at root, omit empty targeting
- sort ASSET mime_types for deterministic round-trip
- recognize set-but-empty oneof variants via HasField
- dedup by _gam_id when present (names legitimately collide)
- only query managed kinds; lazy SOAP/REST client construction
- key by gam_id, fall back to gam_id for non-Latin / empty slugs
- NativeStyle.from_remote tolerates None for empty fields
- use zeep.helpers.serialize_object instead of dict() coercion
- scrub access_token/refresh_token/client_secret from cassettes
- use absolute cassette paths so chdir doesn't break recording
- map proto display_name to model.name (was using resource path)
- preserve consecutive whitespace through YAML round-trip
- emit real !file YAML tag (not quoted string)
- align CreativeTemplate enums to REST API reality
- map REST oneof CreativeTemplateVariable to flat model
- pager pattern + proto-plus dict conversion; document write gap
- use __getitem__ on SOAP response (zeep has no .get)
- KeychainStrategy uses baked-in OAuth client (refresh works)
- request email scopes; tolerate 401 on userinfo fetch
- use new admanager scope (Google renamed dfp → admanager)
- use InstalledAppFlow for run_local_server
- GcloudAdcStrategy refreshes access token on each get_token call
- load OAuth client config from env vars; remove REPLACE_AT_RELEASE

#### Adopt [knope](https://knope.tech) as the release-automation CLI in

place of the ``@changesets/cli`` + ``package.json`` anchor pattern.
``knope.toml`` declares ``pyproject.toml`` as the canonical
versioned file and reuses the existing ``.changeset/*.md`` entries
verbatim (knope's on-disk format is compatible with the NodeJS
Changesets one). Mise pulls knope via the cargo binstall backend so
the same binary is available locally and in CI without a Rust
toolchain. Follow-up PRs swap the release / CI workflows over to
knope's ``release`` and ``prepare-release`` commands and drop the
``package.json`` / ``@changesets/cli`` plumbing.

#### `gampan apply` now refuses to run when the live remote checksum diverges

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

#### `gampan apply` now rebinds CREATE results back into both state.json and

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

#### `gampan plan` and `gampan apply` now refuse CreativeTemplate write

intents at plan time instead of letting them fall through to the
executor and crash with `NotImplementedError`.

GAM's REST Beta exposes `list` / `get` for CreativeTemplate but not
the write verbs, so v0.1 has always been read-only for that kind. The
old behaviour rendered the plan, prompted for confirmation, then
raised `NotImplementedError` inside `executor.execute_plan` — late
enough that an operator who chained other resources in the same plan
might already have applied them by the time the CT row blew up.

A new `validate_v0_1_constraints(plan.changes)` helper scans the diff
for any non-`NO_CHANGE` action on a `CreativeTemplate:*` key and
raises `CreativeTemplateReadOnlyError` with the offending list and a
recovery hint (edit through the GAM UI + `gampan import`, or revert
the YAML). `plan` still renders the diff so the operator can see what
would have been touched before the abort. Both CLIs exit 1 on the
error.

#### Fix `e2e-nightly.yml` parse error. `secrets` is not a valid context in

job-level `if:` and `runner` is not valid in job-level `env:`; both
caused the workflow to fail validation at load time. Gate forks via
`github.repository`, and write the SA file inside a step where
`$RUNNER_TEMP` is available, exporting the path via `$GITHUB_ENV`.

#### `gampan import` now deletes the stale on-disk YAML when a remote

resource is renamed (same `_gam_id`, new slug). Previously the new
file landed under the new slug while the old-slug `<stem>.<kind>.yaml`
plus its `.html` / `.css` side files lingered as orphans, tripping
`validate_no_duplicates` on the next `plan` until the operator
deleted them manually.

The new logic scans `native-styles/`, `creative-templates/`, and
`native-formats/` before writing, builds a `_gam_id → existing yaml`
map, and removes the old path (plus `.html` / `.css` siblings) when
`write_resource` lands the file at a new path. YAMLs without
`_gam_id` (user-authored drafts that have not been imported yet) are
intentionally never touched — only previously-imported files
participate in rename cleanup. A trailing audit line surfaces the
removed orphans.

#### Fix the `release` workflow in `knope.toml`. `Command` steps are split via

shell-words (no real shell), so `&&` doesn't chain — every token after
the first `git add` was being treated as an argument to `git add`,
which then crashed with "error: unknown switch -m". Split the staging
and commit into two separate `Command` steps.

#### Document known limitation: resolved credentials are not yet wired through to

SOAP/REST client library calls in v0.1.0-alpha. The `gampan auth login` flow
works end-to-end for keychain storage and `gampan auth status` reporting, but
the googleads YAML path (SOAP) and google-auth ADC path (REST) remain
independent. v0.1.1 will wire the resolved `Credentials` object into every API
request.

#### Fix `gampan apply` for NativeStyle and stop archived resources from

re-appearing in every `plan` cycle. Three independent fixes uncovered while
running the documented `init → import → plan → apply` smoke test against a
sandbox network:

- **`fix(rest)`: deterministic `mime_types` order.** GAM's REST endpoint
  returns ASSET-variable `mime_types` in a non-deterministic order — the same
  template can yield `['PNG','GIF','JPG']` then `['JPG','PNG','GIF']` on
  consecutive `list()` calls. Without normalisation every `gampan plan`
  immediately after `gampan import` flagged ~25 spurious CreativeTemplate
  UPDATEs. The import path now sorts the enum names alphabetically so YAML
  and remote views stay aligned.
- **`fix(native-style-soap)`: SOAP create/update roundtrip.** `to_remote()`
  was nesting `isFluid` inside `Size` (the SOAP WSDL puts it at the
  `NativeStyle` root) and emitting a flat `targeting.{adUnits,
  customTargeting}` shape that does not match the deeply nested SOAP
  `Targeting` complex type. Both caused `createNativeStyles` /
  `updateNativeStyles` to raise `KeyError` inside `googleads`. `isFluid` now
  lives at the payload root, `targeting` is omitted entirely while it is
  empty (a v0.2 mapping will fill it in), and `from_remote()` keeps a
  backwards-compat read for the old nested shape.
- **`feat(config)`: `include_archived` toggle.** ARCHIVED NativeStyles were
  re-surfacing as DESTROY candidates on every `plan` because
  `getNativeStylesByStatement` returns them regardless of `executor.delete`'s
  prior archive call. A new `include_archived` config field (`false` by
  default) and matching `--include-archived` / `--no-include-archived` CLI
  flags on `plan`, `apply`, and `import` add a PQL status filter. A
  `MissingRemoteError` planner guard prevents the foot-gun where a tracked
  YAML whose remote got filtered out would otherwise be reinterpreted as a
  brand-new CREATE.

#### `NativeStyle.targeting` is now preserved verbatim as the SOAP `Targeting`

complex type. The previous v0.1 model decoded the payload into a flat
`{ad_units, custom}` shape whose keys did not match the WSDL
(`inventoryTargeting`, `customTargeting`, `geoTargeting`, ...). The
mismatch had two consequences:

- **Import was lossy.** Every imported NativeStyle landed in YAML with
  `ad_units: []` / `custom: {}` regardless of what the remote actually
  carried; a production network's NativeStyles all hid real
  `inventoryTargeting.targetedAdUnits` payloads behind that placeholder.
- **Apply was silently destructive.** `to_remote()` re-emitted the same
  flat shape, which `googleads`' SOAP packer dropped during
  `updateNativeStyles` (the WSDL has no `adUnits` field). The remote
  `Targeting` would have been overwritten with an empty payload on the
  first apply that touched an imported NativeStyle. Drift detection did
  not surface the problem because both sides agreed on "empty
  targeting".

This release stores the SOAP shape opaquely so `import → plan → apply`
round-trips byte-for-byte:

- `Targeting` model is removed. `NativeStyle.targeting: dict[str, Any]
  | None` carries the raw SOAP payload (or `None` when GAM returns no
  wrapper at all).
- `from_remote` keeps the dict as-is. `to_remote` re-emits it as-is.
  The `writer._to_user_yaml` mirrors the dict into the YAML, so the
  user can read the full nested structure (and edit it once a v0.2
  schema lands).
- A `@model_validator` migrates the legacy `{ad_units, custom}` shape:
  empty payloads (the only thing v0.1 could produce) become `None`
  silently; populated legacy payloads — which were always a lie —
  raise `LegacyTargetingError` asking the caller to re-run `gampan
  import` instead of applying a destructive empty targeting to the
  remote.

**Migration:** existing YAMLs imported by gampan <= 0.1.x must be
re-imported before the next `apply`. The model accepts the legacy
shape only when empty, so a stale `targeting: {ad_units: [], custom:
{}}` block keeps working until you re-import. Anything else now
raises at parse time.

#### Post-review polish across the apply/plan/import/refresh path. Behaviour-

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

#### Close the `gampan refresh` ⇒ `gampan apply` race that let an out-of-band

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

#### Add `SECURITY.md` (supported versions, GitHub private vulnerability

reporting channel, response SLA) and `.github/dependabot.yml`
(weekly grouped sweeps for the `pip` and `github-actions`
ecosystems). CodeQL keeps running via GitHub's default Code
Scanning setup; no manual workflow needed.

#### `gampan apply` no longer issues an `ArchiveNativeStyles` RPC when the

remote already reports the resource as `ARCHIVED`. GAM's archive
action is idempotent, so the extra call was a no-op, but it added a
network round-trip per orphan row whenever a plan flushed leftover
archived resources from state.json. The executor's DELETE branch now
inspects `change.current.status` first; the state entry is still
removed so the next plan stops re-surfacing the row.

#### Add top-level least-privilege `permissions: contents: read` to

`ci.yml`, `release.yml`, and `e2e-nightly.yml`. Resolves four
`actions/missing-workflow-permissions` CodeQL findings (medium).
The `release.yml` knope job retains its own job-level
`permissions: contents: write + pull-requests: write` to push the
release commit, tag, and PR; the override beats the top-level read.
