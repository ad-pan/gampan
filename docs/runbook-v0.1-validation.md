# gampan v0.1.0 — End-to-End Validation Runbook

This runbook guides you through a single guided session that proves `gampan v0.1.0` works end-to-end against a real Google Ad Manager **test network**.

## Background: the test-network model

Google Ad Manager allows each Google account to create exactly **one** API test network via `makeTestNetwork`. The test network:

- is isolated from any production inventory — nothing you do here touches real ads
- ships with a small set of pre-seeded creative templates (including template ID `10000680`, "Standard Native")
- has a hard limit of 10,000 objects
- is tied to your Google account; you cannot create a second one (the call is idempotent — repeated calls return the existing network)

`gampan bootstrap-test-network` calls `makeTestNetwork` once and writes the returned `network_code` to `.gampan/config.yml`. Running it again on the same account is safe; it returns the same network.

---

## Prerequisites

- Python 3.12+ with `uv` available (`pip install uv` or `brew install uv`)
- `gampan` installed from this repo: `cd /path/to/gampan && uv sync --extra dev && uv pip install -e .`
- A Google account with Ad Manager API access

---

## Step 1 — Register an OAuth client

1. Open <https://console.cloud.google.com> in a browser.
2. Create or select any Google Cloud project.
3. Enable the **Google Ad Manager API** (search for it in the API Library).
4. Navigate to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
5. Application type: **Desktop app**. Give it any name (e.g. `gampan-dev`).
6. Click **Create**, then **Download JSON**.
7. Set the environment variables in your terminal session:

```bash
export GAMPAN_OAUTH_CLIENT_ID="<your_client_id>"
export GAMPAN_OAUTH_CLIENT_SECRET="<your_client_secret>"
```

**Expected**: variables set, no output.

**If it fails**: Ensure the Ad Manager API is enabled and OAuth consent screen is configured (External type is fine for testing; add your Google account as a test user).

---

## Step 2 — Authenticate

```bash
gampan auth login
```

A browser window opens to Google's consent screen. Approve access. Credentials are stored in the system keyring.

**Expected output** (approximately):

```
Opening browser for Google OAuth…
✓ Credentials stored (keyring).
```

**If it fails**: Check that `GAMPAN_OAUTH_CLIENT_ID` and `GAMPAN_OAUTH_CLIENT_SECRET` are set correctly. If the browser does not open, copy the printed URL and paste it manually.

---

## Step 3 — Bootstrap the test network

```bash
mkdir -p /tmp/gampan-validation
cd /tmp/gampan-validation
gampan init --network-code 0 --non-interactive --env validation
gampan bootstrap-test-network --force
```

- `init` creates `.gampan/config.yml` with placeholder network code `0`.
- `bootstrap-test-network --force` calls `makeTestNetwork`, gets the real network code, and overwrites config.yml.

**Expected output** (approximately):

```
initialized /tmp/gampan-validation/.gampan/config.yml
  native-styles/ ready
  creative-templates/ ready
✓ Test network created.
  Network code:  21700000000
  Display name:  Test Network
  UI:            https://admanager.google.com/21700000000
.gampan/config.yml updated.
```

Note the network code — you will use it in Step 8.

**If it fails**:
- `AuthError` → retry Step 2.
- `API quota exceeded` → wait a few minutes; the test network quota resets hourly.

---

## Step 4 — Import (should be empty)

```bash
gampan import
```

**Expected output**:

```
State: 0 resources tracked in .gampan/state.json
```

The test network starts empty, so nothing is imported. This confirms the import path works.

**If it fails**: Check that `config.yml` has a valid (non-zero) network code from Step 3.

---

## Step 5 — Create the sample resource files

Write three files into `/tmp/gampan-validation/native-styles/`:

### `native-styles/sample.yaml`

```yaml
# native-styles/sample.yaml
kind: NativeStyle
name: gampan-validation-sample
size:
  width: 320
  height: 250
  is_fluid: false
template_id: 10000680  # GAM's "Standard Native" template — see TBD note below
html: !file ./sample.html
css: !file ./sample.css
targeting:
  ad_units: []
  custom: {}
status: ACTIVE
```

> **TBD — template_id**: `10000680` is the ID of the "Standard Native" creative template that Google ships with every test network. If `gampan plan` or `gampan apply` returns an error like `CreativeTemplate not found`, run `gampan import --resource creative-templates` first and inspect the IDs written to `creative-templates/*.yaml` — use whichever ID corresponds to a native template.

