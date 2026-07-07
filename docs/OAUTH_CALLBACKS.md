# Social Accounts — OAuth Callback URLs

The **Social Accounts** module connects one account per platform per user via
OAuth 2.0. Every provider redirects back to a **fixed, stable callback URL** on
this backend. Register these exact URLs in each developer portal — they never
change and require no modification.

## Callback URLs to register

Local development (`BACKEND_URL=http://localhost:8000`):

| Platform  | Callback URL (Redirect URI)                          | Portal |
|-----------|------------------------------------------------------|--------|
| Facebook  | `http://localhost:8000/api/auth/facebook/callback`   | https://developers.facebook.com |
| Instagram | `http://localhost:8000/api/auth/instagram/callback`  | https://developers.facebook.com |
| LinkedIn  | `http://localhost:8000/api/auth/linkedin/callback`   | https://developer.linkedin.com |
| X (Twitter) | `http://localhost:8000/api/auth/x/callback`        | https://developer.x.com |
| Pinterest | `http://localhost:8000/api/auth/pinterest/callback`  | https://developers.pinterest.com |
| Threads   | `http://localhost:8000/api/auth/threads/callback`    | https://developers.facebook.com |

In production, set `BACKEND_URL=https://your-domain.com` and register the same
paths on that host, e.g. `https://your-domain.com/api/auth/x/callback`. The URL
is always `{BACKEND_URL}/api/auth/{platform}/callback`.

> Note: X (Twitter) uses the public slug **`x`** in the callback path, while the
> app refers to it internally as `twitter`. Register `/api/auth/x/callback`.

## Environment variables

Add credentials to `.env` (see `.env.example`). A platform with no credentials
returns a clear error on Connect — there is **no simulated/mock connect**; every
account is connected through real OAuth.

```dotenv
# Public base URL of THIS backend — callback URLs derive from it.
BACKEND_URL=http://localhost:8000

# Facebook + Instagram share the Meta app credentials (see Meta OAuth Setup).
META_APP_ID=
META_APP_SECRET=

# Other platforms: one client id/secret pair each.
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
X_CLIENT_ID=
X_CLIENT_SECRET=
PINTEREST_CLIENT_ID=
PINTEREST_CLIENT_SECRET=
THREADS_CLIENT_ID=
THREADS_CLIENT_SECRET=
```

## OAuth scopes requested

| Platform  | Scopes |
|-----------|--------|
| Facebook  | `public_profile`, `email`, `pages_show_list`, `pages_manage_posts` |
| Instagram | `instagram_business_basic`, `instagram_business_content_publish` |
| LinkedIn  | `openid`, `profile`, `email`, `w_member_social` |
| X (Twitter) | `tweet.read`, `tweet.write`, `users.read`, `offline.access` (PKCE) |
| Pinterest | `user_accounts:read`, `boards:read`, `pins:read`, `pins:write` |
| Threads   | `threads_basic`, `threads_content_publish` |

## How the flow works

1. **Start** — the frontend calls `POST /api/social/{platform}/connect`. If the
   platform is configured, the response contains an `authorize_url`; the SPA
   redirects the browser there. (X uses PKCE; the code verifier is carried in a
   signed, short-lived `state` token, so no server session is needed.)
2. **Consent** — the user approves on the provider, which redirects to
   `GET /api/auth/{platform}/callback?code=...&state=...`.
3. **Exchange** — the backend verifies `state` (identifying the user and
   guarding CSRF), swaps the `code` for tokens (Instagram/Threads additionally
   exchange for a long-lived token), fetches the profile, and upserts the
   account. Tokens are stored server-side and **never** returned by the API.
4. **Return** — the browser is bounced back to `/accounts?connected={platform}`
   (or `?error=...`) so the UI can show a toast.

## Management API

| Method & path | Purpose |
|---|---|
| `GET /api/social/accounts` | Overview: connected accounts + per-platform summary |
| `GET /api/social/{platform}` | One connected account (404 if none) |
| `POST /api/social/{platform}/connect` | Begin connect (returns `authorize_url`) |
| `DELETE /api/social/{platform}` | Disconnect and delete stored credentials |
| `POST /api/social/{platform}/refresh` | Refresh tokens / re-sync |

`{platform}` here is the internal key (`instagram`, `facebook`, `twitter`,
`linkedin`, `threads`, `pinterest`). Only the OAuth **callback** uses the `x`
slug for Twitter.

---

# Meta OAuth Setup

Facebook and Instagram are both connected through a single **Meta app**. This
section is the complete, step-by-step setup.

## 1. Required Meta products

