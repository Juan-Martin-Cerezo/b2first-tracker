# Secure Development Life Cycle (SDLC)

Scope: the single-process, stdlib-only `b2first-tracker` service and the one-person
organisation that operates it. This policy is deliberately small enough to be followed
by one person; it does not claim review by someone else.

## 1. One change, one branch

- Every change starts on its own git branch, named by intent
  (`feat/...`, `fix/...`, `test/...`, `docs/...`).
- The change is committed with a conventional-commit message that says what changed and
  why. `main` is only updated from a branch that passed the gate below.
- Secrets and data never enter git: `data/`, `*.key`, `*.crt` stay in `.gitignore`.

## 2. Verification is mandatory before deploy

No change is deployed until `bash tools/preflight.sh` exits 0. The gate runs, in order
and stopping at the first failure:

| Step | Check | Why |
| --- | --- | --- |
| 1 | `python3 -m py_compile server.py mfa.py` | the process must start |
| 2 | JavaScript syntax of the two inline `<script>` blocks | a broken bundle is a blank app |
| 3 | zero inline `on*=` handlers | CSP/XSS posture (R02/R03) |
| 4 | zero purchase/redemption strings in `index.html`, `landing.html` | the service must not sell or redeem |
| 5 | core regression suites (`B2_PREFLIGHT_SUITES`) | login gate, MFA, spike/NAT, security, multi-user |
| 6 | `tools/pentest.py --spawn` | headers, IDOR, brute force, body caps, traversal |

Additional suites are run when the change touches them (speaking, plan, progress), but
the six steps above are the minimum for every release.

## 3. What counts as evidence

A control or a fix is only "done" when there is an artefact that can be executed or
opened, and the artefact's output is recorded. Acceptable evidence:

- a test that fails before the change and passes after it;
- a script whose exit code proves the property (`tools/preflight.sh`,
  `tools/backup_verify.sh`, `tools/check_perms.sh`, `tools/verify_audit.py`,
  `tools/restore_drill.sh`, `tools/pentest.py`);
- a recorded command and its verbatim output in the ISMS documents.

Prose alone is not evidence. Any ISMS row that cites only a paragraph stays `Parcial`
or `Gap` (see `docs/internal/isms/07-ANNEX-A-MAPPING.md`).

## 4. Patch procedure

1. **Identify** — a failing test, an audit finding, a dependency/CVE notice, or an
   incident. Record it in `docs/internal/PATCH-LOG.md` as soon as it is known.
2. **Correct** — the smallest change that removes the cause, on a branch.
3. **Regression test** — a test that would have caught the issue. If a test is
   impossible, say why in the patch-log row instead of pretending.
4. **Gate** — `bash tools/preflight.sh` must pass.
5. **Deploy** — restart the service only after the gate; verify `/api/health` and the
   affected feature.
6. **Record** — add the date, the change, the commit and the test to
   `docs/internal/PATCH-LOG.md`. No invented CVE identifiers: if there is no CVE, write
   `—`.

## 5. Rollback

A branch that fails the gate is not deployed. A deployed change that breaks the service
is reverted with `git revert <commit>` and redeployed through the same gate; data is
restored only through `docs/internal/isms/06-BACKUP-RESTORE.md` and never by editing
`data/` by hand.

## 6. Known limits

- There is no CI service in the repository: the gate is run by the operator on the
  host. A8.29 stays `Parcial` for that reason.
- There is no independent review or approval: the same person writes and approves.
  A8.32 stays `Parcial` until a deployment record with a separate approval exists.
