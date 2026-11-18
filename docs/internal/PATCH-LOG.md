# Patch log

Real changes taken from the git history of this repository and from the current
worktree. No CVE is invented: `—` means the change was not driven by a CVE.

| Date (UTC) | What | Commit | Test / evidence |
| --- | --- | --- | --- |
| 2026-11-18 | Require an account to use the app (no guest, no demo) | `71a3a5a` | `tests/test_auth_gate.py` |
| 2026-11-18 | Pin the no-guest contract with a regression suite | `1bb6cc3` | `tests/test_auth_gate.py` |
| 2026-11-18 | Hide the app shell behind the login overlay | `05ba487` | `tests/test_auth_gate.py` |
| 2026-11-18 | Fix the app shell nested inside the hidden limit modal | `7327d92` | `tests/test_auth_gate.py` |
| 2026-11-18 | Keep-alive with bounded idle time and request caps | `68a7193` | `tests/test_keepalive.py` |
| 2026-11-18 | Add the keep-alive regression suite | `a376f0b` | `tests/test_keepalive.py` |
| 2026-11-18 | Remove the purchase and redemption flow | `9f6bcc4` | `tests/test_no_purchase.py` |
| 2026-11-18 | Add TOTP MFA: enrolment, login ticket, one-use recovery codes, disable | worktree (this change) | `tests/test_mfa.py` (31 checks, exit 0) |
| 2026-11-18 | Add the encrypted backup and verification scripts | worktree (this change) | `tools/backup_offsite.sh` → `tools/backup_verify.sh` PASS (output in `isms/06-BACKUP-RESTORE.md §4.1`) |
| 2026-11-18 | Add the quarterly access-review tool and procedure | worktree (this change) | `python3 tools/access_review.py`, first run 2026-11-18 in `isms/03-ACCESS-CONTROL.md §7` |
| 2026-11-18 | Add the release gate and this SDLC/patch-log pair | worktree (this change) | `bash tools/preflight.sh` (see `docs/internal/SDLC.md §2`) |
| 2026-11-18 | Verify private modes under `data/` | worktree (this change) | `bash tools/check_perms.sh` → exit 0 |

## How to add a row

1. Open the row the moment a defect, audit finding or CVE notice is identified.
2. Fill the commit only after it exists; use `worktree (this change)` until then.
3. The last column must point to a runnable test or a recorded command, not to an
   opinion. If a regression test is not possible, say so in the row.
