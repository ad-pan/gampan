# gampan multi-environment management — Design Spec

- **Status**: Draft (brainstorming output, pre-implementation)
- **Author**: Sejun Jeong (@zb-sj)
- **Date**: 2026-05-26
- **Scope**: gampan v1.x — multi-environment (dev/prod/...) support via hooks
- **Resolves**: v1 design spec §11.1 (deferred multi-env strategy)

## 1. Purpose

The v1 spec deferred multi-environment strategy until real users surfaced needs. A concrete reference case has now emerged. Its conventions (observed in a real production repo):

- **Single GAM network**. dev and prod resources coexist in one network.
- **Asymmetric naming**. Prod resources carry the canonical name unchanged (e.g. `article-card`); dev resources are decorated with a `[dev] ` prefix on GAM's `name` field (e.g. `[dev] article-card`). Filenames mirror this with a `dev-` slug prefix.
- **Kind-asymmetric env-awareness**. `NativeStyle` is mostly env-split, `NativeFormat` partially, `CreativeTemplate` not at all (one shared definition serves both environments).
- **Resource-level env-awareness**. Within an env-aware kind, not every resource is split — some live in prod only, some in both.
- **Branch-driven deploys**. `deploy/dev` and `deploy/prod` git branches gate CI applies per environment.

A naive solution would bake this specific convention into gampan (e.g. a built-in `name_prefix` field or a `[dev]` literal). This spec rejects that path: other organizations will encode environment distinction differently — separate networks, GAM tags, targeting rules, custom prefixes/suffixes, only-some-kinds-env-aware, or per-resource opt-in. Even within the reference case, the convention is non-uniform across kinds. gampan therefore exposes **environments** as a first-class concept and delegates the transformation logic — *what makes a resource "dev" vs "prod"* — to a user-defined **hook**. The hook is free to be kind-aware, resource-aware, or both.

## 2. Goals and non-goals

### Goals

1. **First-class environment concept** in the CLI and state, so that prod and dev artifacts are isolated and never silently confused.
2. **Single source of truth** for the common case: one YAML file describes a resource; per-environment differences are derived, not duplicated.
3. **Environment-only resources** expressible without ceremony: long-running dev-only experiments must remain a 1-line annotation, with promotion = removing that annotation.
4. **Customization without forking**: each organization expresses its own environment convention without changing gampan internals.
5. **Backward compatibility**: existing single-environment users (no `environments:` declared, no hook file) see no behavior change.

### Non-goals

- **Cross-network environments**: gampan v1.x scopes one `network_code` per config. Operating dev on network A and prod on network B is reachable but not a v1.x design target — users can run two repos for now.
- **Promotion policy in core**: gampan does not encode "prod must come from dev" or similar rules in its own logic. The `before-apply` hook (§5.3) is the vehicle for orgs that want to express these rules; gampan ships the mechanism, not the policy.
- **Inline-Python hooks**: the Nuitka build does not expose its embedded interpreter to user code reliably (see §6.2). v1.x hooks are process-boundary only.
- **Multi-environment apply in one invocation**: `gampan apply --env=dev,prod` is rejected at the CLI. Each apply targets exactly one environment to keep blast radius explicit.

## 3. Concepts

### 3.1 Environment

An **environment** is a named deploy target — a long-lived configuration grouping, not a deploy event. Industry-standard term (Vercel, GitHub Actions, Heroku, 12-factor). Continues the existing `Config.env` field, which v1 left as an unused label.

Choice rationale (alternatives considered):

| Candidate | Rejected because |
|---|---|
| `workspace` | Terraform workspaces are state-scoping primitives, and the TF community explicitly warns against using them for dev/prod separation. gampan's surface resembles Terraform's; reusing the term invites the same anti-pattern. |
| `stage` | Connotes a linear pipeline (dev → staging → prod). Parallel environments (`experimental`, `canary`) read awkwardly. |
| `deployment` | Conflicts with Kubernetes' `Deployment` resource. Industry uses it for the *act* of deploying (Vercel, GH deployments API), not the persistent target. |

### 3.2 Hook

A **hook** is an executable invoked per subcommand. By default gampan looks for it at `.gampan/hooks` (or `.gampan/hooks.py` with a `#!` shebang); a config block (`hook.path`, optionally with per-subcommand overrides under `hook.<subcommand>.path`) lets users point at one or more scripts outside the repo, including different scripts per subcommand. gampan invokes the resolved executable with the subcommand as `argv[1]` and JSON over stdin, expecting JSON on stdout. The hook is the entire customization surface for environment-aware transformation and policy gates.

Hooks are optional. If neither the default location nor a config override resolves to an executable file, gampan operates in single-environment mode (current v1 behavior).

### 3.3 Resource-level environment annotation

A resource YAML may declare which environments it participates in:

```yaml
_envs: [dev]   # this resource exists only in dev
```

Absent annotation = the resource is built for all declared environments (the common case). Promotion = removing or expanding the annotation.

The annotation is read by gampan core *before* the hook runs; the hook does not need to re-check it. This keeps the "is this resource in this environment?" decision in one place and visible at git review time.

## 4. Architecture

### 4.1 Pipeline placement

