"""S3 acceptance: live examiner token, minute ledger and the sim transport.

No Google key and no network: a local stdlib stub plays the ephemeral-token
provisioning service. The browser runs the real index.html with ?spk=sim, so
the exam script, the playback queue and barge-in are exercised without a model.

    cd tests && uv run --with playwright python test_speaking_live.py
"""
import json
import os
import re
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

FAKE_KEY = "FAKEKEY123"
USER = "spk-live-runner"
PASS = "spk-live-pass-9"


class TokenStub(BaseHTTPRequestHandler):
    """Stand-in for POST /v1beta/auth_tokens (returns a token in `name`)."""

    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        STUB["body"] = self.rfile.read(length) if length else b""
        STUB["headers"] = {k.lower(): v for k, v in self.headers.items()}
        STUB["calls"] += 1
        body = json.dumps({"name": "ephemeral-token-abc",
                           "expireTime": "2030-01-01T00:00:00Z"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


STUB = {"body": b"", "headers": {}, "calls": 0}
stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), TokenStub)
STUB_PORT = stub_srv.server_address[1]
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()

os.environ["B2_SPK_GOOGLE_KEY"] = FAKE_KEY
os.environ["B2_SPK_GOOGLE_TOKEN_URL"] = (
    f"http://127.0.0.1:{STUB_PORT}/v1beta/auth_tokens")

import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2spklive-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.migrate_legacy()

BASE = {}


def start_server():
    srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    BASE["url"] = f"http://127.0.0.1:{port}"
    BASE["srv"] = srv
    return srv


def http(path, body=None, token=None, method="POST", base=None):
    url = (base or BASE["url"]) + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def register():
    st, body, _ = http("/api/register", {"name": USER, "password": PASS})
    assert st == 200, f"register failed: {st} {body}"
    return json.loads(body)["token"]


def reset_limits():
    S._RATE.clear()


def wait_until(pg, expression, timeout_s, step=100):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pg.evaluate(expression):
            return True
        pg.wait_for_timeout(step)
    return False