In the [Meta Developer Portal](https://developers.facebook.com) create an app
(type **Business**) and add these products:

| Product | Used for |
|---|---|
| **Facebook Login** (or *Facebook Login for Business*) | Connecting a Facebook account + its Pages, and Instagram via those Pages |
| **Instagram Graph API** (Instagram product) | Reading/publishing to the linked Instagram Business account |

Both Facebook and Instagram authenticate through the **official Facebook Login**
dialog and the single **Meta app** (`META_APP_ID` / `META_APP_SECRET`) — the same
model Buffer/Hootsuite/Later use. They are still **separate connections** in the
UI (separate Connect buttons); connecting Instagram never marks Facebook as
connected.

On **Connect Instagram**:

- The user logs in with **Facebook** (fresh login forced via
  `auth_type=reauthenticate`) and grants Pages access.
- The app lists **every** Instagram Business account linked to a granted Page.
  - **0** → clear error, nothing connected.
  - **1** → connected automatically.
  - **many** → the user **picks one**; only that account is stored.
- **Business/Creator accounts only** (they must be linked to a Facebook Page).
- There is **no simulated/mock connect** and no hard-coded token anywhere.

## 2. Required permissions / scopes

Requested automatically by the app during the OAuth redirect — you only need to
add them to the app's permission list and (for production) submit them for App
Review.

**Facebook** (`/api/auth/facebook/callback`)
- `public_profile`
- `email`
- `pages_show_list`
- `pages_manage_posts`

**Instagram** (`/api/auth/instagram/callback`) — granted through Facebook Login
- `instagram_basic`
- `instagram_content_publish`
- `instagram_manage_insights`
- `pages_show_list`
- `pages_read_engagement`
- `business_management`

While the app is in **Development mode** these work for users with a **role** on
the app (Admin/Developer/Tester) without App Review. Add your test users under
*App Roles → Roles*.

## 3. Callback URLs to register

Add these **exact** Valid OAuth Redirect URIs.

- Facebook → *Facebook Login → Settings → Valid OAuth Redirect URIs*:
  ```
  http://localhost:8000/api/auth/facebook/callback
  ```
- Instagram (authorizes via the same Facebook Login dialog) — add to *Facebook
  Login → Settings → Valid OAuth Redirect URIs*:
  ```
  http://localhost:8000/api/auth/instagram/callback
  ```

For production, swap the host (e.g. `https://your-domain.com/...`) and add those
too. HTTPS is required by Meta for non-localhost URLs.

## 4. Where to place App ID and App Secret

Copy them from *App → Settings → Basic* into **`.env`** (never commit real
secrets — `.env` is git-ignored):

```dotenv
# Facebook — from App > Settings > Basic
META_APP_ID=1604802984403205
META_APP_SECRET=<your app secret>
META_GRAPH_VERSION=v21.0
META_REDIRECT_URI=http://localhost:8000/api/auth/facebook/callback

# Instagram uses the SAME Meta app — only its redirect URI is separate.
INSTAGRAM_REDIRECT_URI=http://localhost:8000/api/auth/instagram/callback
```

The app reads all of these from the environment — nothing is hardcoded. Both
Facebook and Instagram use `META_APP_ID` / `META_APP_SECRET`. There is no
personal access token and no simulated connect — every account is connected
per-user via real OAuth. Restart the backend after editing `.env`.

## 5. How to test Facebook login

1. Put `META_APP_ID` / `META_APP_SECRET` in `.env` and restart the backend.
2. Open the app → **Social Accounts** → click **Connect** on the Facebook card.
3. You're redirected to `https://www.facebook.com/v21.0/dialog/oauth?...` — log
   in and approve the permissions.
4. Facebook redirects to `/api/auth/facebook/callback`, which exchanges the
   code for a token, fetches your profile, stores the account, and bounces you
   back to `/accounts?connected=facebook` with a success toast.
5. The card now shows **Connected**, your name, and the last sync time.

Backend logs for each step:
```
OAuth callback: exchanging code for facebook (user N)
Connected facebook account @<name> (user N), token expires in <s>s
```

## 6. How to test Instagram login

1. Add the **Instagram Graph API** product to the same Meta app. No extra
   credentials — Instagram uses `META_APP_ID` / `META_APP_SECRET`. Register the
   Instagram callback URL (step 3). Restart the backend.
2. Your Instagram account must be **Professional** (Business/Creator) **and
   linked to a Facebook Page** you manage.
3. **Social Accounts → Connect** on the Instagram card → you're sent to the
   **Facebook** login dialog (forced fresh login); grant the account/Pages →
   approve.
4. The callback exchanges the code, upgrades to a **long-lived** token (~60
   days), and lists every Instagram Business account linked to a granted Page:
   - none → clear error, nothing connected;
   - one → connected automatically;
   - several → a picker appears; **choose one**, only it is stored.
5. The card shows **Connected** with your `@username`, profile picture, and
   connected date. Facebook stays a **separate** card (Not Connected unless you
   connect it too).

## 7. Additional required steps (checklist)

- [ ] App created (Business type) in the Meta Developer Portal.
- [ ] Facebook Login + Instagram products added.
- [ ] Both callback URLs registered exactly as above.
- [ ] `META_APP_ID` / `META_APP_SECRET` in `.env`; backend restarted.
- [ ] Test users given an app **role** (dev mode) — or the app submitted for
      **App Review** with the scopes above (production).
- [ ] Instagram account is Professional (Business/Creator) and linked to a
      Facebook Page.
- [ ] For production: app switched to **Live** mode, HTTPS callback URLs added,
      a Privacy Policy URL set in *Settings → Basic*.
- [ ] **Rotate the App Secret** if it was ever shared in plaintext.

## Security notes

- Access/refresh tokens are stored server-side and **never** returned by the
  API (`SocialAccountRead` omits them). The connect flow only takes secrets in.
- The OAuth `state` is a signed, short-lived JWT carrying the user id (and PKCE
  verifier where used), so the public callback can't be forged or replayed —
  built-in CSRF protection.
- Tokens are currently stored in plaintext in the DB. For production, encrypt
  `access_token` / `refresh_token` at rest (Fernet or a KMS) — a marked
  follow-up in `models/social_account.py`.