```
   YAML files
       │
       ▼
   core/fs/loader               ← discovers files (unchanged)
       │
       ▼
   core/env/filter              ← NEW: keep resources whose _envs (and _gam_ids)
       │                           include current env
       ▼
   core/identity/resolve        ← NEW: read each resource's _gam_ids[env]; missing
       │                           id ⇒ CREATE intent; strip _gam_ids/_envs from dict
       ▼
   core/hooks/invoke `transform`  ← NEW: data-direction hook
       │                             pass-through when absent
       ▼
   core/engine/diff             ← compares against state[env].resources[gam_id]
       │                           (CREATE actions have no state counterpart yet)
       ▼
   core/engine/planner          ← emits plan (unchanged)
       │
       ▼ (apply only)
   core/hooks/invoke `before-apply` ← NEW: lifecycle policy gate
       │                             approves by default when absent
       ▼
   core/engine/executor         ← apply; on CREATE, capture GAM-returned id and
       │                           write back to YAML (_gam_ids[env]) + state
       ▼
   core/fs/writer (YAML)        ← writes back _gam_ids after CREATE actions
```

Hook injection points:

- **`transform`** sits after identity resolution and before the diff engine. By the time it runs, the resource set is scoped to the target environment, identity (gam_id) is already resolved, and gampan-managed metadata (`_gam_ids`, `_envs`) has been stripped. Its job is to *transform* (rename, inject fields), not to filter or identify.
- **`before-apply`** sits after the plan is computed and before the executor mutates GAM. It receives the full plan and may reject; gampan does not call `before-apply` on `plan` (read-only).

### 4.2 Module additions

| Module | Responsibility |
|---|---|
| `core/env/config.py` | Parse the new `environments:` block from `config.yml`. |
| `core/env/filter.py` | Apply `_envs` annotation rules. |
| `core/identity/resolve.py` | Read `_gam_ids[env]` per resource; emit CREATE intents for missing ids; strip gampan-managed metadata (`_gam_ids`, `_envs`) before downstream stages. |
| `core/hooks/discover.py` | Per-subcommand path resolution (`hook.<sub>.path` → `hook.path` → `.gampan/hooks` → none); validate executable bit. |
| `core/hooks/invoke.py` | Subprocess invocation; serialize input, deserialize output, error envelope. |
| `core/state/store.py` | gam_id-keyed, env-nested state (§5.4); v1 → v2 migration. |
| `core/fs/writer.py` | Existing; gains write-back for `_gam_ids` after CREATE actions. |

`gam/` is untouched. The hook mechanism is environment-shaped but resource-shape-agnostic; it lives entirely in `core/`.

## 5. Schemas

### 5.1 `.gampan/config.yml` additions

```yaml
network_code: "21700000000"
default_dry_run: false

environments:                    # NEW. Absent ⇒ single-env mode (v1 behavior).
  dev:
    vars:                        # Free-form bag passed verbatim to the hook.
      ad_unit: "12345"
  prod:
    vars:
      ad_unit: "67890"

hook:                                  # NEW (optional). Override default `.gampan/hooks`
  path: ../shared/all-hooks.py         # shared fallback used for any subcommand without its own block
  before-apply:
    path: ./hooks/policy.sh            # this subcommand uses a different script
                                       # transform / reverse-transform fall back to hook.path above

sources: [...]                         # Unchanged.
```

The existing `env:` scalar field is **removed**. It was an unused label; users currently treating it as documentation should move that value into a comment or repo README. (Cleanup acceptable in v1.x because v1 is alpha.)

`vars` is an opaque dict from gampan's perspective: it is passed to the hook untouched and gampan does not interpret or validate keys.

The `hook` block is optional and hierarchical. v1.x supports `hook.path` and `hook.<subcommand>.path`; per-subcommand `env` and `args` (and friends like `timeout_sec`) are deliberately deferred until a real use case surfaces — but the hierarchy keeps room for them inside each subcommand block when added. Orgs that need those today can wrap their script in a one-line shell launcher. See §6.2 for resolution.

### 5.2 Resource YAML — gampan-managed annotations

Three underscore-prefixed metadata fields. All are gampan-managed (users may add `_envs` by hand to mark dev/prod-only resources; the rest gampan writes back on apply/import). All are stripped from the resource dict before the hook sees it.

```yaml
kind: NativeStyle
name: article-card                       # human label; freely renameable
_gam_ids:                                # env-keyed GAM identifiers
  dev: "943048"
  prod: "961262"
_envs: [dev, prod]                       # optional; defaults to declared envs
size: ...
```

#### `_gam_ids` — identity

The pair (`kind`, `_gam_ids[env]`) uniquely identifies the GAM resource for a given environment. This is what gampan keys state and diffs by — not by `name`. Renaming the `name:` field has no effect on identity; it's a label update that gampan propagates to GAM as a regular field change.

Rules:

- **Dict form (preferred)**: `_gam_ids: { dev: "<id>", prod: "<id>" }`. Each key is an env name declared in `environments:`. Values are GAM-issued IDs as strings.
- **Scalar form (deprecated, accepted for v1 back-compat)**: `_gam_id: "<id>"`. Means "same id in every env this resource participates in". v1 single-env users see this on first read; gampan emits a deprecation warning and writes back the dict form on next apply. Removed in v2.
- **Absent**: the resource has never been applied to any env. First `gampan apply --env=<X>` creates it, captures the GAM-issued ID, and writes back `_gam_ids[X]`.
- A key in `_gam_ids` that is not declared in `environments:` is a load-time error.
- The intersection of `_gam_ids` keys and `_envs` (if both set) defines what actually materializes — see §5.2 *Interaction below*.

#### `_envs` — environment participation

Declares which environments a resource should be deployed to. Different from `_gam_ids` keys: `_gam_ids` records what's *already* been applied; `_envs` declares what *should* exist.

Rules:

