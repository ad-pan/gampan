# OAuth Client Setup for gampan

## Why this document exists

`gampan` ships with placeholder OAuth credentials (`TODO_REGISTER_OAUTH_CLIENT...`).
Until those placeholders are replaced with a real registered client, `gampan auth login`
exits with an error pointing here.

This is intentional: per **RFC 8252 §8.5**, the `client_secret` for an installed/desktop
OAuth app is **not actually secret** — it is distributed with the app binary and the spec
explicitly acknowledges this. Mainstream CLIs (`gcloud`, `gh`, `firebase`, `rclone`) all
ship their own OAuth client. `gampan` follows the same pattern. The placeholders simply
mark the fact that no client has been registered yet — they need to be replaced once in
source code before the tool is usable.

Enterprise users who want their own client for audit reasons can skip source changes
entirely by setting `GAMPAN_OAUTH_CLIENT_ID` and `GAMPAN_OAUTH_CLIENT_SECRET` env vars.

---

## Steps to register the OAuth client

### 1. Open Google Cloud Console

Go to <https://console.cloud.google.com>. Select an existing project or create a new one.
Suggested project name: **`ad-pan`**.

### 2. Enable the Google Ad Manager API

Navigate to **APIs & Services → Library**, search for **"Google Ad Manager API"**, and
click **Enable**.

### 3. Configure the OAuth consent screen

Navigate to **APIs & Services → OAuth consent screen**.

- **User type**: External (unless the account is part of a Google Workspace org that
  owns the GCP project, in which case Internal is also fine).
- **App name**: `gampan` (or `ad-pan`).
- **Support email** and **Developer contact email**: your own.
- **Scopes**: add three:
  - `https://www.googleapis.com/auth/admanager` — Google Ad Manager API.
  - `openid` — required for identity.
  - `https://www.googleapis.com/auth/userinfo.email` — so `gampan` can display the logged-in user's email.

  _Note: the legacy GAM scope `.../auth/dfp` is replaced server-side with `admanager` and oauthlib will reject the mismatch — request `admanager` directly._
- **Test users**: add your own Google account.
- Publishing status: leave as **Testing** for v0.1. Only switch to **In production** if
  you plan to distribute gampan to users outside your Google Workspace.

### 4. Create the OAuth client ID

Navigate to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.

- **Application type**: **Desktop app**
- **Name**: `gampan CLI`

Click **Create**. A modal shows your `client_id` and `client_secret` — copy both.

### 5. Replace the placeholder constants in source

Open `src/gampan/gam/oauth.py` and replace:

```python
_DEFAULT_CLIENT_ID = "TODO_REGISTER_OAUTH_CLIENT.apps.googleusercontent.com"
_DEFAULT_CLIENT_SECRET = "TODO_REGISTER_OAUTH_CLIENT_SECRET"  # noqa: S105
```

with the values from the modal:

```python
_DEFAULT_CLIENT_ID = "<your_client_id>.apps.googleusercontent.com"
_DEFAULT_CLIENT_SECRET = "<your_client_secret>"  # noqa: S105
```

### 6. Commit

```bash
git add src/gampan/gam/oauth.py
git commit -m "feat(oauth): register gampan OAuth client"
```

---

## Enterprise / fork override via environment variables

If you do not want to modify source code (e.g. you are running a private fork with your
own audit requirements), export the following before running `gampan`:

```bash
export GAMPAN_OAUTH_CLIENT_ID="<your_client_id>.apps.googleusercontent.com"
export GAMPAN_OAUTH_CLIENT_SECRET="<your_client_secret>"
```

The env vars take precedence over the baked-in defaults and the placeholder guard is
bypassed automatically.
