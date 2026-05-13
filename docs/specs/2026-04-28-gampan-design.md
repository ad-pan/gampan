# gampan v1 — Design Spec

- **Status**: Draft (brainstorming output, pre-implementation)
- **Author**: Sejun Jeong (@zb-sj)
- **Date**: 2026-04-28
- **Scope**: gampan v1 — Google Ad Manager CLI within the `ad-pan` ecosystem

## 1. Purpose

`gampan` is a declarative, Terraform-style CLI for managing Google Ad Manager (GAM) resources as code. Users define ad resources in YAML files, version them in git, and run `gampan plan` / `gampan apply` to reconcile remote GAM state with the repo.

v1 ships with two resource types:

- **NativeStyle** — native ad rendering templates (HTML/CSS + variables)
- **CreativeTemplate** — creative template definitions used by GAM line items

These resources currently lack first-class export/version-control tooling. The immediate motivating problem (internal ticket HGNN-12911) is that GAM's console offers no export for native styles, forcing manual copy-paste during audits, migrations, or recovery.

## 2. Ecosystem context

`gampan` is the first CLI in the **ad-pan** ecosystem of declarative ad-platform tools.

```
ad-pan/                           ← GitHub org + brand (간판 = signboard, ad-domain root)
├── gampan                        ← v1: Google Ad Manager (this spec)
├── naverpan                      ← future: Naver GFA
├── kakaopan                      ← future: Kakao Ad
├── metapan                       ← future: Meta Audience Network
│       …
│
├── ad-pan-core                   ← Python lib (post-v1): state, diff engine, planner, fs loader
│
└── adpan (orchestrator)          ← v3+: cross-network workflows (optional)
```

Roadmap:

| Phase | Deliverable | Time |
|---|---|---|
| v1 (alpha) | `gampan` standalone repo. NativeStyle + CreativeTemplate. PyPI + nuitka binaries. | 0–2 months |
| v1.x | Extract `ad-pan-core` from gampan; both published independently; no user-facing change. | 2–4 months |
| v2 | Second `*pan` (driven by real demand). Proves the abstraction. | 4–8 months |
| v3 | `adpan` orchestrator CLI for cross-network workflows. | 8–12 months |

## 3. Architecture

### 3.1 High-level diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      gampan CLI (typer)                           │
│   init   import   plan   apply   refresh   info   version         │
└─────────────────┬────────────────────────────────────────────────┘
                  │
        ┌─────────▼──────────┐
        │   core/            │   Pure logic — no I/O
        │   - engine/diff    │   YAML model ↔ remote model diff
        │   - engine/planner │   Action plan (CREATE/UPDATE/DELETE)
        │   - engine/executor│   Run actions idempotently
        │   - fs/            │   YAML + side-file loader
        │   - state/         │   state.json read/write + schema
        │   - protocols.py   │   Resource / Client ABCs
        └─────────┬──────────┘
                  │
   ┌──────────────┼──────────────┐
   │              │              │
┌──▼───┐    ┌────▼─────┐    ┌────▼──────┐
│ fs/  │    │  state/  │    │ clients/  │  ← Per-resource adapter
│ load │    │  read/   │    │  ┌─────┐  │
│ YAML │    │  write   │    │  │SOAP │  │  NativeStyle (today)
└──────┘    └──────────┘    │  └─────┘  │
                            │  ┌─────┐  │
                            │  │REST │  │  CreativeTemplate (today)
                            │  └─────┘  │  + NativeStyle (when Google
                            └───────────┘    ships REST coverage)
