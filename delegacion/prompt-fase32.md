# Phase 32 — Data security, privacy policy and terms

## Goal
The product now stores accounts, progress, audit events, plans and (never) keys.
Make the data handling defensible and publish honest documents: a privacy policy,
terms of use, and a security page — all served from the app, not just markdown in
the repo.

Owner instruction (verbatim): "Asegurá la seguridad de todos los datos, actualiza
documentos, politicas y terminos."

## Part A — Data security (code first, documents after)
Write `docs/DATA-MAP.md` and make the code match it.

| Store | Path | Contents | Protection |
| --- | --- | --- | --- |
| accounts | `data/users.json` | name, salt, hash (PBKDF2 600k), color | `0600` |
| sessions | `data/tokens.json` | `sha256(token)` → user, exp | `0600` |
| progress | `data/users/<id>/progress.json` | practice log, profile | `0700`/`0600` |
| backups | `data/users/<id>/backups/` | last 20 progress docs | `0700` |
| audit | `data/audit.log` | security events, hash chain | `0600`, rotates 5 MB |
| usage | `data/usage.json` | counters per account | `0600` |
| licenses | `data/licenses.json` | `sha256(code)` | `0600` |

Rules to verify and enforce:
1. **Nothing sensitive in logs.** Access log: method, path, status, ms,
   `request_id`, and a **hashed** client identifier (sha256 of IP truncated to 12
   chars) — never the raw IP, never a token, never a body. Sweep every `print()`
   and `logging` call in `server.py` and fix the leaks.
2. **Retention.** Audit log 90 days, usage counters 13 months, backups 20
   versions. Add `tools/retention.py` (stdlib) that enforces this and is safe to
   run from cron; it must be idempotent and print what it deleted.
3. **Deletion is complete.** `DELETE /api/account` must remove the user record,
   every token, the progress directory including backups, usage and license rows,
   and append a final audit event mentioning it **without** personal data. Verify
   by grepping the whole `data/` tree afterwards.
4. **Export is complete.** `GET /api/export` returns everything the account owns in
   one JSON file (progress, audit events, plan, usage) — GDPR-style portability.
5. **Passwords**: reject the top-1000 common passwords, keep the existing 600k
   PBKDF2, force a re-hash when `iters` is below the current constant.
6. **No PII in `data/` beyond what is needed**: no email, no IP, no user agent
   (the current `ua_hash` is fine).
7. Run `tools/verify_audit.py` in the acceptance and paste the output.

## Part B — Documents
Create in the repo and serve at the app routes:

- `docs/PRIVACY.md` → `GET /privacy`
- `docs/TERMS.md` → `GET /terms`
- `docs/SECURITY.md` → `GET /security` (policy + disclosure, links `security.txt`)

Requirements for the text:
- **Honest and specific**: name the third parties that actually receive data —
  Cloudflare (TLS terminates at the edge, sees requests in plaintext), Google
  Gemini (speaking audio, and whether the free tier trains on it), DeepSeek
  (writing text), Azure (only if the user configures pronunciation). Say what is
  **not** stored: audio is never written to disk.
- **What is stored**: account name, password hash, progress, plan, usage counters,
  audit events. Where: this Raspberry Pi, in Argentina. No database.
- **User rights**: export, delete account, clear BYO key, all self-service, with
  the exact menu paths.
- **Age**: the product targets 16+, states it, and says that users under 18 need
  permission from a parent or guardian.
- **No selling data, no advertising, no tracking pixels.** If analytics exist,
  name them.
- **Terms**: no guarantee of a Cambridge score, fair-use limits, the user is
  responsible for their own provider key and its costs, the owner may change
  limits with notice, the service is provided as is.
- **Version and date** at the top of each document, and a changelog line.

## Part C — Serving them
3. Render the three markdown files with a tiny stdlib renderer (headings,
   paragraphs, lists, links, tables, code) — no dependency, no template engine.
   Sanitise all HTML (those files are trusted, but the renderer must still escape
   any `<` it does not generate).
4. Link them from the footer (currently only Privacy) and from the signup screen
   with "By creating an account you accept the Terms and the Privacy Policy".
5. They must be reachable **without** a session and must be cacheable for 5 min.

## Acceptance (write `tests/test_legal.py` + extend others)
- `GET /privacy`, `/terms`, `/security` → 200, `text/html`, and each contains its
  version line and a "Last updated" date.
- Each names Cloudflare and Google; privacy names DeepSeek; privacy says audio is
  not stored.
- The signup screen shows the acceptance line with both links working.
- `tools/retention.py` deletes a planted 100-day-old audit line and a 21st backup,
  and does nothing on a second run (idempotent).
- After `DELETE /api/account` for a throwaway user: `data/users/<id>` gone, no
  token, no usage row, no license row; a grep of `data/` for that user id returns
  **only** the final audit line (which must not contain the name).
- `tools/verify_audit.py` exits 0.
- Access log lines contain no raw IP (assert the `request_id` line format) and no
  token substring after a logged-in request.

## Verify before finishing
```
cd tests && uv run --with httpx python test_legal.py         # exit 0
cd tests && uv run --with playwright python test_final.py    # green
cd tests && uv run --with playwright python test_plans.py    # green
sudo bash tools/audit-host.sh                                # 55/55 unchanged
```
Finish with `VERDICT: ok` only if all four pass. In the verdict, list any claim in
the documents you could **not** verify from the code, so nothing published is
wishful.
