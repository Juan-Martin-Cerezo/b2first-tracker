"""Multi-user end-to-end tests: real accounts, quotas, limits and account control.

Boots its own server with a temporary DATA_DIR (B2_DEMO=0, B2_REGISTER=open)
plus a mock AI provider, so nothing touches the real data/ nor the real key.
"""
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# 1. Mock AI provider (no network, no real keys)
# ---------------------------------------------------------------------------
VALID_MODEL_JSON = {
    "bands": {"content": 4, "communicative_achievement": 3, "organisation": 4, "language": 2},
    "feedback": {
        "content": "Covers all the points of the task with a clear position.",
        "communicative_achievement": "The register is appropriate and holds the reader.",
        "organisation": "Good use of connectors and clear paragraphs.",
        "language": "Some grammar slips that need polishing for a solid B2.",
    },
    "quotes": {
        "content": "pollution and damage to the environment is the most serious problem",
        "communicative_achievement": "First of all, it is widely believed that transport plays a major role",
        "organisation": "In addition to this, our rivers and seas are in danger",
        "language": "Doing a little steps for protection our environment every day",
    },
    "weaknesses": {
        "content": ["Third supporting point is barely developed.", "Conclusion repeats the introduction."],
        "communicative_achievement": ["Simple ideas dominate without nuance.", "Tone drifts too general at times."],
        "organisation": ["Basic enumerators only ('First of all', 'In addition').", "One-sentence paragraphs."],
        "language": ["Subject-verb agreement error in the opening sentence.", "Wrong collocation in 'Doing a little steps'."],
    },
    "rewrite": [
        "Pollution and environmental damage are among the most pressing challenges worldwide.",
        "First of all, transport causes significant harm to the environment.",
        "Taking small steps to protect our environment every day will help us save the planet.",
    ],
}


class MockAIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            self.rfile.read(length)
        content = json.dumps(VALID_MODEL_JSON, ensure_ascii=False)
        if self.path.endswith("/chat/completions"):
            envelope = {"choices": [{"message": {"role": "assistant", "content": content}}]}
        else:
            envelope = {"candidates": [{"content": {"parts": [{"text": content}]}}]}
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


mock_srv = ThreadingHTTPServer(("127.0.0.1", 0), MockAIHandler)
MOCK_PORT = mock_srv.server_address[1]
threading.Thread(target=mock_srv.serve_forever, daemon=True).start()