### `native-styles/sample.html`

```html
<div class="ad">
  <h2>[%Headline%]</h2>
  <p>[%Body%]</p>
</div>
```

### `native-styles/sample.css`

```css
.ad { padding: 12px; border: 1px solid #ccc; }
```

You can create them with your editor or by pasting the blocks above directly in the shell.

---

## Step 6 — Plan (CREATE)

```bash
gampan plan
```

**Expected output**:

```
  CREATE    NativeStyle:gampan-validation-sample

CREATE: 1
UPDATE: 0
DELETE: 0
NO_CHANGE: 0
```

Exit code must be **2** (pending changes). Verify with `echo $?`.

**If it fails**:
- `SchemaError` → check YAML syntax in `sample.yaml`.
- `template_id not found` → see the TBD note above.
- Exit code 0 → the `--detailed-exitcode` flag may be off; run `gampan plan --detailed-exitcode`.

---

## Step 7 — Apply

```bash
gampan apply --auto-approve
```

**Expected output**:

```
  CREATE    NativeStyle:gampan-validation-sample

Done.
```

After this step, verify `cat .gampan/state.json` — it should contain an entry under `resources."NativeStyle:gampan-validation-sample"` with a real `gam_id` (a numeric string from GAM, not `0`).

**If it fails**:
- `Permission denied` / `PERMISSION_DENIED` → the OAuth account may not have write access; check the Ad Manager user role in the network's admin settings.
- Any other API error → the response body is logged; check for quota limits.

---

## Step 8 — Verify in UI

Open your browser to:

```
https://admanager.google.com/<network_code>/creatives#native-styles
```

replacing `<network_code>` with the value from Step 3.

Confirm that a native style named `gampan-validation-sample` appears in the list.

---

## Step 9 — Modify and re-apply

Edit `native-styles/sample.html` to change the body text, e.g.:

```html
<div class="ad">
  <h2>[%Headline%]</h2>
  <p>[%Body%] — updated by gampan</p>
</div>
```

Then:

```bash
gampan plan      # should show UPDATE
gampan apply --auto-approve
```

**Expected**: plan shows `UPDATE NativeStyle:gampan-validation-sample`, apply succeeds.

---

## Step 10 — Drift recovery

1. In the GAM UI (<https://admanager.google.com/>), open the native style and manually change the CSS snippet (add a comment or change a color).
2. Save the change in the UI.
3. Run:

```bash
gampan plan
```

**Expected**: plan shows an UPDATE (the remote checksum diverged from state.json).

4. Run:

```bash
gampan refresh
```

**Expected output**:

```
Drift detected (remote changed since last apply):
  NativeStyle:gampan-validation-sample
```

`refresh` re-syncs `state.json`'s remote checksum without touching your YAML. This makes `plan` aware that the remote is ahead and lets you decide whether to re-apply your YAML (push your desired state back) or update your YAML to match the remote.

---

## Step 11 — Record cassettes

With the live session done, replay the same flow while recording VCR cassettes so the test suite can run offline:

```bash
cd /tmp/gampan-validation
VCR_RECORD=once bash /path/to/gampan/scripts/record_cassettes.sh
```

See `scripts/record_cassettes.sh` for the exact command. Cassettes will be written to `tests/integration/cassettes/` inside the gampan repo.

> The recording script must be run from the gampan **source repo root**, not from `/tmp/gampan-validation`. The cassette paths are relative to the repo.

---

## Step 12 — Commit cassettes

```bash
cd /path/to/gampan
git add tests/integration/cassettes/
git commit -m "test(integration): add v0.1 validation cassettes"
```

After committing, run:

```bash
make validate
```

All four integration tests should pass (no longer skipped). This is the offline proof that the flow works.

---

## Appendix: expected cassette filenames

| Test | Cassette file |
|---|---|
| `test_import_native_styles` | `tests/integration/cassettes/test_import_native_styles.yaml` |
| `test_e2e_import_after_apply_records_state` | `tests/integration/cassettes/test_e2e_import_after_apply_records_state.yaml` |
| `test_e2e_plan_create` | `tests/integration/cassettes/test_e2e_plan_create.yaml` |
| `test_e2e_apply_update_then_refresh` | `tests/integration/cassettes/test_e2e_apply_update_then_refresh.yaml` |