```

### 3.2 Module boundaries

- **`core/`**: Domain-agnostic IaC machinery. Will be extracted into `ad-pan-core` after v1. Knows about `Resource` and `Client` protocols (ABCs); has no concept of GAM specifically.
- **`gam/`**: GAM-specific concrete implementations. Pydantic models for NativeStyle / CreativeTemplate. Clients for SOAP and REST.
- **`cli/`**: typer commands. GAM-specific entrypoints; thin wrappers around `core/` + `gam/`.

The `core/` ↔ `gam/` line is the future extraction boundary. v1 keeps both in one repo for velocity; v1.x extracts `core/` without breaking changes.

### 3.3 Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Runtime mgr | mise | Pins Python version + task runner |
| Language | Python 3.12+ | Required for `tomllib`, structural pattern matching |
| Dep mgr | uv | Fast, lockfile-driven |
| CLI framework | typer | Type-hint-driven, derives from Click |
| Schema | pydantic v2 | YAML ↔ model validation |
| YAML | ruamel.yaml | Round-trippable, preserves comments/order |
| Logging | structlog + rich | Human + JSON output |
| HTTP retry | tenacity | Exponential backoff on 5xx |
| Tests | pytest + vcrpy | Unit + replay-based integration |
| Binary build | nuitka | True compiler, single-file output |
| Release versioning | `@changesets/cli` | PR-level changeset entries → auto-generated CHANGELOG |

## 4. Repo layout

### 4.1 `gampan` repo (this project)

```
gampan/
├── src/gampan/
│   ├── __main__.py              # `python -m gampan` entry
│   ├── cli/                     # typer commands
│   │   ├── init.py
│   │   ├── import_cmd.py
│   │   ├── plan.py
│   │   ├── apply.py
│   │   ├── refresh.py
│   │   ├── info.py
│   │   └── version.py
│   │
│   ├── core/                    # → future ad-pan-core
│   │   ├── engine/
│   │   │   ├── diff.py
│   │   │   ├── planner.py
│   │   │   └── executor.py
│   │   ├── fs/
│   │   │   ├── loader.py
│   │   │   └── refs.py          # !file custom YAML tag
│   │   ├── state/
│   │   │   ├── schema.py
│   │   │   └── store.py
│   │   ├── protocols.py         # Resource, Client ABCs
│   │   └── errors.py
│   │
│   └── gam/                     # GAM-specific
│       ├── clients/
│       │   ├── soap.py
│       │   ├── rest.py
│       │   └── adapter.py       # per-resource routing
│       ├── models/
│       │   ├── native_style.py
│       │   └── creative_template.py
│       └── auth.py              # ADC bootstrap
│
├── tests/
│   ├── unit/
│   ├── integration/             # vcrpy cassettes
│   └── e2e/                     # opt-in, real GAM sandbox
│
├── examples/                    # example user repos
│   ├── basic/
│   └── multi-env/
│
├── docs/
│   ├── specs/                   # design docs (this file)
│   ├── guides/                  # user-facing how-to
│   └── reference/               # CLI + schema reference
│
├── .changeset/                  # changesets entries
├── pyproject.toml               # uv-managed, hatchling build
├── mise.toml                    # python 3.12, uv, task runner
├── .python-version
├── nuitka.yaml                  # per-platform compile config
├── package.json                 # for @changesets/cli only
├── LICENSE                      # Apache 2.0
├── CHANGELOG.md                 # generated by changesets
├── README.md
└── CONTRIBUTING.md              # includes DCO + Code of Conduct
```

### 4.2 User's repo (scaffolded by `gampan init`)

```
my-gam-config/
├── .gampan/
│   ├── config.yml               # network code, env, optional source paths
│   └── state.json               # committed; managed by gampan
├── native-styles/
│   ├── article-card.yaml
│   ├── article-card.html        # referenced by !file
│   └── article-card.css
├── creative-templates/
│   └── interstitial.yaml
└── README.md
```

Default layout follows convention; custom layouts supported via `sources:` in `config.yml`.

## 5. User-side schemas

### 5.1 `.gampan/config.yml`

```yaml
network_code: "21700000000"
env: prod
default_dry_run: false

# Optional: customize resource locations
sources:
  native_style:
    - "ads/native/**/*.yaml"
  creative_template:
    - "templates/creatives/**/*.yaml"

