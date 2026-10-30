"""Phase 30 acceptance: bring-your-own provider key for writing + speaking.

Runs a real server process (temporary DATA_DIR, no owner data) and a local stub
that plays an OpenAI-compatible provider. The stub is trusted through
B2_BYO_TRUSTED_BASES, so the same request path is exercised without network.

The important assertion is the leak test: a sentinel key is sent through a live
request (success and then a provider 500), and afterwards the whole data/ tree,
the access log, the audit log and the last 200 journal lines must contain it
zero times.

    cd tests && uv run --with httpx python test_byokey.py
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402

USER = "byo-runner"
PASS = "byo-runner-pass-9"

SAMPLE_TEXT = (
    "Nowadays pollution and damage to the environment is the most serious and difficult "
    "problem for countries all over the world. First of all, transport causes huge damage "
    "to the environment because people cannot imagine living without cars and planes. In "
    "addition to this, our rivers and seas are in danger due to factories pouring waste. "
    "Every person must contribute to solving this problem by taking small steps every day. "
    "Governments should also invest in clean public transport and renewable energy so that "
    "future generations inherit a healthier planet with cleaner air and safer water."
)

VALID_MODEL_JSON = {
    "bands": {
        "content": 4,
        "communicative_achievement": 3,
        "organisation": 4,
        "language": 3,
    },
    "feedback": {
        "content": "Covers the task with a clear position and enough development.",
        "communicative_achievement": "The register is appropriate and holds the reader.",
        "organisation": "Good use of connectors and clear paragraphs.",
        "language": "Some slips, but the meaning is always clear.",
    },
    "quotes": {
        "content": "pollution and damage to the environment is the most serious",
        "communicative_achievement": "First of all, transport causes huge damage",
        "organisation": "In addition to this, our rivers and seas are in danger",
        "language": "people cannot imagine living without cars and planes",
    },
    "weaknesses": {
        "content": ["The third argument could be developed further.",
                    "The conclusion repeats the introduction."],
        "communicative_achievement": ["Ideas stay simple without nuance.",
                                      "The tone drifts general at times."],
        "organisation": ["Basic enumerators only.",
                         "Some paragraphs are a single sentence."],
        "language": ["Subject-verb agreement slip in the opening sentence.",
                     "Article missing before 'future generations'."],
    },
    "rewrite": [
        "Environmental damage has become one of the most pressing global problems.",
        "First of all, transport inflicts significant harm on the environment.",
        "Governments should invest in clean public transport and renewable energy.",
    ],
}

STUB = {"calls": 0, "headers": {}, "body": {}, "mode": "ok"}


class StubProvider(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        STUB["calls"] += 1
        STUB["headers"] = {k.lower(): v for k, v in self.headers.items()}
        try:
            STUB["body"] = json.loads(raw.decode("utf-8"))
        except ValueError:
            STUB["body"] = {}
        if STUB["mode"] == "fail500":
            body = b'{"error":"stub upstream failure"}'
            self.send_response(500)
        else:
            content = json.dumps(VALID_MODEL_JSON)
            envelope = {"choices": [{"message": {"role": "assistant", "content": content}}]}
            body = json.dumps(envelope).encode("utf-8")
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def wait_health(base, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def request(base, path, body=None, token=None, headers=None, method="POST"):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def read_tree(root):
    chunks = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as f:
                    chunks.append(f.read())
            except OSError:
                pass
    return b"\n".join(chunks)


def journal_tail():
    try:
        out = subprocess.run(["journalctl", "-n", "200", "--no-pager"],
                             capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


out = {}

# 1. Stub provider + real server process on a temporary DATA_DIR.
stub = ThreadingHTTPServer(("127.0.0.1", 0), StubProvider)
STUB_URL = "http://127.0.0.1:%d" % stub.server_address[1]
threading.Thread(target=stub.serve_forever, daemon=True).start()

DATA_DIR = tempfile.mkdtemp(prefix="b2byo-")
PORT = free_port()
APP_URL = "http://127.0.0.1:%d" % PORT
stdout_path = os.path.join(DATA_DIR, "..", os.path.basename(DATA_DIR) + "-stdout.log")
stderr_path = os.path.join(DATA_DIR, "..", os.path.basename(DATA_DIR) + "-stderr.log")
stdout_path = os.path.abspath(stdout_path)
stderr_path = os.path.abspath(stderr_path)

env = dict(os.environ)
env.update({
    "DATA_DIR": DATA_DIR,
    "PORT": str(PORT),
    "B2_HOST": "127.0.0.1",
    "B2_DEMO": "0",
    "B2_REGISTER": "open",
    "B2_AI_KEY": "owner-key-not-a-secret",
    "B2_AI_BASE": STUB_URL,
    "B2_AI_MODEL": "deepseek-chat",
    "B2_AI_PROVIDER": "deepseek",
    "B2_AI_DAILY_PER_USER": "8",
    "B2_AI_DAILY_TOTAL": "800",
    "B2_BYO_TRUSTED_BASES": STUB_URL,
})
stdout_file = open(stdout_path, "w", encoding="utf-8")
stderr_file = open(stderr_path, "w", encoding="utf-8")
proc = subprocess.Popen([sys.executable, os.path.join(REPO, "server.py")],
                        cwd=REPO, env=env, stdout=stdout_file, stderr=stderr_file)
try:
    assert wait_health(APP_URL), "the test server did not start"
    helpers._ensure_account(APP_URL + "/", USER, PASS)
    login = helpers._api(APP_URL + "/", "api/login", {"name": USER, "password": PASS})
    TOKEN = login["token"]
    out["1_server_up"] = True

    def ai(body, headers=None, ip="198.51.100.10"):
        hdrs = {"X-Forwarded-For": ip}
        if headers:
            hdrs.update(headers)
        return request(APP_URL, "/api/ai/writing", body, token=TOKEN, headers=hdrs)

    def account():
        st, body, _ = request(APP_URL, "/api/account", token=TOKEN, method="GET")
        assert st == 200, (st, body)
        return json.loads(body)

    # 2. No headers -> owner key path: quota applies and the counter moves.
    before = account()["ai_left_today"]
    st, body, _ = ai({"text": SAMPLE_TEXT, "task": "essay", "kind": "Essay"},
                     ip="198.51.100.21")
    assert st == 200, "owner path failed: %s %s" % (st, body[:200])
    after = account()["ai_left_today"]
    assert after == before - 1, "owner quota did not move: %s -> %s" % (before, after)
    st2, body2, _ = ai({"text": SAMPLE_TEXT, "task": "essay", "kind": "Essay"},
                       ip="198.51.100.22")
    assert st2 == 200, "second owner call within the limit failed: %s %s" % (st2, body2[:200])
    after2 = account()["ai_left_today"]
    assert after2 == after - 1, "second owner call did not consume quota"
    out["2_owner_quota"] = {"before": before, "after": after, "after2": after2}

    # 3. A stub key + stub base: the stub receives Bearer <key>, and the answer
    #    is returned. The response never carries the key.
    sentinel = "KEY_SENTINEL_" + secrets.token_hex(8)
    st, body, _ = ai({"text": SAMPLE_TEXT, "task": "essay", "kind": "Essay"},
                     {"X-Provider-Key": sentinel,
                      "X-Provider-Base": STUB_URL,
                      "X-Provider-Model": "byo-model-x"},
                     ip="198.51.100.31")
    assert st == 200, "BYO call failed: %s %s" % (st, body[:200])
    assert json.loads(body).get("bands"), "BYO response has no bands"
    assert STUB["headers"].get("authorization") == "Bearer " + sentinel, \
        "the stub did not receive the user's key"
    assert STUB["body"].get("model") == "byo-model-x", STUB["body"].get("model")
    assert sentinel not in body, "the key leaked into the response"
    out["3_byo_bearer"] = True

    # 4. The user's key means their cost: the daily counter does not move.
    before = account()["ai_left_today"]
    for ip in ("198.51.100.41", "198.51.100.42"):
        st, body, _ = ai({"text": SAMPLE_TEXT, "task": "essay", "kind": "Essay"},
                         {"X-Provider-Key": sentinel,
                          "X-Provider-Base": STUB_URL,
                          "X-Provider-Model": "byo-model-x"},
                         ip=ip)
        assert st == 200, "BYO call failed: %s %s" % (st, body[:200])
    after = account()["ai_left_today"]
    assert after == before, "BYO consumed the owner quota: %s -> %s" % (before, after)
    out["4_byo_no_quota"] = {"before": before, "after": after}

    # 5. Hostile bases are refused with 400 and never reach the stub.
    bad_bases = [
        "http://127.0.0.1:9999",
        "https://10.0.0.5",
        "https://localhost",
        "http://api.example.com",
        "https://x:8443",
    ]
    calls_before = STUB["calls"]
    for base in bad_bases:
        st, body, _ = ai({"text": SAMPLE_TEXT, "task": "essay", "kind": "Essay"},
                         {"X-Provider-Key": sentinel, "X-Provider-Base": base},
                         ip="198.51.100.51")
        assert st == 400, "hostile base accepted (%s): %s %s" % (base, st, body[:160])
        assert json.loads(body).get("error") == "invalid_provider_base", body
        assert base not in body, "the refused base was echoed back"
    assert STUB["calls"] == calls_before, "a hostile base reached the stub"
    out["5_bad_bases_400"] = len(bad_bases)

    # 6. Provider test endpoint: {ok, model}, no key, no provider body.
    st, body, _ = request(APP_URL, "/api/ai/provider/test", {}, token=TOKEN,
                          headers={"X-Forwarded-For": "198.51.100.61",
                                   "X-Provider-Key": sentinel,
                                   "X-Provider-Base": STUB_URL,
                                   "X-Provider-Model": "byo-model-x"})
    assert st == 200, "provider test failed: %s %s" % (st, body[:160])
    tested = json.loads(body)
    assert tested == {"ok": True, "model": "byo-model-x"}, tested
    assert sentinel not in body
    st, body, _ = request(APP_URL, "/api/ai/provider/test", {}, token=TOKEN,
                          headers={"X-Forwarded-For": "198.51.100.62"})
    assert st == 400 and json.loads(body).get("code") == "provider_key_required", body
    STUB["mode"] = "fail500"
    st, body, _ = request(APP_URL, "/api/ai/provider/test", {}, token=TOKEN,
                          headers={"X-Forwarded-For": "198.51.100.63",
                                   "X-Provider-Key": sentinel,
                                   "X-Provider-Base": STUB_URL})
    assert st == 502 and json.loads(body).get("code") == "upstream_failed", body
    assert sentinel not in body
    STUB["mode"] = "ok"
    out["6_provider_test"] = True

    # 7. The leak test: a live success, then a live provider 500, and the
    #    sentinel must be absent everywhere.
    st, ok_body, _ = ai({"text": SAMPLE_TEXT, "task": "essay", "kind": "Essay"},
                        {"X-Provider-Key": sentinel, "X-Provider-Base": STUB_URL},
                        ip="198.51.100.71")
    assert st == 200, "leak-test success call failed: %s %s" % (st, ok_body[:160])
    STUB["mode"] = "fail500"
    st, err_body, _ = ai({"text": SAMPLE_TEXT, "task": "essay", "kind": "Essay"},
                         {"X-Provider-Key": sentinel, "X-Provider-Base": STUB_URL},
                         ip="198.51.100.72")
    assert st == 502, "provider failure was not mapped to 502: %s %s" % (st, err_body[:160])
    STUB["mode"] = "ok"
    assert sentinel not in ok_body and sentinel not in err_body, \
        "the key leaked into a response"
    time.sleep(0.4)  # let the access log flush

    tree = read_tree(DATA_DIR)
    assert sentinel.encode() not in tree, "the key leaked into the data/ tree"

    stdout_file.flush()
    stderr_file.flush()
    access_log = open(stdout_path, "r", encoding="utf-8", errors="replace").read()
    server_err = open(stderr_path, "r", encoding="utf-8", errors="replace").read()
    assert sentinel not in access_log, "the key leaked into the access log"
    assert sentinel not in server_err, "the key leaked into the server stderr"
    audit_path = os.path.join(DATA_DIR, "audit.log")
    audit_text = open(audit_path, "r", encoding="utf-8").read() if os.path.exists(audit_path) else ""
    assert sentinel not in audit_text, "the key leaked into audit.log"
    journal = journal_tail()
    if journal is not None:
        assert sentinel not in journal, "the key leaked into the journal"
    out["7_leak_test"] = {"journal_checked": journal is not None,
                          "access_log_bytes": len(access_log)}

    # 8. The key is absent from the synced document and the export endpoint.
    st, prog, _ = request(APP_URL, "/api/progress?user=%s&download=1" % login["id"],
                          token=TOKEN, method="GET")
    assert st == 200 and sentinel not in prog, \
        "the key reached /api/progress (%s): %s" % (st, prog[:120])
    st, export, _ = request(APP_URL, "/api/export", token=TOKEN, method="GET")
    assert st == 200 and sentinel not in export, "the key reached /api/export"
    out["8_not_in_progress_or_export"] = True

    print(json.dumps(out, ensure_ascii=False, indent=1))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    stub.shutdown()
    stdout_file.close()
    stderr_file.close()
