# Phase 30 — Bring your own key (writing + speaking)

## Goal
Let a user paste **their own** provider key and have writing corrections and the
speaking examiner run on their key, at their cost. The owner's key stays the
default for accounts that do not provide one.

Owner instruction (verbatim): "Para el writing podemos hacer que el usuario use
CUALQUIER API key? ... que pueda poner su clave".

## Hard rules — these are security requirements, not suggestions
1. **The user's key must never touch disk on the server.** Not `data/`, not a log,
   not the audit chain, not an error string, not a traceback. It lives in memory
   for the duration of one request.
2. It must never appear in the response body returned to the client.
3. `logging`, `print`, exception messages and `repr(request)` are forbidden around
   it. Use an explicit allow-list when logging headers.
4. Code, comments, commits: English. Stdlib only.

## Protocol
- Request header `X-Provider-Key: <key>` (optional).
- Request header `X-Provider-Base: <https url>` (optional, default per provider).
- Request header `X-Provider-Model: <model id>` (optional).
- **Supported shape (v1): OpenAI-compatible** `POST {base}/chat/completions` with
  `Authorization: Bearer <key>`. That covers DeepSeek, OpenAI, Groq, Together,
  OpenRouter, Mistral, xAI, Fireworks with one adapter.
- `X-Provider-Base` must be validated: `https://` only, no IP literals, no
  `localhost`, no private ranges, no port other than 443. Refusing these is what
  stops the endpoint from becoming an SSRF gadget.
- If `X-Provider-Key` is absent → today's behaviour (owner key + quotas).

## Server work (`server.py`)
1. Parse and validate the three headers. Reject a bad base with `400` and a
   message that does not echo the value.
2. Refactor the outbound call into one function that takes (base, key, model,
   payload) so the owner-key path and the BYO path share sanitising, timeouts,
   size limits and output guards. The BYO path must keep **every** guard the
   owner path has.
3. Timeout 20 s, max response 256 KB, no redirects.
4. With a user key: **skip the daily quota** (their cost, their limit) but keep
   the per-IP rate limit, and cap at 120 requests/hour/account.
5. Add `GET /api/ai/provider/test` (POST) that sends a 1-token request and returns
   `{ok, model}` or `{ok:false, code}` — never the key, never the provider body.

## Client work (`index.html`)
1. Settings → **AI provider** block: provider select (DeepSeek / OpenAI / Groq /
   OpenRouter / Custom), key input `type="password"` with a show/hide toggle,
   optional base URL and model fields.
2. Stored in `D.settings.byo` inside the user's own progress document? **No** —
   progress syncs to the server. Store it in `localStorage` under
   `b2first_byo_<userId>` and **exclude it from `save()`/sync**. Add a comment
   saying why.
3. "Test connection" button → `POST /api/ai/provider/test`.
4. When a key is set, the AI panel shows a small badge "using your key" and the
   quota counter hides.
5. Clear-key button that wipes it from `localStorage`.

## Acceptance (write `tests/test_byokey.py`)
Live service, `tests/helpers.py`, plus a local stub provider (reuse the pattern in
`tests/test_speaking_pa.py`):
- Without headers → owner path, quota applies (2nd call within the limit works,
  counter increments).
- With a stub key + stub base → the stub receives `Authorization: Bearer <key>`,
  and the response is returned.
- With a stub key → **no quota consumption** (the daily counter does not move).
- `X-Provider-Base: http://127.0.0.1:9999` → `400`. Same for `https://10.0.0.5`,
  `https://localhost`, `http://api.example.com` (not https), `https://x:8443`.
- **Leak test (the important one):** after a request carrying a sentinel key
  (`KEY_SENTINEL_<random>`), grep the whole `data/` tree, the access log, the
  audit log and the last 200 journal lines: zero occurrences. Then trigger a
  provider error (stub returns 500) and assert the sentinel is **still** absent
  from the error response and the logs.
- The key is absent from `GET /api/progress` and from the export endpoint.

## Verify before finishing
```
cd tests && uv run --with playwright --with httpx python test_byokey.py  # exit 0
cd tests && uv run --with playwright python test_final.py                # green
bash tools/audit.sh                                                      # 39/39
```
Finish with `VERDICT: ok` only if all three pass, and state explicitly in the
verdict that the leak test ran against a live request.