# ---------------------------------------------------------------------------
# 2. App server with temporary data + server-owned AI key
# ---------------------------------------------------------------------------
os.environ["B2_DEMO"] = "0"
os.environ["B2_REGISTER"] = "open"
os.environ["B2_AI_KEY"] = "server-owned-fake-key"
os.environ.pop("B2_AI_DAILY_PER_USER", None)
os.environ.pop("B2_AI_DAILY_TOTAL", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S
import store

_tmp = tempfile.mkdtemp(prefix="b2multi-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.B2_DEMO = False
S.B2_REGISTER = "open"
S.B2_AI_BASE = f"http://127.0.0.1:{MOCK_PORT}/v1beta"
S.B2_AI_MODEL = "mock-model"

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
S.PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{S.PORT}"

SAMPLE_TEXT = (
    "Nowadays pollution and damage to the environment is the most serious and difficult problem "
    "for countries all over the world. First of all, transport causes huge damage to the environment "
    "because people cannot imagine living without cars and planes. In addition to this, our rivers "
    "and seas are in danger due to factories pouring waste. Every person must contribute to solving "
    "this problem by taking small steps every day."
)

out = {}


def req(method, path, body=None, token=None, headers=None, raw_body=None):
    """HTTP helper: returns (status, body_text, response_headers)."""
    if raw_body is not None:
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    hdrs = {}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = "Bearer " + token
    if headers:
        hdrs.update(headers)
    r = urllib.request.Request(URL + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


# 1. POST /api/register (user A) -> 200 with a token
st, body, _ = req("POST", "/api/register", {"name": "alice", "password": "correct-horse-9"})
reg_a = json.loads(body)
assert st in (200, 201) and reg_a.get("token"), f"register A failed: {st} {body}"
uid_a, tok_a = reg_a["id"], reg_a["token"]
out["1_register_user_a"] = st

# 2. the same username again -> 409 "That username is taken."
st, body, _ = req("POST", "/api/register", {"name": "alice", "password": "password456"})
assert st == 409 and json.loads(body).get("error") == "That username is taken.", f"dup register: {st} {body}"
out["2_register_duplicate_409"] = st

# 3. POST /api/login (A) -> 200 with a token
st, body, _ = req("POST", "/api/login", {"name": "alice", "password": "correct-horse-9"})
login_a = json.loads(body)
assert st == 200 and login_a.get("token"), f"login A failed: {st} {body}"
tok_a = login_a["token"]
out["3_login_a_200"] = st

# 4. PUT /api/progress (A) with {"log":[{"type":"ue"}]} -> 200
st, body, _ = req("PUT", f"/api/progress?user={uid_a}", {"log": [{"type": "ue"}]}, token=tok_a)
assert st == 200, f"progress PUT failed: {st} {body}"
out["4_progress_put_200"] = st

# 5. GET /api/progress (A) -> returns what was written
st, body, _ = req("GET", f"/api/progress?download=1&user={uid_a}", token=tok_a)
assert st == 200 and json.loads(body)["log"][0]["type"] == "ue", f"progress GET mismatch: {st} {body}"
out["5_progress_get_matches"] = st

# 6. register B -> GET /api/progress (B) sees nothing of A (isolation)
st, body, _ = req("POST", "/api/register", {"name": "bob", "password": "correct-horse-9"})
reg_b = json.loads(body)
assert st in (200, 201) and reg_b.get("token"), f"register B failed: {st} {body}"
uid_b, tok_b = reg_b["id"], reg_b["token"]
st, body, _ = req("GET", f"/api/progress?download=1&user={uid_b}", token=tok_b)
assert st == 200 and "ue" not in body, f"B sees A's data: {st} {body}"
out["6_isolation_b"] = st

# 7. A with an invalid token -> 401
st, body, _ = req("GET", f"/api/progress?download=1&user={uid_a}", token="definitely-not-a-valid-token")
assert st == 401, f"invalid token not rejected: {st} {body}"
out["7_invalid_token_401"] = st

# 8. expired token (exp forced into the past) -> 401 "session expired"
st, body, _ = req("POST", "/api/login", {"name": "alice", "password": "correct-horse-9"})
expired_tok = json.loads(body)["token"]
tok_path = os.path.join(_tmp, "tokens.json")
with open(tok_path, "r", encoding="utf-8") as f:
    tokens = json.load(f)
tokens[hashlib.sha256(expired_tok.encode()).hexdigest()]["exp"] = time.time() - 60
with open(tok_path, "w", encoding="utf-8") as f:
    json.dump(tokens, f)
st, body, _ = req("GET", f"/api/progress?download=1&user={uid_a}", token=expired_tok)
assert st == 401 and "session expired" in body, f"expired token not rejected: {st} {body}"
out["8_expired_token_401"] = st

# 9. PUT /api/progress with 2.1 MB -> 413
big = json.dumps({"log": [], "errs": [], "pad": "x" * int(2.1 * 1024 * 1024)}).encode("utf-8")
st, body, _ = req("PUT", f"/api/progress?user={uid_a}", token=tok_a, raw_body=big)
assert st == 413 and "progress too large" in body, f"oversized PUT not rejected: {st} {body[:200]}"
out["9_progress_2mb_413"] = st

# 10. POST /api/ai/writing with no key and quota 0 -> 429 "daily AI quota reached"
S._AI_RATE.clear()
os.environ["B2_AI_DAILY_PER_USER"] = "0"
st, body, _ = req("POST", "/api/ai/writing", {"text": SAMPLE_TEXT, "kind": "Essay"})
assert st == 429 and json.loads(body).get("error") == "daily AI quota reached", f"quota 0 not enforced: {st} {body[:200]}"
reset_date = json.loads(body).get("reset") or ""
assert re.match(r"\d{4}-\d{2}-\d{2}$", reset_date), f"bad reset date: {reset_date!r}"
out["10_ai_quota_zero_429"] = st

# 11. B2_AI_DAILY_PER_USER=1: first request consumes the quota, second -> 429
os.environ["B2_AI_DAILY_PER_USER"] = "1"
S._AI_RATE.clear()
st1, body1, _ = req("POST", "/api/ai/writing", {"text": SAMPLE_TEXT, "kind": "Essay"})
st2, body2, _ = req("POST", "/api/ai/writing", {"text": SAMPLE_TEXT, "kind": "Essay"})
assert st1 == 200, f"first AI call should pass: {st1} {body1[:200]}"
assert st2 == 429 and json.loads(body2).get("error") == "daily AI quota reached", f"second AI call: {st2} {body2[:200]}"
out["11_ai_quota_one"] = {"first": st1, "second": st2}

# 12. with the user's own key -> 200 even with the server quota exhausted
st, body, _ = req("POST", "/api/ai/writing", {"text": SAMPLE_TEXT, "kind": "Essay", "provider_key": "user-own-key-123"})
assert st == 200 and json.loads(body).get("bands"), f"own key rejected: {st} {body[:200]}"
os.environ["B2_AI_DAILY_PER_USER"] = "8"
out["12_ai_own_key_200"] = st

# 13. 5 failed logins to the same username -> locked: 429 with retry_after (cross-IP)
statuses = []
for _ in range(11):
    st, _body, _hdrs = req("POST", "/api/login", {"name": "brute-target", "password": "wrong-password"},
                           headers={"X-Forwarded-For": "203.0.113.77"})
    statuses.append(st)
assert statuses[:5] == [401] * 5, f"first 5 failed logins should be 401: {statuses}"
assert statuses[5] == 429, f"6th login should be 429 (username locked): {statuses}"
out["13_login_lockout_6th_429"] = statuses

# 14. DELETE /api/account with the wrong password -> 401
st, body, _ = req("DELETE", "/api/account", {"password": "wrong-password"}, token=tok_b)
assert st == 401, f"delete with wrong password: {st} {body}"
out["14_delete_wrong_password_401"] = st

# 15. DELETE /api/account with the right password -> 200 and data/users/<uid>/ is gone
st, body, _ = req("DELETE", "/api/account", {"password": "correct-horse-9"}, token=tok_b)
assert st == 200 and json.loads(body).get("ok") is True, f"delete account failed: {st} {body}"
assert not os.path.exists(os.path.join(_tmp, "users", uid_b)), "data/users/<uid> still exists after delete"
st_tok, _b, _h = req("GET", f"/api/progress?download=1&user={uid_b}", token=tok_b)
assert st_tok == 401, f"deleted user's token still valid: {st_tok}"
out["15_delete_account_200"] = st

# 16. GET /api/export -> application/json with the progress + Content-Disposition
st, body, hdrs = req("GET", "/api/export", token=tok_a)
ctype = hdrs.get("Content-Type", "")
disp = hdrs.get("Content-Disposition", "")
assert st == 200 and ctype.startswith("application/json"), f"export content-type: {st} {ctype}"
assert "attachment" in disp, f"export without Content-Disposition: {disp}"
assert json.loads(body)["log"][0]["type"] == "ue", f"export body mismatch: {body[:200]}"
out["16_export_json"] = {"status": st, "content_type": ctype}

# 17. permissions: data/users/<uid> is 0700 and progress.json is 0600
user_dir = os.path.join(_tmp, "users", uid_a)
prog_file = os.path.join(user_dir, "progress.json")
dir_mode = stat.S_IMODE(os.stat(user_dir).st_mode)
file_mode = stat.S_IMODE(os.stat(prog_file).st_mode)
assert dir_mode == 0o700, f"user dir mode is {oct(dir_mode)}, expected 0o700"
assert file_mode == 0o600, f"progress.json mode is {oct(file_mode)}, expected 0o600"
out["17_permissions"] = {"user_dir": oct(dir_mode), "progress_json": oct(file_mode)}

# 18. the UI with a logged-in session renders without JS errors
st, body, _ = req("POST", "/api/login", {"name": "alice", "password": "correct-horse-9"})
session = json.loads(body)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errores_js = []
    pg.on("pageerror", lambda e: errores_js.append(str(e)))
    pg.goto(URL + "/", wait_until="networkidle")
    pg.evaluate("localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(session)))
    pg.evaluate("localStorage.setItem('ob_%s', '1');" % session["id"])
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(500)
    state = pg.evaluate(
        """() => ({
        hasUser: !!(window.USER && window.USER.token),
        authHidden: getComputedStyle(document.getElementById('authOverlay')).display === 'none',
        footBadge: (document.getElementById('syncBadgeFoot')||{}).textContent || ''
    })"""
    )
    assert state["hasUser"] and state["authHidden"], f"session UI state wrong: {state}"
    assert state["footBadge"] in ("Synced", "Saving…", "Offline"), f"unexpected footer badge: {state}"
    assert errores_js == [], f"JS errors with a logged-in session: {errores_js}"
    out["18_ui_no_js_errors"] = {"state": state, "errores_js": errores_js}
    b.close()

srv.shutdown()
mock_srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