# Alternative flat mode (kind-by-content):
# sources:
#   - "resources/**/*.yaml"
```

Three layout modes:

| Mode | Config | Discovery |
|---|---|---|
| Convention (default) | `sources:` omitted | Fixed dirs: `native-styles/`, `creative-templates/` |
| Per-kind explicit | `sources: {kind: [globs]}` | Glob patterns mapped to kinds |
| Flat / mixed | `sources: [globs]` | Single glob; each file's `kind:` field discriminates |

### 5.2 NativeStyle YAML

```yaml
# native-styles/article-card.yaml
kind: NativeStyle
name: article-card                  # ← logical identity (stable, code-side)
size:
  width: 320
  height: 250
  is_fluid: false
template_id: 12345                  # FK to CreativeTemplate (raw gam_id in v1)
html: !file ./article-card.html     # custom YAML tag → side-file content
css:  !file ./article-card.css
targeting:
  ad_units: [hogangnono/article]
  custom: {}
status: ACTIVE
```

- `!file` is a custom YAML constructor that loads side-file content at parse time.
- `gam_id` is **not** in the YAML — it lives in `state.json`.
- `template_id` is a foreign key (raw GAM ID in v1; symbolic refs deferred to v2).

### 5.3 CreativeTemplate YAML

```yaml
# creative-templates/interstitial.yaml
kind: CreativeTemplate
name: interstitial
description: "Full-screen interstitial with countdown"
type: USER_DEFINED
snippet: !file ./interstitial.html
variables:
  - name: headline
    type: STRING
    required: true
    description: "Ad headline (max 40 chars)"
  - name: image_url
    type: URL
    required: true
  - name: cta_text
    type: STRING
    default: "자세히 보기"
status: ACTIVE
```

Pydantic v2 models in `gam/models/` validate types, requireds, and enum values at load-time. Schema errors fire **before** any API call.

### 5.4 `.gampan/state.json`

```json
{
  "schema_version": 1,
  "network_code": "21700000000",
  "last_apply_at": "2026-04-28T05:13:22Z",
  "last_apply_tool_version": "gampan/0.1.0",
  "resources": {
    "native_style:article-card": {
      "gam_id": "12345678",
      "checksum_local": "sha256:a3f0...",
      "checksum_remote": "sha256:a3f0...",
      "last_modified_remote": "2026-04-24T11:02:00Z"
    },
    "creative_template:interstitial": {
      "gam_id": "98765432",
      "checksum_local": "sha256:e2c1...",
      "checksum_remote": "sha256:e2c1...",
      "last_modified_remote": "2026-04-22T03:18:00Z"
    }
  }
}
```

- **Composite key** `<kind>:<name>` — prevents collisions across kinds.
- **Two checksums** — `local` (what we last applied) vs `remote` (what GAM last had). Divergence indicates drift.
- **`schema_version`** enables forward-compatible state migrations.
- **Committed to git** — sidecar state model. No remote backend in v1.

## 6. CLI surface

| Command | Network? | Mutates | Purpose |
|---|---|---|---|
| `gampan init` | ❌ | local fs | Scaffold user repo (`.gampan/config.yml`, dirs) |
| `gampan import` | ✅ | local fs + state | Pull GAM resources into YAML files + state |
| `gampan plan` | ✅ | nothing | Show diff (YAML ↔ GAM via state); print actions |
| `gampan apply` | ✅ | GAM + state | Execute the plan (confirms unless `--auto-approve`) |
| `gampan refresh` | ✅ | state only | Re-sync state.json from GAM (heal UI-side drift) |
| `gampan info` | ✅ (skippable) | nothing | Diagnostic: version, auth, network, config, resources |
| `gampan version` | ❌ | nothing | Binary version + build info |

### 6.1 Exit codes

| Code | Meaning |
|---|---|
| 0 | Success / no changes |
| 1 | API/runtime error |
| 2 | Plan has pending changes (use with `--detailed-exitcode` for CI gating) |
| 3 | User aborted (declined confirmation) |

### 6.2 Data flow per command

#### `import`

```
ADC auth → clients/adapter:
  - SOAP: NativeStyleService.getNativeStylesByStatement(*)
  - REST: networks/{n}/creativeTemplates (list)
        │
        ▼
