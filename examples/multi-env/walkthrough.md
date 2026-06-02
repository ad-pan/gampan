# Multi-env walkthrough — copy-pasteable command sequence

This file walks through every multi-env CLI command in order, showing the inputs and the on-disk state after each step. Mirrors `tests/integration/test_multi_env_e2e.py` so the test and the human-readable docs stay in sync.

> Prerequisites: gampan installed (`pipx install gampan` or `pip install gampan`), and a GAM network with a `Trafficker`-or-above credential. For the walkthrough we assume placeholder network code `21700000000`.

## 0. Scaffold

```bash
mkdir my-gam-iac && cd my-gam-iac
gampan auth login
gampan init --network-code 21700000000 --envs dev,prod
```

This scaffolds `.gampan/config.yml` with the environments already declared:

```yaml
network_code: "21700000000"
default_dry_run: false
include_archived: false
environments:
  dev: {}
  prod: {}
```

Copy the example hook:

```bash
cp /path/to/gampan/examples/multi-env/.gampan/hooks .gampan/hooks
chmod +x .gampan/hooks
```

(See `examples/multi-env/.gampan/hooks` in this repo for the reference script. Adapt `DECORATED_KINDS` / `DEV_PREFIX` to your org's convention.)

## 1. Import — pull both envs into canonical YAML

```bash
gampan import
```

For a GAM network that holds e.g. `[dev] article-card` and `article-card` as two NativeStyles, gampan emits:

```
  ✓ native-styles/article-card.native-style.yaml
  ✓ creative-templates/image-banner.creative-template.yaml
  ...
State: 14 resources tracked in .gampan/state.json across 2 env(s)
```

`native-styles/article-card.native-style.yaml`:

```yaml
kind: NativeStyle
_gam_ids:
  dev: "943048"
  prod: "961262"
name: article-card
size:
  width: 320
  height: 250
  is_fluid: false
template_id: 1
html: !file ./article-card.native-style.html
css:  !file ./article-card.native-style.css
status: ACTIVE
```

No `_envs` annotation — the resource participates in every declared env.

For a dev-only resource the YAML carries `_envs: [dev]` plus a single-key `_gam_ids`:

```yaml
kind: NativeStyle
_gam_ids:
  dev: "949120"
_envs: [dev]
name: experimental-banner
...
```

## 2. Routine update — edit one YAML, plan both envs

```bash
vim native-styles/article-card.native-style.css   # tweak CSS
gampan plan --all-envs
```

```
=== env: dev ===
  ~  NativeStyle:[dev] article-card
      css:
        - "<sha256:abc1234>"
        + "<sha256:def5678>"
Plan: 0 to add, 1 to change, 0 to destroy.

=== env: prod ===
  ~  NativeStyle:article-card
      css:
        - "<sha256:abc1234>"
        + "<sha256:def5678>"
Plan: 0 to add, 1 to change, 0 to destroy.
```

Note the actual remote name differs per env (`[dev] article-card` vs `article-card`) because the `transform` hook decorates dev but leaves prod canonical.

## 3. Apply dev, then prod

```bash
gampan apply --env=dev --auto-approve
# QA on dev...
gampan apply --env=prod --auto-approve
```

`.gampan/state.json` after both applies:

```json
{
  "schema_version": 2,
  "network_code": "21700000000",
  "environments": {
    "dev":  { "resources": { "943048": {...} } },
    "prod": { "resources": { "961262": {...} } }
  }
}
```

Same content under both keys; different gam_ids reflect the two GAM resources.

## 4. New dev-only experiment

Create `native-styles/experimental-banner.native-style.yaml` *without* `_gam_ids`:

```yaml
kind: NativeStyle
_envs: [dev]
name: experimental-banner
size: { width: 320, height: 50, is_fluid: false }
template_id: 1
html: "<div class='exp'>...</div>"
css: ".exp { color: blue; }"
status: ACTIVE
```

```bash
gampan apply --env=dev --auto-approve
```

CREATE fires; the GAM-returned id is written back to the YAML:

```yaml
kind: NativeStyle
_gam_ids:
  dev: "952003"
_envs: [dev]
name: experimental-banner
...
```

A merge into `deploy/prod` at this point is a no-op for this file (the `_envs` filter drops it before the diff).

## 5. Promote the experiment to prod

```bash
sed -i '' '/_envs:/d' native-styles/experimental-banner.native-style.yaml
gampan apply --env=prod --auto-approve
```

CREATE fires again for the prod env; write-back records both gam_ids:

```yaml
kind: NativeStyle
_gam_ids:
  dev: "952003"
  prod: "952077"
name: experimental-banner
...
```

The prod GAM resource carries the canonical (undecorated) name `experimental-banner`.

## 6. CI wiring

| Trigger | CI step |
|---|---|
| PR against `main` | `gampan plan --all-envs` |
| Push to `deploy/dev` | `gampan apply --env=dev --auto-approve` |
| Push to `deploy/prod` | `gampan apply --env=prod --auto-approve` |

Promotion is `git merge deploy/dev → deploy/prod`.

## 7. Deletion / demotion

```bash
# Demote: shrink _envs
vim native-styles/legacy-style.native-style.yaml
# add `_envs: [dev]` to remove prod participation

gampan apply --env=prod --auto-approve
# Plan shows `- NativeStyle:legacy-style` — prod gam_id is deleted, _gam_ids[prod] removed from YAML.
```

```bash
# Full delete: drop the file
git rm native-styles/legacy-style.native-style.yaml
gampan plan --all-envs    # both envs show a DELETE
gampan apply --env=dev --auto-approve
gampan apply --env=prod --auto-approve
```

State entries are removed; `before-apply` hook is the right place to gate destructive prod operations behind sign-off.
