"""Phase 39 acceptance: the manual password-reset request path.

Boots its own server on a throwaway DATA_DIR (never the repo's data/) and
drives `POST /api/password-reset/request` plus `tools/reset_password.py
--pending`. The point of the endpoint is that it cannot enumerate accounts and
that nothing but a hashed address is stored.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from helpers import isolated_data_dir, isolated_server

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = isolated_data_dir(prefix="b2pwreset-")
URL = isolated_server(extra_env={"B2_DEMO": "0", "B2_REGISTER": "open"},
                      data_dir=DATA_DIR)
QUEUE = os.path.join(DATA_DIR, "pwreset.jsonl")
KNOWN = "pwreset-known"

out = {}


def post(payload):
    req = urllib.request.Request(
        URL + "/api/password-reset/request",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def lines():
    try:
        with open(QUEUE, "r", encoding="utf-8") as f:
            return [ln for ln in f.read().split("\n") if ln.strip()]
    except OSError:
        return []


# 1. An unknown user gets 200 {"ok":true} and a byte-identical body to a known one.
status_a, body_a = post({"name": "nobody-here", "contact": "x@example.com"})
assert status_a == 200, status_a
assert json.loads(body_a) == {"ok": True}, body_a
after_unknown = len(lines())
assert after_unknown == 1, after_unknown

status_b, body_b = post({"name": KNOWN, "contact": "x@example.com"})
assert status_b == 200, status_b
assert body_a == body_b, (body_a, body_b)
out["1_no_enumeration"] = {"status": status_b, "identical_body": body_a.decode()}

# 2. A known user appended exactly one line, with a hashed address only.
assert len(lines()) == 2, len(lines())
entry = json.loads(lines()[-1])
assert entry["name"] == KNOWN, entry
assert entry.get("contact") == "x@example.com", entry
assert re.fullmatch(r"[0-9a-f]{16}", entry.get("ip_hash", "")), entry
assert entry.get("rid"), entry
with open(QUEUE, "r", encoding="utf-8") as f:
    raw = f.read()
assert "127.0.0.1" not in raw, "plaintext IP leaked into pwreset.jsonl"
assert (os.stat(QUEUE).st_mode & 0o777) == 0o600, oct(os.stat(QUEUE).st_mode)
out["2_one_line_hashed_ip"] = {
    "lines": len(lines()), "ip_hash_len": len(entry["ip_hash"]),
    "mode": oct(os.stat(QUEUE).st_mode & 0o777),
}

# 3. Control characters in the contact are stripped; an over-long contact is refused.
status_c, _ = post({"name": KNOWN, "contact": " \x00\x07 bob@example.com \n"})
assert status_c == 200, status_c
assert json.loads(lines()[-1])["contact"] == "bob@example.com", lines()[-1]

before_long = len(lines())
status_d, body_d = post({"name": KNOWN, "contact": "a" * 500})
assert status_d == 422, (status_d, body_d)
assert json.loads(body_d) == {"error": "invalid contact"}, body_d
assert len(lines()) == before_long, "a rejected contact was queued anyway"
out["3_contact"] = {"stripped": "bob@example.com", "long_contact_status": status_d}

# 4. The sixth request from one IP in the same hour is rate-limited.
status_e, _ = post({"name": KNOWN, "contact": "@telegram"})
assert status_e == 200, status_e
status_f, body_f = post({"name": KNOWN, "contact": "@telegram"})
assert status_f == 429, (status_f, body_f)
assert json.loads(body_f)["error"] == "too many requests", body_f
out["4_rate_limit"] = {"sixth_status": status_f}

# 5. The operator tool prints the queued name for this DATA_DIR.
env = dict(os.environ)
env["DATA_DIR"] = DATA_DIR
env["B2_DATA_DIR"] = DATA_DIR
proc = subprocess.run(
    [sys.executable, os.path.join(REPO, "tools", "reset_password.py"), "--pending"],
    cwd=REPO, env=env, capture_output=True, text=True,
)
assert proc.returncode == 0, (proc.returncode, proc.stderr)
assert KNOWN in proc.stdout, proc.stdout
assert "ip_hash" not in proc.stdout, proc.stdout
out["5_pending"] = {"returncode": proc.returncode, "rows": len(proc.stdout.splitlines())}

print(json.dumps(out, ensure_ascii=False, indent=1))
sys.exit(0)