For each remote resource:
  ① Pydantic model from response
  ② Write `<dir>/<slug>.yaml` (+ side `.html` / `.css`)
  ③ Append/update state.json: { "<kind>:<name>": { gam_id, checksum } }
```

Re-running is idempotent (overwrites YAML; `--dry-run` to inspect).

#### `plan`

```
Read YAML files via core/fs
Read state.json
For each desired (YAML) resource:
  - state entry exists? → fetch remote by gam_id, diff → CREATE / UPDATE / NO_CHANGE
  - no state entry?     → CREATE
For each state entry with no matching YAML:
  - DELETE (red warning at apply time)
Emit:
  - Human-readable table (default)
  - Machine-readable (--json) for CI gating
```

#### `apply`

```
Re-run plan in-memory (fresh state)
Print plan + summary
Prompt: "Apply N changes? (yes/no)" unless --auto-approve
For each action sequentially:
  - Execute via clients/adapter
  - On success: update state.json + checksum
  - On error: stop, persist partial state, exit 1
Print summary
```

#### `refresh`

```
ADC auth → list all remote resources
For each state entry:
  - Re-fetch remote by gam_id
  - Update state.json checksum
Note drifted entries: "remote changed since last apply"
```

### 6.3 `gampan info` output

```
$ gampan info
gampan 0.1.0

Auth
  Method:           service_account
  Principal:        gampan-bot@zigbang-prod.iam.gserviceaccount.com
  Source:           GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/sa.json

Network
  Network code:     21700000000
  Display name:     Hogangnono Ad Manager
  Connected:        ✓ ok

Config
  Config file:      .gampan/config.yml
  Layout mode:      convention
  Discovered:       14 native styles, 3 creative templates

State
  State file:       .gampan/state.json
  Schema version:   1
  Last apply:       2026-04-24 11:02 KST (gampan/0.1.0)
```

`--offline` skips network call; `--json` for machine-readable output.

## 7. Auth

**Strategy**: Google Application Default Credentials (ADC). Zero custom auth code in gampan.

```
gampan boots → ADC lookup order:
  1. GOOGLE_APPLICATION_CREDENTIALS env var → service account JSON
  2. `gcloud auth application-default login` → user OAuth refresh token
  3. GCE/Cloud Run metadata server (for CI on GCP)
```

User onboarding (documented in README):

```bash
# Local dev (one-time)
gcloud auth application-default login

# CI
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json

