"""Phase 32 acceptance: legal pages, data security, retention, deletion, export.

Boots its own server with a temporary DATA_DIR, so it never touches real data/.
Runs with plain HTTP (no browser): the signup acceptance line is checked in the
served HTML and in both dictionaries, and its two links are fetched for real.

    cd tests && uv run --with httpx python test_legal.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import httpx

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_tmp = tempfile.mkdtemp(prefix="b2legal-")
os.environ["DATA_DIR"] = _tmp
os.environ["B2_DEMO"] = "0"
os.environ["B2_REGISTER"] = "open"

import server as S  # noqa: E402
import store  # noqa: E402
import legal  # noqa: E402

S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.B2_DEMO = False
S.B2_REGISTER = "open"

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
URL = f"http://127.0.0.1:{srv.server_address[1]}"
threading.Thread(target=srv.serve_forever, daemon=True).start()

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else ("FAIL " + (detail or name))
    if not cond:
        failed.append(name)


def req(method, path, body=None, token=None):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    kwargs = {"headers": headers, "timeout": 30}
    if body is not None:
        kwargs["json"] = body
    return httpx.request(method, URL + path, **kwargs)


def read_tree(root):
    """Yield (path, text) for every readable file under root (skip binaries)."""
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    yield path, handle.read()
            except (OSError, UnicodeDecodeError):
                continue


# ---------------------------------------------------------------------------
# 0. The Markdown renderer never turns source text into live markup.
# ---------------------------------------------------------------------------
sample = legal.render_markdown(
    "# Title\n\nA <script>alert(1)</script> tag.\n\n"
    "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"
    "[ok](https://example.com) [bad](javascript:alert(1))\n"
)
check("L0_renderer_sanitises",
      "&lt;script&gt;" in sample and "<script>" not in sample
      and "<table>" in sample and 'href="https://example.com"' in sample
      and 'href="#"' in sample)


# ---------------------------------------------------------------------------
# 1. The three legal pages are public, HTML and cacheable.
# ---------------------------------------------------------------------------
privacy = req("GET", "/privacy")
terms = req("GET", "/terms")
security = req("GET", "/security")
check("L1_status_html",
      all(r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
          for r in (privacy, terms, security)),
      f"{[r.status_code for r in (privacy, terms, security)]}")
check("L2_cache_5_min",
      all("max-age=300" in r.headers.get("cache-control", "")
          for r in (privacy, terms, security)),
      str([r.headers.get("cache-control") for r in (privacy, terms, security)]))
for label, r in (("privacy", privacy), ("terms", terms), ("security", security)):
    body = r.text
    check(f"L3_{label}_version",
          "Version 1.0" in body and "Last updated: 2026-10-30" in body,
          body[:120])
    check(f"L4_{label}_names_cloudflare_google",
          "Cloudflare" in body and "Google" in body)

pbody = privacy.text
check("L5_privacy_deepseek", "DeepSeek" in pbody)
check("L6_privacy_audio_not_stored",
      "audio is never written to disk" in pbody.lower()
      and "never stored" in pbody.lower())
check("L7_privacy_no_placeholder", "TODO_OWNER_EMAIL" not in pbody)
check("L8_security_links_security_txt",
      "/.well-known/security.txt" in security.text
      and req("GET", "/.well-known/security.txt").status_code == 200)

# ---------------------------------------------------------------------------
# 2. Footer and signup accept both documents.
# ---------------------------------------------------------------------------
index = req("GET", "/").text
check("L9_footer_links",
      all(f'href="{h}"' in index for h in ("/privacy", "/terms", "/security")))
check("L10_signup_acceptance",
      'data-i18n-html="auth_privacy_html"' in index
      and "you accept the" in index and "Terms" in index
      and "Términos" in index and "/terms" in index and "/privacy" in index)
check("L11_signup_links_resolve",
      terms.status_code == 200 and privacy.status_code == 200)

# ---------------------------------------------------------------------------
# 3. A logged-in request produces an access line with no raw IP and no token.
# ---------------------------------------------------------------------------
cap = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
_real_stdout = sys.stdout
sys.stdout = cap

name = "Legal Throwaway 8f3c"
password = "legal-throwaway-9!"
reg = req("POST", "/api/register", {"name": name, "password": password})
check("S1_register", reg.status_code == 200, f"{reg.status_code} {reg.text[:120]}")
account = reg.json()
uid, token = account["id"], account["token"]
req("PUT", f"/api/progress?user={uid}", {"log": [{"type": "ue", "date": "2026-10-30"}],
                                          "errs": []}, token=token)
req("PUT", f"/api/progress?user={uid}", {"log": [{"type": "ue", "date": "2026-10-31"}],
                                          "errs": []}, token=token)
req("GET", "/api/me", token=token)
time.sleep(0.2)
sys.stdout = _real_stdout
cap.seek(0)
log_text = cap.read()
lines = [ln for ln in log_text.splitlines() if "rid=" in ln]
check("S2_access_line_format",
      bool(lines) and re.search(
          r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z rid=[0-9a-f]{8} "
          r"[A-Z]+ /\S* \d{3} \d+ms ip=[0-9a-f]{12}$", lines[-1]) is not None,
      lines[-1] if lines else "no lines")
check("S3_no_raw_ip", "127.0.0.1" not in log_text and "::1" not in log_text)
check("S4_no_token_in_log", token not in log_text and account["token"][:12] not in log_text)

# ---------------------------------------------------------------------------
# 4. Export contains progress + account + plan + usage + audit.
# ---------------------------------------------------------------------------
exp = req("GET", "/api/export", token=token)
body = exp.json()
check("S5_export_complete",
      exp.status_code == 200 and body.get("log") and "account" in body
      and "usage" in body and "audit" in body and "plan" in body,
      f"{exp.status_code} keys={sorted(body)[:12]}")
check("S6_export_no_secrets",
      "hash" not in body["account"] and "salt" not in body["account"]
      and token not in exp.text)

# ---------------------------------------------------------------------------
# 5. Plant usage + licence rows, then delete the account.
# ---------------------------------------------------------------------------
S.plans = __import__("plans")
plans = S.plans
plans.writing_consume(uid)
code = "FT-PRO-1M-AAAA-BBBB-CCCC"
plans.record_issue(code, "pro", 30)
plans.mark_redeemed(code, uid, "2026-12-01T00:00:00Z")

before_user_dir = os.path.join(_tmp, "users", uid)
check("S7_fixtures_present",
      os.path.isdir(before_user_dir)
      and any(v.get("user_id") == uid for v in plans._licenses().values()))

deleted = req("DELETE", "/api/account", {"password": password}, token=token)
check("S8_delete_200", deleted.status_code == 200, f"{deleted.status_code} {deleted.text[:120]}")

check("S9_user_dir_gone", not os.path.exists(before_user_dir))
tokens = json.load(open(os.path.join(_tmp, "tokens.json"), encoding="utf-8"))
usage = json.load(open(os.path.join(_tmp, "usage.json"), encoding="utf-8"))
licences = json.load(open(os.path.join(_tmp, "licenses.json"), encoding="utf-8"))
check("S10_no_token", not any(v.get("user_id") == uid for v in tokens.values()))
check("S11_no_usage", uid not in usage.get("accounts", {}))
check("S12_no_license_link",
      not any(v.get("user_id") == uid for v in licences.values()))

hits = []
for path, text in read_tree(_tmp):
    for line in text.splitlines():
        if uid in line:
            hits.append((os.path.relpath(path, _tmp), line))
check("S13_only_final_audit_line",
      len(hits) == 1 and hits[0][0] == "audit.log"
      and "account_delete" in hits[0][1],
      f"{len(hits)} hit(s): {[h[0] for h in hits]}")
check("S14_final_line_has_no_name",
      not hits or name.lower() not in hits[0][1].lower(),
      hits[0][1][:160] if hits else "")

# ---------------------------------------------------------------------------
# 6. The audit chain still verifies.
# ---------------------------------------------------------------------------
verify = subprocess.run([sys.executable, os.path.join(REPO, "tools", "verify_audit.py"), _tmp],
                        capture_output=True, text=True)
check("S15_verify_audit", verify.returncode == 0, verify.stdout + verify.stderr)

# ---------------------------------------------------------------------------
# 7. Retention: 100-day-old audit line, 21st backup, idempotent second run.
# ---------------------------------------------------------------------------
audit_path = os.path.join(_tmp, "audit.log")
old_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 100 * 86400))
with open(audit_path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"ts": old_ts, "rid": "planted", "event": "planted_old",
                             "user": "", "ip": "", "prev": "0" * 64}) + "\n")

bk_dir = os.path.join(_tmp, "users", "backup-target", "backups")
os.makedirs(bk_dir, mode=0o700, exist_ok=True)
for i in range(21):
    with open(os.path.join(bk_dir, f"progress-20260101-{i:06d}.json"), "w") as handle:
        handle.write("{}")

run1 = subprocess.run([sys.executable, os.path.join(REPO, "tools", "retention.py"), _tmp],
                      capture_output=True, text=True)
after1 = len(os.listdir(bk_dir))
run2 = subprocess.run([sys.executable, os.path.join(REPO, "tools", "retention.py"), _tmp],
                      capture_output=True, text=True)
after2 = len(os.listdir(bk_dir))
audit_after = open(audit_path, encoding="utf-8").read()
check("R1_audit_old_deleted",
      run1.returncode == 0 and "planted_old" not in audit_after
      and "delete audit" in run1.stdout)
check("R2_backups_trimmed", after1 == 20 and after2 == 20,
      f"{after1} -> {after2}")
check("R3_idempotent",
      "delete audit" not in run2.stdout and "delete backup" not in run2.stdout,
      run2.stdout)
verify2 = subprocess.run([sys.executable, os.path.join(REPO, "tools", "verify_audit.py"), _tmp],
                         capture_output=True, text=True)
check("R4_chain_after_retention", verify2.returncode == 0, verify2.stdout + verify2.stderr)

srv.shutdown()
shutil.rmtree(_tmp, ignore_errors=True)

print(json.dumps(out, ensure_ascii=False, indent=1))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print(f"OK {len(out)} checks")
sys.exit(0)
