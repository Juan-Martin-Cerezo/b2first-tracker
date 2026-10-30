# Phase 34 — Google sign-in and passkeys (more ways to log in)

## Goal
Today the only way in is username + password. Add two more, without adding a
dependency and without an email flow (the app stores no email on purpose):

1. **Sign in with Google** (OAuth 2.0 authorization-code + PKCE, no client secret
   leak in the browser, no SDK).
2. **Passkeys** (WebAuthn) as a second factor *and* as a standalone sign-in for
   returning devices.

Owner instruction (verbatim): "Esta lo del login seguro y login con google y varios
medios?"

## Constraints
- Stdlib only on the server. WebAuthn needs CBOR decoding and COSE key parsing:
  write a small `webauthn.py` (~250 lines, decode-only, no encoding library) and
  test it against fixed vectors. If a vector cannot be produced offline, generate
  it with Playwright's virtual authenticator and store the bytes in the test.
- No new third-party runtime. Google is spoken to with `urllib.request`.
- The Google path must never create an account silently: first Google sign-in
  either links to an existing account by an explicit confirmation screen, or
  creates one with a generated local username the user can rename.
- **No email storage** unless the user opts in on that screen; if they do, store it
  hashed + note it in the privacy policy (phase 32 must be updated).

## Google sign-in
1. `GET /api/auth/google/start` → 302 to Google with `state` (random, stored
   server-side for 5 min, single use), `code_challenge` (S256), scope
   `openid email profile`.
2. `GET /api/auth/google/callback` → verify state, exchange code at
   `https://oauth2.googleapis.com/token`, read the id_token **and verify**:
   signature against Google's JWKS (RS256 — implement with `hashlib`+`hmac`? RSA
   verify needs modular exponentiation: `pow()` is enough), `iss`, `aud`, `exp`,
   `nonce`. Refuse anything else. No JWT library.
3. Map `sub` → local account (`data/oauth.json`, `0600`, `{sub: user_id}`).
4. Success → same session token shape as the password flow, redirect to `/`.

## Passkeys
1. `POST /api/webauthn/register/begin` + `/finish` (authenticated, requires the
   password once).
2. `POST /api/webauthn/login/begin` + `/finish` (unauthenticated, discoverable
   credentials, `userVerification: preferred`).
3. Store `{credential_id, public_key_cose, sign_count, created, label}` in
   `data/webauthn/<user_id>.json` (`0600`). Reject a signature counter that goes
   backwards.
4. RP ID from `B2_RP_ID` (default `firsttracker.app`), origin from `B2_PUBLIC_URL`.

## Client work
1. Login screen: "Continue with Google" (only if `B2_GOOGLE_CLIENT_ID` is set, via
   `/api/config`) and "Sign in with a passkey".
2. Settings → Security: "Add a passkey" (with device label), list of passkeys with
   "Remove", and a warning if the account has no password as a fallback.
3. All new visible strings go through `I18N` in **both** languages — this phase
   must not add a single hardcoded string (see phase 32's scan).

## Acceptance (write `tests/test_auth_methods.py`)
- Google: with a stubbed token endpoint + a locally generated RSA key, a valid
  id_token signs in; a tampered signature, wrong `aud`, wrong `iss`, expired
  `exp` and reused `state` are each rejected with `400`.
- Passkeys: Playwright's CDP virtual authenticator registers a credential, then a
  fresh browser context signs in with it; a bumped-down sign counter is rejected.
- Password login still works and still revokes sessions on change.
- No secret in logs: the `code`, the `id_token` and the client secret never appear
  in `data/`, the journal, or the audit log.
- i18n: zero new hardcoded strings (grep the diff for text nodes without
  `data-i18n`).

## Verify before finishing
```
cd tests && uv run --with playwright python test_auth_methods.py  # exit 0
cd tests && uv run --with playwright python test_final.py         # green
cd tests && uv run --with httpx python test_legal.py              # green
```
Finish with `VERDICT: ok` only if all three pass. If Google credentials are absent,
the Google suite must skip loudly (print `SKIP: no client id`) rather than pass.