- `_envs` is a list of environment names. Names must appear in `environments:` in `config.yml`; unknown names are a load-time error.
- Absent `_envs` ⇒ resource participates in all declared environments.
- `_envs: []` ⇒ resource excluded from every environment (effectively disabled). Useful as a "park" state during refactor.

#### Interaction between `_envs` and `_gam_ids`

| `_envs` for env X | `_gam_ids[X]` | Plan action |
|---|---|---|
| Includes X | Present | `~ update` (diff against remote) or `=` (no change) |
| Includes X | Missing | `+ create` (apply will write back the new gam_id) |
| Excludes X | Present | `- delete` (the resource was promoted out of this env) |
| Excludes X | Missing | `=` no-op (not in this env, never was) |

This makes promotion and demotion symmetric edits:

- **Promote** dev experiment to prod: add `prod` to `_envs`. Next `apply --env=prod` creates, captures `_gam_ids[prod]`.
- **Demote** prod resource: remove `prod` from `_envs`. Next `apply --env=prod` deletes, drops `_gam_ids[prod]`.

### 5.3 `.gampan/hooks` contract

The hook is an executable file. gampan invokes:

```
.gampan/hooks <subcommand>
```

with a JSON document on stdin and expects a JSON document on stdout. All hooks share two universal exit-code conventions:

- **Exit 0** — success / approve. stdout is interpreted per the subcommand's contract.
- **Exit 64** — subcommand not implemented. gampan falls back to default behavior (no-op for data-direction hooks; approve for policy hooks). Every hook subcommand is optional via this signal.
- **Other non-zero exit** — failure. gampan surfaces stderr and aborts. For `before-*` hooks specifically, a non-zero exit with a parseable `{"reject": "..."}` on stdout is treated as a *policy rejection* (clean error message) rather than a hook crash; absence of that JSON envelope is treated as a crash.

#### Hook taxonomy

Two families:

- **Data-direction hooks** transform resource bags between YAML-shape and remote-shape. They are the primary v1.x surface.
- **Lifecycle hooks** observe (or gate) command phases. They receive event payloads, not resource bags.

| Subcommand | Family | Phase | Ship | Purpose |
|---|---|---|---|---|
| `transform` | data | plan / apply / refresh, after `_envs` filter, before diff | **v1.x** | Forward transform: canonical → remote-shape |
| `reverse-transform` | data | import, after fetch | **v1.x** (optional) | Reverse transform: remote → canonical |
| `before-apply` | lifecycle | apply, after plan is computed, before any GAM mutation | **v1.x** (optional) | Policy gate (e.g. "no prod-destroy", "must come from dev") |
| `before-plan` | lifecycle | plan / apply, before remote read | deferred | Setup, env validation, repo state gate |
| `validate` | per-resource | load-time | deferred | Org-side schema (naming rules, required fields) |
| `after-apply` | lifecycle | apply, after all actions complete | deferred | Notification, audit log, downstream trigger |
| `after-import` | lifecycle | import, after files written | deferred | Post-processing (formatter, lint) |

Deferred subcommands have their input/output shape sketched in §5.3 *Deferred subcommands* so that the v1.x contract is forward-compatible with their eventual addition. Adding a subcommand is permanently non-breaking thanks to exit 64.

#### `transform` (v1.x — required when `environments:` declared)

Invoked once per `plan`/`apply`/`refresh`, after `_envs` filtering, before diff.

Input:

```json
{
  "schema_version": 1,
  "environment": "dev",
  "config": {
    "network_code": "21700000000",
    "vars": { "ad_unit": "12345" }
  },
  "resources": [
    { "kind": "CreativeTemplate", "name": "card", ... },
    { "kind": "NativeStyle", "name": "article-card", ... }
  ]
}
```

Output:

```json
{
  "schema_version": 1,
  "resources": [
    { "kind": "CreativeTemplate", "name": "card", ... },
    { "kind": "NativeStyle", "name": "[dev] article-card", ... }
  ]
}
```

Contract notes:

- The hook **may filter** by returning fewer resources than received (e.g. to drop kinds it doesn't care about). gampan does not enforce input/output cardinality.
- The hook **must preserve** the logical `name` ↔ post-transform name mapping in a stable way across invocations; gampan does not re-key state, so a hook that decorates `article-card` as `[dev] article-card` on Monday and `[dev2] article-card` on Tuesday will produce a destroy+create plan.
- `config.vars` is the value of `environments.<env>.vars` from `config.yml`.

#### `reverse-transform` (v1.x — optional, for `import`)

Invoked by `gampan import --env=<name>`. Input is the raw remote resource set scoped to one environment; output is the canonical YAML form (suffix stripped, env-specific fields removed).

Input:

```json
{
  "schema_version": 1,
  "environment": "dev",
  "resources": [ ...raw GAM resources... ]
}
```

Output:

```json
{
  "schema_version": 1,
  "resources": [ ...canonical resources... ]
}
```

A hook that returns its input unchanged is valid — it means "I don't know how to reverse, use raw remote form". Users without a `reverse-transform` hook get the raw form and edit manually.

#### `before-apply` (v1.x — optional, policy gate)

Invoked by `gampan apply --env=<name>` after the plan is fully computed and before any GAM mutation. Receives the plan; may approve (exit 0) or reject (non-zero exit with `{"reject": "..."}`).

Input:

```json
{
  "schema_version": 1,
  "environment": "prod",
  "config": { "network_code": "21700000000", "vars": {} },
  "plan": [
    {
      "action": "create",
      "kind": "NativeStyle",
      "name": "banner-redesign",
      "post_transform_name": "banner-redesign",
      "gam_id": null
    },
    {
      "action": "update",
      "kind": "NativeStyle",
      "name": "article-card",
      "post_transform_name": "article-card",
      "gam_id": "961262",
      "changes": [
        { "field": "css", "from": "<sha256:abc>", "to": "<sha256:def>" }
      ]
    },
    {
      "action": "delete",
      "kind": "NativeStyle",
      "name": "old-style",
      "post_transform_name": "old-style",
      "gam_id": "888777"
    }
  ]
}
```

- `gam_id` is the target GAM identifier for this action. `null` for CREATE (gam_id not yet known); a string for UPDATE/DELETE.
- `name` is the canonical (pre-`transform`) `name:` value from YAML — a human label, not identity. `post_transform_name` is what the action will write to GAM as the resource's name field (e.g. `[dev] article-card` for env=dev).
- `changes` summarizes per-field diffs. For large blobs (HTML/CSS), values are sha256-prefixed hashes rather than full bodies, to keep the JSON small. Hooks that need the full body can fetch it from the YAML directly.

Output on approve: exit 0. stdout content is ignored.

Output on reject:

```
exit 1   (or any non-zero except 64)
stdout: { "schema_version": 1, "reject": "destructive change in prod requires release-train sign-off" }
```

gampan prints the `reject` message verbatim, no plan executes, exit code propagates.

Typical uses:

- **Promotion enforcement** — `if env == "prod" and any(action.kind == "NativeStyle" and not seen_in_dev_state(action.name) for action in plan): reject`.
- **Destroy-in-prod brake** — `if env == "prod" and any(action.action == "delete" for action in plan): reject unless flag_file_exists()`.
- **Size limit** — `if len(plan) > 50: reject "plan too large, split into smaller PRs"`.

#### Deferred subcommands (shape sketched; not implemented in v1.x)

These are documented so the hook framework's input format is stable across future additions. None ship in v1.x.

**`before-plan`** — invoked at the start of `plan` / `apply` before any remote read.

```
input:  { schema_version, environment, config }
output (approve):  exit 0, stdout ignored
output (reject):   exit non-zero + { reject: "..." } on stdout
```

Use case: pre-flight checks (credentials present, repo clean, dependent services healthy).

**`validate`** — invoked per resource at load-time, after schema validation, before `_envs` filtering.

```
input:  { schema_version, resource }
output (ok):     exit 0, stdout ignored
output (errors): exit non-zero + { errors: ["msg1", "msg2"] }
```

Use case: org-side naming conventions, required custom fields, cross-resource invariants.

**`after-apply`** — invoked after all actions complete (whether all succeeded or some failed).

```
input:  { schema_version, environment, results: [{action, kind, name, ok, duration_ms, error?}] }
output: exit code observed (logged as warning if non-zero, does not unwind the apply)
```

Use case: Slack notification, audit log, cache invalidation, dependent-system trigger.

**`after-import`** — invoked after `import` writes files to disk.

```
input:  { schema_version, envs: [...], imported_files: [path] }
output: exit code observed (logged as warning if non-zero)
```

Use case: formatter (`prettier`), lint, follow-up commits.

A future addition to this list can be made non-breaking by relying on exit 64 from older hook scripts that predate the new subcommand.

### 5.4 State file — sync metadata, env-nested, gam_id-keyed

State is *sync metadata about remote resources*, not the source of truth for identity. Identity lives in YAML (`_gam_ids`); state records what gampan last knew about each remote at each gam_id.

```json
{
  "schema_version": 2,
  "network_code": "21700000000",
  "environments": {
    "dev": {
      "last_apply_at": "2026-05-26T05:13:22Z",
      "last_apply_tool_version": "gampan/0.2.0",
      "resources": {
        "943048": {
          "kind": "NativeStyle",
          "name_hint": "article-card",
          "checksum_local": "sha256:a3f0...",
          "checksum_remote": "sha256:a3f0..."
        },
        "777001": {
          "kind": "CreativeTemplate",
          "name_hint": "image-banner",
          "checksum_local": "sha256:b1c2...",
          "checksum_remote": "sha256:b1c2..."
        }
      }
    },
    "prod": {
      "last_apply_at": "2026-05-26T07:01:11Z",
      "last_apply_tool_version": "gampan/0.2.0",
      "resources": {
        "961262": {
          "kind": "NativeStyle",
          "name_hint": "article-card",
          "checksum_local": "sha256:a3f0...",
          "checksum_remote": "sha256:a3f0..."
        },
        "777001": {
          "kind": "CreativeTemplate",
          "name_hint": "image-banner",
          "checksum_local": "sha256:b1c2...",
          "checksum_remote": "sha256:b1c2..."
        }
      }
    }
  }
}
```

- `schema_version` bumped to **2**. Migration from v1: on first run, gampan moves the v1 `resources` map (keyed by `<kind>:<name>`) into `environments.default.resources` (keyed by gam_id, derived from each entry's `gam_id` field). Idempotent.
- **Key** inside each env's `resources` is the `gam_id` (string). gam_id is unique within a GAM network, so within one env there's no collision risk.
- **`name_hint`** is the resource's last-known `name:` value. Purely informational — useful when a state file is reviewed in a PR. Never read by the engine.
- **Shared kinds** (e.g. `CreativeTemplate`) have the *same* gam_id in multiple env slices. The duplication is harmless; the engine treats each env slice uniformly.
- **Env-split kinds** have distinct gam_ids in each env slice.
- A single state file holds all environments. Alternative (file-per-env) was rejected because cross-environment promotion review benefits from co-located state.

#### Identity lookup flow

For each YAML resource on `apply --env=X`:

```
yaml._gam_ids[X]                          → gam_id (e.g. "943048")
state.environments[X].resources[gam_id]   → checksums
diff (yaml content after hook) vs (remote content at gam_id)
```

When `_gam_ids[X]` is missing (new resource or first-time apply to a new env), the lookup short-circuits to a CREATE action; the GAM-returned gam_id is then written back to both YAML (`_gam_ids[X]`) and state (new entry).

## 6. CLI surface

### 6.1 New flags

| Flag | Applies to | Behavior |
|---|---|---|
| `--env <name>` (alias `-e`) | `plan`, `apply`, `refresh` | Required when `environments:` is declared. Targets exactly one environment. |
| `--all-envs` | `plan` only | Iterate over every declared environment, print each plan sequentially. Convenience for PR CI. |
| `--envs <a,b,...>` | `init` only | Declare environments at scaffold time. |

`apply --env` accepts only one value by design (§2 non-goal). `--all-envs` for apply is not provided.

**`import` has no env flag** — it always covers every declared environment (see §6.3). A subset import cannot compute `_envs` correctly (a resource present only in the imported subset would be mis-tagged as subset-only, silently dropping the other envs' gam_ids), so the operation is all-envs by construction.

### 6.2 Hook discovery

Resolution is **per subcommand**. For each invocation of a hook subcommand (e.g. `transform`, `before-apply`), gampan picks an executable using this order, first match wins:

1. **Per-subcommand config** — `hook.<subcommand>.path` (e.g. `hook.before-apply.path`). If set, used for this subcommand only.
2. **Shared config fallback** — `hook.path`. If set, used for any subcommand without its own block.
3. **Default location** — `.gampan/hooks` (preferred, extensionless, language-agnostic by convention) or `.gampan/hooks.py` (accepted alternative for Python authors who want `.py` tooling).
4. **No hook** — pass-through mode (input == output for data hooks; approve for policy hooks).

Once any config-level path appears (level 1 or 2), default-location discovery (level 3) is **not** consulted as a further fallback — config is treated as the authoritative declaration. Mixing is intentional only via the explicit `hook.path` fallback layer.

Constraints:

- The resolved file must have the executable bit set; gampan does not invoke `python3 hook.py` itself — the hook's shebang line is the user's responsibility.
- For the default-location case, if both `.gampan/hooks` and `.gampan/hooks.py` exist, gampan exits with a hard error rather than guessing.
- A config-declared path (`hook.path` or any `hook.<subcommand>.path`) pointing at a non-existent or non-executable file is a hard error (no fallback to default discovery).
- A single executable file may serve multiple subcommands — gampan just invokes it with the subcommand as `argv[1]`. The hierarchical config does not preclude file reuse; it just decouples *configuration* from *file layout*.

Nuitka note: the gampan binary does **not** embed a usable Python interpreter for user scripts. Hooks run in whatever interpreter their shebang resolves to on the host, which is the user's responsibility. This avoids the entire class of "I can't `import requests` from my hook" surprises that an in-process hook would create.

If `environments:` is declared but the hook file is missing or non-executable, gampan errors at command start:

```
Error: environments declared but no executable hook found.
  Looked for: .gampan/hooks, .gampan/hooks.py
  See docs/guides/multi-env.md
```

### 6.3 `import` — always all declared environments

`gampan import` takes **no env flag**. When `environments:` is declared it imports every declared environment at once; in v1 single-env mode it imports the one (implicit) env.

```bash
$ gampan import
```

**Why no subset flag.** `import` reads one GAM network and writes canonical YAMLs whose `_envs` annotation records *which* environments each resource lives in. That determination is only correct when every declared env is seen in the same pass: a resource present in both dev and prod, imported with only dev in scope, would be written as `_envs: [dev]` and its prod `gam_id` would be silently dropped. A later `apply --env=prod` would then treat the real prod resource as unmanaged. To make this footgun unrepresentable, `import` is all-envs by construction — there is no `--env`/`--envs` selector.

Flow:

1. For each declared environment, fetch all remote resources (each with its GAM-issued `gam_id`). The fetch hits the same single network every time; the per-env pass exists so `reverse-transform` can classify resources into the right env bucket.
2. Run `reverse-transform` per environment (if the hook implements it; otherwise pass-through).
3. Build a canonical-name-keyed map per environment, retaining each entry's `gam_id`.
4. **Cross-environment reconciliation**:
   - Same canonical name in all environments, content identical ⇒ write one YAML with `_gam_ids: { <env>: <id>, ... }` covering every env present. No `_envs` annotation.
   - Same canonical name in some environments only ⇒ write one YAML with `_gam_ids` covering those envs and `_envs: [<those-envs>]`.
   - Same canonical name in multiple environments with **different content** ⇒ error, list the differences, require human resolution. (This is real drift; gampan refuses to silently pick a winner.)
5. Write state per-environment, keyed by gam_id (§5.4).

**Note on reverse-transform.** Cross-environment reconciliation depends on the canonical name being shared across environments. If the org's hook does not implement `reverse-transform`, the "canonical name" defaults to the raw remote name (`[dev] article-card` vs `article-card`, or whatever the org's convention produces) — decorated and undecorated forms never match across environments, so step 4 falls through to single-env-annotated duplicates. Multi-env import is therefore only meaningful when `reverse-transform` is implemented.

### 6.4 Safety

- `apply --env=<prod-like>` must be explicit; there is no default. (A user with one environment named `prod` and one named `dev` cannot type `gampan apply` and have it pick one.)
- `--env` value must match a declared environment in `config.yml`; otherwise hard error.
- `_envs` referencing an undeclared environment is a load-time error, not a runtime warning.
- The hook's stdout must parse as JSON conforming to the schema; malformed output aborts the run before any GAM mutation.

## 7. Worked example — single network, asymmetric prefix convention

The example below models the reference case from §1: one GAM network, prod resources carry canonical names, dev resources are decorated with a `[dev] ` prefix on GAM's `name` field. Env-split is per-kind (only `NativeStyle` and `NativeFormat` participate; `CreativeTemplate` is shared) and per-resource (some env-aware-kind resources are still prod-only or shared).

### 7.1 `.gampan/config.yml`

```yaml
network_code: "21700000000"
environments:
  dev: {}
  prod: {}
```

`vars` is omitted because this org's convention does not need per-env config beyond the env name itself. The block remains available for orgs that need it (e.g. per-env ad-unit IDs).

### 7.2 `.gampan/hooks` (committed to the repo)

```python
#!/usr/bin/env python3
"""Environment transform: decorate dev names with `[dev] ` prefix,
kind-aware (only NativeStyle and NativeFormat carry env-distinct names)."""
import json, sys

DECORATED_KINDS = {"NativeStyle", "NativeFormat"}
DEV_PREFIX = "[dev] "

sub = sys.argv[1]
inp = json.load(sys.stdin)

if sub == "transform":
    env = inp["environment"]
    out = []
    for r in inp["resources"]:
        if r["kind"] in DECORATED_KINDS and env == "dev":
            r["name"] = f"{DEV_PREFIX}{r['name']}"
        out.append(r)
    json.dump({"schema_version": 1, "resources": out}, sys.stdout)

elif sub == "reverse-transform":
    env = inp["environment"]
    out = []
    for r in inp["resources"]:
        if r["kind"] not in DECORATED_KINDS:
            out.append(r)                            # CreativeTemplate: shared, pass through for both envs
            continue
        decorated = r["name"].startswith(DEV_PREFIX)
        if env == "dev":
            if not decorated:
                continue                             # prod-form resource — not in dev import
            r["name"] = r["name"][len(DEV_PREFIX):]
        else:  # env == "prod"
            if decorated:
                continue                             # dev-decorated — not in prod import
        out.append(r)
    json.dump({"schema_version": 1, "resources": out}, sys.stdout)

else:
    sys.exit(64)   # subcommand not handled
```

Two design points the hook makes explicit:

- **Kind-awareness lives in the hook**, not in gampan. The list `DECORATED_KINDS` is the org's policy. gampan core has no notion of "which kinds are env-aware".
- **Asymmetry is honored in both directions**. Transform only decorates dev. Reverse-transform separates streams: dev import keeps only decorated resources (with prefix stripped); prod import keeps only undecorated resources; shared kinds (CT) flow into both.

### 7.3 Repo layout (after `gampan import`)

```
my-gam-iac/
├── .gampan/
│   ├── config.yml
│   ├── hooks                                       # the script above, chmod +x
│   └── state.json
├── creative-templates/
│   ├── image-banner.yaml                           # _envs absent — shared (CT is not env-split)
│   └── mobile-adhesion-banner.yaml
├── native-formats/
│   ├── feed-image-format.yaml                      # _envs absent — has both dev+prod variants in GAM
│   └── native-app-install-ad.yaml                  # _envs: [prod] — no dev variant exists
└── native-styles/
    ├── article-card.yaml                           # _envs absent — has both dev+prod variants in GAM
    ├── banner-style.yaml                           # _envs: [prod] — prod-only
    └── experimental-banner-redesign.yaml           # _envs: [dev] — long-running experiment
```

Notes:

- Filenames in this layout are the **canonical names** (prod form). The `dev-` filename prefix seen in the pre-gampan-v1.x repo is gone — one canonical YAML per logical resource.
- Each YAML carries `_gam_ids` after the first apply or import (omitted from the comments above for readability). `_gam_ids` is gampan-managed; users never hand-edit it.
- `_envs` annotations encode the cases where a resource does *not* participate in both envs. The majority of files have no `_envs` line.
- `CreativeTemplate` files never carry `_envs` because the hook's `DECORATED_KINDS` excludes them; they are deployed identically to both environments (same gam_id in both `_gam_ids` entries).

### 7.4 CI mapping to `deploy/dev` / `deploy/prod` branches

| Branch | CI step |
|---|---|
| PR against `main` | `gampan plan --all-envs` (comment on PR) |
| Push to `deploy/dev` | `gampan apply --env=dev --auto-approve` |
| Push to `deploy/prod` | `gampan apply --env=prod --auto-approve` |

Promotion is a regular git operation: merge `deploy/dev` into `deploy/prod`. Removing `_envs: [dev]` from a YAML in that merge expands the resource into prod on the next `deploy/prod` apply.

## 8. Lifecycle simulation

### 8.1 Day-1 bootstrap

```
$ gampan init --network-code 21700000000
$ vim .gampan/config.yml         # declare environments
$ vim .gampan/hooks               # author transform + reverse-transform
$ chmod +x .gampan/hooks
$ gampan import
```

Expected output for a network containing both env-split NativeStyles (e.g. `article-card` with a `[dev] article-card` counterpart), a prod-only NativeStyle, a dev-only experimental NativeStyle, and shared CreativeTemplates:

```
Imported 32 resources.
  native-styles/article-card.yaml                  _gam_ids: {dev: 943048, prod: 961262}
  native-styles/banner-style.yaml                  _gam_ids: {prod: 941001}, _envs: [prod]
  native-styles/experimental-banner-redesign.yaml  _gam_ids: {dev: 949120}, _envs: [dev]
  creative-templates/image-banner.yaml             _gam_ids: {dev: 777001, prod: 777001}  (shared)
  ...
State: 48 entries written across [dev, prod].
```

### 8.2 Routine change

```
$ vim native-styles/article-card.yaml     # edit CSS
$ git checkout -b feat/article-card-css; git push; gh pr create
```

PR CI runs `gampan plan --all-envs`:

```
[dev]   ~ NativeStyle:article-card    css: <diff>
[prod]  ~ NativeStyle:article-card    css: <diff>
```

(Plan output keys are pre-transform canonical names; the actual GAM resources mutated are `[dev] article-card` for the dev env and `article-card` for prod.)

Merge → `deploy/dev` → `gampan apply --env=dev`. QA passes. `deploy/prod` merge → `gampan apply --env=prod`.

A change to a shared kind (e.g. an `image-banner` CreativeTemplate) shows the same diff under both `[dev]` and `[prod]`, but the underlying GAM resource is the single shared one — the hook never renames CTs, so both plan rows resolve to the same remote target.

### 8.3 Long-running dev-only experiment

Add `native-styles/banner-redesign.yaml` with `_envs: [dev]` and no `_gam_ids` (brand new resource). On `deploy/dev`:

```
[dev]   + NativeStyle:banner-redesign   (new — no gam_id yet)
```

`gampan apply --env=dev` creates it in GAM, writes back `_gam_ids: { dev: 952003 }` to the YAML.

On any accidental merge into `deploy/prod` before promotion: the resource is filtered out by core (`_envs` doesn't include `prod`); `gampan apply --env=prod` shows no change for this file. No prod side-effect.

### 8.4 Promotion

```diff
 kind: NativeStyle
 name: banner-redesign
+_gam_ids: { dev: "952003" }       # already present from §8.3 apply
-_envs: [dev]
```

Merge to `deploy/dev`: no-op (resource already exists in dev). Merge to `deploy/prod`:

```
[prod]  + NativeStyle:banner-redesign   (new in prod — no _gam_ids[prod] yet)
```

`gampan apply --env=prod` creates `banner-redesign` (no `[dev] ` prefix — prod is the canonical form) in GAM, writes back so the YAML now reads `_gam_ids: { dev: "952003", prod: "952077" }`.

### 8.5 UI drift

Someone edits `article-card` (prod form, no prefix) directly in the GAM console. Next `gampan apply --env=prod`:

```
Error: drift detected for NativeStyle:article-card in env=prod
  remote css = "manually edited"
  expected (state) = <previous>
  Run `gampan refresh --env=prod` to acknowledge, then plan again.
```

This is the existing drift pre-check (v1) restricted to one environment's state slice. No new logic.

### 8.6 Demotion — shrinking `_envs`

A resource currently in both dev and prod should be retired from prod (e.g. legacy NativeStyle being phased out of public traffic), but kept in dev for archival/reference:

```diff
 kind: NativeStyle
 name: legacy-style
 _gam_ids: { dev: "920104", prod: "920200" }
-_envs absent (default = all envs)
+_envs: [dev]
```

Plan output per env:

```
[dev]   = NativeStyle:legacy-style    (unchanged; still in _envs)
[prod]  - NativeStyle:legacy-style    (env removed from _envs; gam_id=920200 will be deleted)
```

After `gampan apply --env=prod`:

- GAM resource at `gam_id=920200` is deleted.
- `_gam_ids[prod]` is removed from the YAML on write-back; the file now reads `_gam_ids: { dev: "920104" }`.
- State's `prod.resources["920200"]` entry is removed.
- Dev side completely untouched.

Re-promotion later is just adding `prod` back to `_envs` and applying — gampan treats it as a fresh CREATE in prod (new gam_id).

### 8.7 Deletion — removing the YAML entirely

The resource is no longer wanted anywhere. The user deletes the file:

```
$ git rm native-styles/legacy-style.yaml
$ git commit -m "drop legacy-style"
```

`gampan plan --all-envs` reads what's in YAML (nothing for `legacy-style`) against what's in state (entries for both envs' gam_ids). Plan output:

```
[dev]   - NativeStyle:legacy-style    (file removed; gam_id=920104 will be deleted)
[prod]  - NativeStyle:legacy-style    (file removed; gam_id=920200 will be deleted)
```

After applying to both envs:

- Both GAM resources deleted.
- Both state slice entries removed.
- No YAML to write back (file is already gone).

Plan output `name` for orphaned DELETE actions uses the `name_hint` from state (the last-known canonical name). Reviewers see a meaningful name in the diff even though the file no longer exists.

**Safety: `before-apply` is the gate.** Org policy ("no DELETE in prod without manual approval", "any DELETE requires sign-off ticket") is encoded inside the `before-apply` hook (§5.3) — it sees all action types including `delete` and can refuse.

## 9. Error handling

| Failure | Detection | Recovery |
|---|---|---|
| `environments:` declared, no executable hook | Start of any networked command | Hard error pointing to `.gampan/hooks` (or to the configured `hook.path` if set) |
| Config-declared path (`hook.path` or `hook.<sub>.path`) points at missing or non-executable file | First invocation of the affected subcommand | Hard error with the resolved path; no silent fallback to default discovery |
| Both `.gampan/hooks` and `.gampan/hooks.py` exist (no override) | Default discovery | Hard error: ambiguous; remove one or set `hook.path` |
| `before-apply` rejects (non-zero exit + `{"reject": "..."}`) | Before any GAM mutation | Print reject message verbatim; exit non-zero; no actions executed |
| `before-apply` crashes (non-zero exit, no parseable `reject`) | Before any GAM mutation | Surface stderr as hook failure; exit non-zero; no actions executed |
| Hook returns non-JSON | After subprocess completion | Print stderr + raw stdout; abort before GAM call |
| Hook exit code ≠ 0 (and ≠ 64) | After subprocess completion | Surface stderr verbatim; abort |
| Hook exit code = 64 for required subcommand (e.g. `transform`) | After subprocess completion | Hard error: "hook does not implement `transform`" |
| `_envs` lists undeclared env | Load-time | File path + line; abort before any I/O |
| `_gam_ids` key references undeclared env | Load-time | File path + key; abort before any I/O |
| Same gam_id appears in two different YAMLs (would indicate aliased configuration) | Load-time | List both file paths + the colliding id; abort |
| `_gam_ids[env]` present but state has no entry for that id in that env | First lookup | Auto-refresh that one resource from remote; if still missing in GAM, hard error suggesting `--allow-orphan-id` recovery flag |
| `--env` value not in `environments:` | CLI parse | Friendly error listing valid choices |
| Cross-env import reconciliation conflict | During `import` | Print per-resource diff; require human resolution; no partial write |
| Write-back of `_gam_ids` after CREATE fails (e.g. YAML file unwritable) | After GAM CREATE succeeds | Hard warning: GAM has the new resource but YAML is stale; print the captured gam_id so user can paste it; state is updated regardless |

The hook never sees credentials and never makes GAM API calls. It is deterministic given its input and runs in a subprocess with the user's working directory as cwd.

## 10. Backward compatibility

| User state | v1.x behavior |
|---|---|
| No `environments:`, no hook file | Identical to v1. `--env` flag absent. On the next state write, the file is rewritten to schema v2 with all entries nested under `environments.default.*`. The user is never required to type "default" anywhere. |
| User adds `environments:` (e.g. `dev`, `prod`) to an existing repo | On the next command, gampan detects state schema v2 with only `default` populated and `environments:` newly declared. It refuses to proceed and prints: re-run `gampan import` to repopulate state per environment, or manually edit the state file to rename `default` to the intended env. No new CLI command; the user's path forward is import (which already understands multi-env). |
| `env:` field present in old `config.yml` | Read and warned ("the `env:` field is removed in v1.x; move to a comment or use `environments:`") but otherwise ignored. Not a hard error in v1.x to ease transition; becomes one in v2. |
| YAML carries scalar `_gam_id: "<id>"` (v1 form) | Accepted with a deprecation warning. On the next apply, gampan rewrites the YAML in place: `_gam_id: "<id>"` → `_gam_ids: { <env>: "<id>" }` where `<env>` is the env being applied (or `default` if no `environments:` declared). v2 removes scalar acceptance. |
| YAML carries no identity field at all (`_gam_id` and `_gam_ids` both absent) | Treated as a brand-new resource. First `apply --env=X` creates it in GAM, captures the returned id, writes back `_gam_ids[X]`. Plan output flags these explicitly so reviewers see "this YAML will create a new GAM resource". |
| State file references a gam_id that no longer exists in any YAML's `_gam_ids` | Plan shows a DELETE action keyed by that gam_id (the resource was removed from configuration). Apply executes the delete; user can opt out with `--exclude-deletes` (existing v1 flag, if available) or by re-adding the YAML entry. |

## 11. Open questions

1. **Hook caching** — the hook is pure given its input; gampan could cache transformed resources by input hash to speed up `plan --all-envs`. Defer until perf data justifies it.
2. **Hook discovery in monorepos** — `.gampan/` is per-repo today; if gampan moves toward multi-config repos, hook scope follows config scope. Out of v1.x scope.
3. **Schema versioning of the hook contract** — the input/output documents carry `schema_version: 1`. The bump-and-handshake protocol for v2 of the hook contract is not specified yet; first breaking change will define it.
4. **Promotion enforcement** — "prod must be reached only via dev" is policy, not gampan logic. The `before-apply` hook (§5.3) is the v1.x vehicle: orgs that need this rule author the check inside their hook. No reference implementation ships with gampan; one may be added as an `examples/` snippet once a real org commits to the convention.
5. **`name_hint` staleness in state** — when a YAML `name:` is renamed but the resource is not re-applied to every env, the env slices that weren't applied still carry the old name_hint. This is informational-only data (engine ignores it) but may confuse PR reviewers reading state diffs. Acceptable for v1.x; could be self-healing on next refresh.

## 12. Success criteria

1. **Real-world onboarding**: an organization with an existing single-network dev/prod setup — where env distinction lives in names and/or fields per a per-kind convention — can adopt gampan via `gampan init` → author hooks → `gampan import`, ending with a clean repo whose `deploy/dev` and `deploy/prod` branches run `gampan apply --env=<env>` in CI.
2. **Single source of truth**: editing one YAML file produces synchronized changes across both environments in `gampan plan --all-envs` output, with no shared-content duplication on disk.
3. **Dev-only escape hatch**: a resource with `_envs: [dev]` never appears in any `prod` plan, even when merged into `deploy/prod`.
4. **Backward compatible**: existing v1 single-environment repos continue to work without authoring a hook or declaring environments.
5. **State safety**: state for `dev` and `prod` resources is fully isolated; an apply error in one environment cannot corrupt the other's state slice.
