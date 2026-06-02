# Example: multi-env GAM repo with a kind-aware prefix convention

This example models the most common multi-environment pattern observed in real production GAM repos:

- **One GAM network.** Dev and prod resources coexist.
- **Asymmetric naming.** Prod resources carry the canonical name unchanged (e.g. `article-card`); dev resources are decorated with a `[dev] ` prefix on GAM's `name` field (e.g. `[dev] article-card`).
- **Kind-asymmetric env-awareness.** `NativeStyle` and `NativeFormat` are env-split. `CreativeTemplate` is shared — one resource serves both environments.
- **Resource-level env-awareness.** Most env-aware-kind resources exist in both envs; some are prod-only or dev-only.
- **Branch-driven deploys.** `deploy/dev` and `deploy/prod` git branches gate CI applies per environment.

The reference spec is at [`docs/specs/2026-05-26-multi-env-management-design.md`](../../docs/specs/2026-05-26-multi-env-management-design.md).

## Files

- **`.gampan/config.yml`** — declares the two environments. `vars` is empty in this example because this convention doesn't need per-env config beyond the env name.
- **`.gampan/hooks`** — executable Python script implementing the prefix convention. Handles `transform` (forward) and `reverse-transform` (during import); exits 64 for anything else (pass-through).
- **`native-styles/`**, **`creative-templates/`**, **`native-formats/`** — would contain canonical YAML files after `gampan import`. Not included here (network-specific data).

## Hook walkthrough

The hook's core policy lives in two constants:

```python
DECORATED_KINDS = {"NativeStyle", "NativeFormat"}
DEV_PREFIX = "[dev] "
```

### `transform` (forward, runs during `plan` / `apply` / `refresh`)

Input: gampan-canonical resources for the target env.

Behavior:
- For each resource whose `kind` is in `DECORATED_KINDS`, prepend `[dev] ` to its `name` if the env is `dev`. Prod runs leave names untouched.
- `CreativeTemplate` flows through unmodified (shared kind).

### `reverse-transform` (runs during `gampan import`)

Input: raw remote resources fetched from GAM for one env.

Behavior (separates streams):
- `CreativeTemplate` resources flow into both envs unchanged (shared).
- For decorated kinds (NS / NF):
  - When importing **dev**: keep only resources whose `name` starts with `[dev] `, strip the prefix.
  - When importing **prod**: keep only resources whose `name` does NOT start with `[dev] `.

This split is what lets `gampan import` produce one canonical YAML per logical resource, with `_gam_ids: {dev: ..., prod: ...}` recording both remote identifiers.

## Adopting this convention in your repo

```bash
# 1. Scaffold with environments declared up front.
gampan init --network-code <YOUR_GAM_NETWORK_CODE> --envs dev,prod

# 2. Copy this directory's .gampan/hooks into your repo, chmod +x it.
cp examples/multi-env/.gampan/hooks .gampan/hooks
chmod +x .gampan/hooks

# 3. Import (always covers every declared environment).
gampan import
```

After import, each canonical YAML carries an env-keyed `_gam_ids` block:

```yaml
kind: NativeStyle
_gam_ids:
  dev: "943048"
  prod: "961262"
name: article-card
size: { width: 1, height: 1, is_fluid: false }
# ...
```

Resources that exist in only one env get an `_envs` annotation:

```yaml
kind: NativeStyle
_gam_ids:
  dev: "999000"
_envs: [dev]
name: experimental-banner
```

## CI wiring (deploy/dev, deploy/prod)

| Branch | CI step |
|---|---|
| PR against `main` | `gampan plan --all-envs` (comment on PR) |
| Push to `deploy/dev` | `gampan apply --env=dev --auto-approve` |
| Push to `deploy/prod` | `gampan apply --env=prod --auto-approve` |

Promotion is a regular git operation: merge `deploy/dev` into `deploy/prod`. Removing `_envs: [dev]` from a YAML in that merge expands the resource into prod on the next `deploy/prod` apply.

## Adapting the convention

Different orgs encode the dev/prod distinction differently:

- **Suffix instead of prefix** (`-dev`/`-prod`): swap `DEV_PREFIX` for a `-dev` suffix, change `startswith` → `endswith`, and strip from the right.
- **GAM tags / targeting fields**: replace the name-decoration logic with field manipulation (e.g. inject `targeting.custom: {env: "dev"}`).
- **Separate GAM networks**: out of scope for this example; would require separate `network_code` per env, which the v1.x spec doesn't support yet (see §2 non-goals).
- **All kinds env-aware**: drop the `DECORATED_KINDS` filter so the prefix applies to every kind.

The hook is yours to author — gampan ships the mechanism, not the policy.