def main():
    out = {}
    srv = start_server()
    reset_limits()
    token = register()

    # 1. No key -> 503 speech_not_configured (one log line, no Retry-After).
    saved_key = os.environ.pop("B2_SPK_GOOGLE_KEY", None)
    try:
        reset_limits()
        st, body, headers = http("/api/speaking/token", {"session_id": "suite-live-1"}, token=token)
        j = json.loads(body)
        assert st == 503 and j.get("error") == "speech_not_configured", f"{st} {body}"
        assert "Retry-After" not in {k.title() for k in headers}, headers
        out["1_no_key_503"] = j["error"]
    finally:
        os.environ["B2_SPK_GOOGLE_KEY"] = saved_key or FAKE_KEY

    # 2. With a fake key + local stub: 200 and the documented body, no key leak.
    reset_limits()
    before = STUB["calls"]
    st, body, _ = http("/api/speaking/token", {"session_id": "suite-live-1"}, token=token)
    j = json.loads(body)
    assert st == 200, f"mint failed: {st} {body}"
    assert j["token"] == "ephemeral-token-abc", j
    assert j["expires_in"] == 1800, j
    assert j["ws_url"].startswith("wss://generativelanguage.googleapis.com/"), j
    assert j["model"] == "gemini-3.8-live", j
    assert FAKE_KEY not in body, "the Google key leaked into the response"
    assert "EXAMINER_SYSTEM" not in body and "interlocutor" in j["instruction"].lower(), \
        "the examiner instruction is missing from the mint response"
    assert STUB["calls"] == before + 1, "the mint did not reach the stub"
    assert STUB["headers"].get("x-goog-api-key") == FAKE_KEY, STUB["headers"]
    sent = json.loads(STUB["body"])
    assert sent.get("uses") == 1, sent
    assert "expireTime" in sent and "newSessionExpireTime" in sent, sent
    out["2_mint_contract"] = True

    # 2b. S4: the same endpoint mints the partner's own instruction.
    reset_limits()
    st, body, _ = http("/api/speaking/token", {"role": "partner", "part": 3, "session_id": "suite-live-1"},
                       token=token)
    j = json.loads(body)
    assert st == 200 and j["role"] == "partner" and j["part"] == 3, (st, body)
    assert "Candidate B" in j["instruction"], "the partner instruction is missing"
    assert "interlocutor in a Cambridge" not in j["instruction"], \
        "the partner received the examiner prompt"
    out["2b_partner_mint"] = True

    # 3. No Authorization -> 401; an invalid one -> 401 too.
    reset_limits()
    st, _, _ = http("/api/speaking/token", {})
    assert st == 401, f"anonymous mint accepted: {st}"
    st, _, _ = http("/api/speaking/token", {}, token="not-a-session")
    assert st == 401, f"invalid session accepted: {st}"
    out["3_auth_401"] = True

    # 4. 10 tokens/min/user, the 11th -> 429 + Retry-After.
    reset_limits()
    codes = [http("/api/speaking/token", {"session_id": "suite-live-1"}, token=token)[0] for _ in range(11)]
    assert codes[:10] == [200] * 10, codes
    assert codes[10] == 429, f"11th mint allowed: {codes}"
    out["4_token_rate_429"] = codes[10]

    # 5. Minute ledger: accumulates, clamps at the cap, persisted at 0600.
    reset_limits()
    os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "20"
    st, body, _ = http("/api/speaking/minute", {"seconds": 100}, token=token)
    j = json.loads(body)
    assert st == 200 and j["remaining_s"] == 20 * 60 - 100, f"{st} {body}"
    assert j["used_s"] == 100 and j["cap_s"] == 1200, j
    st, body, _ = http("/api/speaking/minute", {"seconds": 0}, token=token)
    assert json.loads(body)["used_s"] == 100, "a 0-second probe consumed minutes"
    st, _, _ = http("/api/speaking/minute", {"seconds": 100})
    assert st == 401, "anonymous minute report accepted"
    st, body, _ = http("/api/speaking/minute", {"seconds": -5}, token=token)
    assert st == 422, f"negative seconds accepted: {st} {body}"
    ledger = store.speaking_file(USER)
    assert os.path.exists(ledger), "speaking.json was not created"
    assert oct(os.stat(ledger).st_mode & 0o777) == "0o600", oct(os.stat(ledger).st_mode)
    saved = json.load(open(ledger, encoding="utf-8"))
    assert saved["seconds"] == 100.0 and saved["tokens_minted"] >= 10, saved
    out["5_minute_ledger"] = saved

    # 6. /api/metrics exposes the two new sums.
    metrics = S.build_metrics()
    assert metrics["speaking_minutes_today"] >= 1.6, metrics
    assert metrics["speaking_tokens_minted"] >= 10, metrics
    out["6_metrics"] = {k: metrics[k] for k in
                        ("speaking_minutes_today", "speaking_tokens_minted")}

    # 7. A restart keeps the consumption (same data dir, new process state).
    srv.shutdown()
    srv.server_close()
    S._RATE.clear()
    srv = start_server()
    st, body, _ = http("/api/speaking/minute", {"seconds": 0}, token=token)
    j = json.loads(body)
    assert st == 200 and j["used_s"] == 100, f"ledger lost on restart: {st} {body}"
    out["7_restart_keeps"] = j["used_s"]

    # --- Browser: real index.html, deterministic sim transport ---------------
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright missing: cd tests && uv run --with playwright "
                         "python test_speaking_live.py")

    from helpers import login_owner

    page_errors, console_errors = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
        ])
        ctx = b.new_context()
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.on("console", lambda m: console_errors.append(m.text)
              if m.type == "error" else None)

        pg.goto(BASE["url"] + "/?spk=sim", wait_until="networkidle")
        login_owner(pg, BASE["url"] + "/")
        pg.evaluate("showView('hoy');selectSessionStudio('fri-b')")
        assert pg.evaluate("typeof makeTransport==='function' && "
                           "typeof makeLiveTransport==='function' && "
                           "typeof makeSimTransport==='function'"), \
            "the transport interface is missing"

        os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "20"
        pg.click("#spkOpenBtn")
        assert wait_until(pg, "!!(window.SPK && SPK.running === true)", 20), \
            "sim session did not start"
        assert pg.evaluate("SPK.mode") == "sim", pg.evaluate("SPK.mode")
        out["sim_badge"] = pg.evaluate("document.getElementById('spkBadge').textContent")

        # 8. Barge-in: local speech during the examiner's turn empties the queue.
        assert wait_until(pg, "SPK.turns.length >= 1 && SPK.speaking === true", 10), \
            "the examiner never started speaking"
        pg.evaluate("SPK.simulateUserSpeech(800)")
        assert wait_until(pg, "SPK.turns.some(t => t.interrupted === true)", 10), \
            "barge-in did not mark the turn"
        assert wait_until(pg, "SPK.queueEmpty() === true", 5), \
            "the audio queue was not emptied on barge-in"
        assert pg.evaluate("SPK.muted === true || SPK.barged === true"), \
            "the output was not muted on barge-in"
        out["8_barge_in"] = pg.evaluate(
            "({interrupted: SPK.turns.filter(t=>t.interrupted).length, "
            "count: SPK.interrupted, empty: SPK.queueEmpty()})")

        # 9. Three deterministic turns complete with both transcripts visible.
        assert wait_until(pg, "SPK.outCount >= 3 && SPK.inCount >= 3", 25), \
            "the 3-turn script did not complete"
        lines = pg.evaluate("SPK.lines.map(l => ({side:l.side, t:l.t}))")
        assert len(lines) >= 6, lines
        times = [l["t"] for l in lines]
        assert times == sorted(times), f"transcript timestamps are not increasing: {times}"
        assert times[-1] > times[0], times
        assert pg.evaluate("document.querySelectorAll('#spkInText .spk-line').length") >= 3
        assert pg.evaluate("document.querySelectorAll('#spkOutText .spk-line').length") >= 3
        assert "Good morning" in pg.evaluate(
            "document.getElementById('spkOutText').textContent")
        out["9_turns"] = pg.evaluate(
            "({turns: SPK.turns.length, inLines: SPK.inCount, outLines: SPK.outCount, "
            "lastTs: SPK.lines[SPK.lines.length-1].t})")

        pg.evaluate("spkStop()")
        assert wait_until(pg, "SPK.running === false && SPK.lastCtx !== null", 10), \
            "session did not stop"
        assert wait_until(pg, "SPK.lastCtx.state === 'closed'", 5), \
            "the AudioContext was not closed on stop"

        # 10. Cap reached -> the client refuses to start and says the message.
        os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "0"
        try:
            pg.evaluate("spkDiscard()")
            pg.evaluate("spkStart()")
            assert wait_until(
                pg,
                "document.getElementById('spkStatus').textContent"
                ".includes('daily speaking limit reached')",
                10), "the cap message never appeared"
            assert pg.evaluate("SPK.running === false"), "the client started over the cap"
            out["10_cap_message"] = pg.evaluate(
                "document.getElementById('spkStatus').textContent")
            assert "daily speaking limit reached (20 min)" in out["10_cap_message"], \
                out["10_cap_message"]
        finally:
            os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "20"

        # 11. Open + close three times: no AudioContext leaks.
        pg.evaluate("spkDiscard()")
        for _ in range(3):
            pg.evaluate("spkStart()")
            assert wait_until(pg, "SPK.running === true", 10), "restart failed"
            pg.evaluate("spkStop()")
            assert wait_until(pg, "SPK.lastCtx !== null && SPK.lastCtx.state === 'closed'",
                              5), "AudioContext stayed open across restarts"
        assert pg.evaluate("SPK.lastCtx.state") == "closed", "leaked AudioContext"
        out["11_ctx_closed"] = pg.evaluate("SPK.lastCtx.state")

        # 12. No JS/console errors anywhere in the run.
        assert not page_errors, f"page errors: {page_errors}"
        assert not console_errors, f"console errors: {console_errors}"
        out["12_no_console_errors"] = True

        b.close()

    srv.shutdown()
    stub_srv.shutdown()

    # 13. The microphone PCM never reached our server: only the ledger exists.
    stray = []
    for dirpath, _dirs, files in os.walk(_tmp):
        for fn in files:
            if fn.lower().endswith((".wav", ".pcm", ".ogg", ".webm")):
                stray.append(os.path.join(dirpath, fn))
    assert not stray, f"audio written to disk: {stray}"
    out["13_no_audio_on_disk"] = True

    # 14. The client source wires the verified endpoint and never a wildcard.
    html = open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
    assert "BidiGenerateContentConstrained" in html, "verified WSS path missing"
    assert "access_token=" in html, "ephemeral token is not passed as access_token"
    assert "inputAudioTranscription" in html and "outputAudioTranscription" in html
    assert not re.search(r"connect-src[^;\"]*\\*", html), "CSP wildcard appeared"
    out["14_client_protocol"] = True

    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("OK: S3 acceptance passed")


if __name__ == "__main__":
    main()