# Sanity check
gampan info
```

Required GAM role: **Trafficker** or above for read; **Admin** or **Publisher** for write. Documented per-command in `docs/reference/`.

## 8. Error handling

| Failure | Detection | Recovery |
|---|---|---|
| Auth missing/expired | Pre-flight in any networked command | Message: run `gcloud auth application-default login` |
| Network code mismatch | First API call → 403/404 | Print expected vs actual, exit 1 |
| YAML invalid (schema) | Pydantic v2 at load-time | Friendly error w/ file path + line, **before** any API call |
| Side `!file` not found | Loader resolves immediately | File path + parent YAML printed |
| GAM API 5xx | Transient | Exponential backoff (1s, 2s, 4s, 8s, max 4 retries) via tenacity |
| GAM API 4xx (validation) | Permanent | No retry; print GAM's error verbatim + which resource failed |
| Partial apply mid-flight | Each action persists state.json on success | On crash, `gampan plan` shows exactly what's left |
| Concurrent applies | State.json git push conflict | Standard git-merge resolution; **no in-tool lock for v1** |
| Drift (UI edit) | `gampan plan` reads remote, diffs vs state.json checksum | `gampan refresh` re-syncs state; then `plan` to review |

### 8.1 Logging

- **`structlog`** with two output modes:
  - Default: human-readable (boxed messages, colors via rich)
  - `--log-format json`: structured JSON to stderr
- Verbosity: `-v` (debug), `-vv` (trace API calls), `--quiet` (errors only)
- **No telemetry, no phone-home.**

## 9. Testing

| Layer | Scope | Tools |
|---|---|---|
| Unit (`tests/unit/`) | Pure logic: diff, planner, fs loader, state read/write, schema validation | pytest + pure functions |
| Integration (`tests/integration/`) | Full command flows against fake GAM | `vcrpy` HTTP recordings (REST); googleads-python-lib mock layer (SOAP) |
| E2E (`tests/e2e/`, opt-in via `pytest -m e2e`) | Real GAM sandbox network | Real ADC creds; CI nightly only |

- vcrpy cassettes committed; re-recordable with explicit flag.
- Engine code is pure → no mocking; tests pass fake `Resource` / `Client` objects via Protocol.
- E2E requires `GAMPAN_E2E_NETWORK_CODE` + creds; not run on every PR.

## 10. Release & distribution

- **License**: Apache 2.0 (matches Terraform, kubectl, prevailing dev-tool norm; patent grant).
- **CLA / DCO**: DCO (`Signed-off-by:` line) — lighter than CLA, widely accepted.
- **Code of Conduct**: Contributor Covenant 2.1.
- **Versioning**: SemVer. `0.x.y` during alpha/beta (breaking changes allowed in minor); `1.0.0` when state.json schema and CLI surface are committed-to.
- **Release artifacts** via GitHub Actions:
  - Nuitka-compiled binaries: `gampan-{linux-x64,linux-arm64,macos-x64,macos-arm64}`
  - Checksums + GitHub release provenance
  - PyPI: `pip install gampan` / `pipx install gampan`
  - Homebrew tap (eventual): `brew install ad-pan/tap/gampan`
- **CHANGELOG**: Generated by `@changesets/cli`. Each PR includes a `.changeset/*.md` entry; release CI consumes them.

## 11. Open questions (TBD, do not block v1)

1. **Multi-env strategy** (dev/staging/prod networks) — workspaces? Separate state files? Defer to v1.x once real users surface needs.
2. **Secrets in resource YAML** — most GAM resource fields aren't secret, but worth a final review during implementation.
3. **Concurrent-apply lock** — relies on git push conflict in v1. Document. Revisit if real-world users hit issues.
4. **REST migration path** — when Google ships REST `NativeStyle`, the per-resource adapter swaps from SOAP to REST. May offer a `gampan migrate-client` helper if migration has noticeable user impact.
5. **Symbolic refs across resources** — v1 uses raw `gam_id` for `template_id` FK in NativeStyle. v2 may introduce `!ref creative_template:interstitial` for git-friendly refs.
6. **Resource-name uniqueness in GAM** — GAM doesn't strictly enforce unique names for NativeStyle / CreativeTemplate at the API level. v1 relies on `gam_id` in state for identity; conflicts at `import` time (two resources with same name) become a `gampan import` warning.

## 12. Non-goals (v1)

- Reporting / line-item / order management (defer; covered by REST API today, but not in scope).
- Multi-tenant / SaaS hosting — gampan is a local CLI; no service to host.
- Web UI — out of scope for v1; CLI + git is the entire surface.
- Cross-network workflows — that's `adpan` orchestrator territory, v3+.
- Real-time sync / webhooks — gampan runs on demand.

## 13. Success criteria for v1

1. **Day-one win**: `gampan init && gampan import --resource native-styles` produces a clean, version-controllable repo from any existing GAM network in under a minute. Solves the HGNN-12911 manual-copy problem.
2. **Round-trip**: `gampan import` → edit YAML → `gampan plan` shows expected diff → `gampan apply` updates GAM and state.json without manual intervention.
3. **Drift recovery**: someone edits a native style in the GAM UI; `gampan plan` correctly detects drift; `gampan refresh` heals state without losing user's YAML changes.
4. **Distribution**: single-file nuitka binary installs via brew, pipx, or curl on macOS (arm64+x64) and linux (x64+arm64). PyPI install also works.
5. **Tests**: ≥80% line coverage on `core/` (engine, fs, state); integration tests cover the happy path for all commands; opt-in e2e for the full apply cycle on a sandbox network.
