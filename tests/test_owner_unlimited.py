"""Owner unlimited daily usage tests (offline, stubbed upstreams).

With B2_OWNER_UIDS=juan-martin-cerezo:
  1. Owner gets effectively infinite daily limits in /api/plan while regular
     accounts keep the service row (5 writings / 1 mock / 15 min).
  2. Regular user hits 429 on writing call #6 (per-user daily cap = 5).
  3. Owner completes 25 writing calls on the same day without 429, blowing past
     both B2_AI_DAILY_PER_USER=5 and B2_AI_DAILY_TOTAL=20, while another
     regular user is blocked by the instance daily total.
  4. Regular user hits 429 on speaking session #2 (1 mock/day).
  5. Owner logs 30 speaking minutes (past B2_SPK_MIN_DAILY_PER_USER=15 and
     B2_SPK_MIN_DAILY_TOTAL=25) and still opens 3 fresh speaking sessions plus
     a Live token without 429, while a regular user is blocked by the daily
     speaking minute ceiling.
  6. Exhausting the global monthly Gemini Live guard (SPK_MONTH_MINUTES) still
     returns 429 voice_month for everyone, including the owner.

Run:
    cd tests && uv run --no-project --quiet --with playwright --with httpx python test_owner_unlimited.py
"""
import base64
import json
import math
import os
import struct
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OWNER_UID = "juan-martin-cerezo"
OWNER_PASS = "owner-unlimited-pass-9"
REG_UID = "regular-student"
REG_PASS = "regular-student-pass-9"
REG2_UID = "regular-student-2"
REG2_PASS = "regular-student-2-pass-9"

LEGIT_ESSAY = "\n\n".join([
    "Nowadays, pollution has become one of the most serious problems in our society.",
    "First of all, transport causes a huge amount of damage to the environment because people "
    "cannot imagine their daily lives without cars and planes. In addition to this, our rivers "
    "and seas are in danger due to the waste that factories pour into them every single day.",
    "Furthermore, governments should invest in public transport so that citizens can travel "
    "without harming the planet. Finally, every person must contribute to solving this problem "
    "by taking small steps every day, such as recycling at home and using bicycles for short trips.",
    "In conclusion, protecting the environment is a shared responsibility that requires action "
    "from both governments and ordinary people. Small daily habits can make a real difference.",
])

WRITING_OK = {
    "bands": {
        "content": 4,
        "communicative_achievement": 3,
        "organisation": 4,
        "language": 3,
    },
    "feedback": {
        "content": "Covers the points of the task clearly.",
        "communicative_achievement": "Appropriate register for an essay.",
        "organisation": "Clear paragraphs and linking words.",
        "language": "Mostly accurate B2 grammar and vocabulary.",
    },
    "quotes": {
        "content": "pollution has become one of the most serious problems",
        "communicative_achievement": "First of all, transport causes a huge amount of damage",
        "organisation": "In addition to this, our rivers and seas are in danger",
        "language": "Small daily habits can make a real difference",
    },
    "weaknesses": {
        "content": ["Could develop the third point further.", "Conclusion is brief."],
        "communicative_achievement": ["Some ideas remain general.", "Could add nuance."],
        "organisation": ["Relies on basic enumerators.", "Short closing paragraph."],
        "language": ["Limited complex structures.", "Occasional repetition."],
    },
    "rewrite": [
        "Pollution has become one of the most pressing challenges worldwide.",
        "First of all, transport causes significant harm to the environment.",
        "Taking small steps every day can make a meaningful difference.",
    ],
}


def pcm_bytes(seconds=0.2, rate=24000):
    """Minimal valid 16-bit mono PCM for the stubbed TTS response."""
    n = int(rate * seconds)
    return b"".join(
        struct.pack("<h", int(2000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(n)
    )


class ProviderStub(BaseHTTPRequestHandler):
    """Local stub for DeepSeek writing, Gemini turn/TTS, and Live token mint."""

    def log_message(self, fmt, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        _ = self.rfile.read(length) if length > 0 else b""
        path = self.path.split("?")[0]
        if path.endswith("/auth_tokens"):
            self._json({
                "name": "ephemeral-token-stub",
                "expireTime": "2030-01-01T00:00:00Z",
            })
            return
        if ":generateContent" in path:
            if "flash-preview-tts" in path:
                self._json({"candidates": [{"content": {"parts": [{
                    "inlineData": {
                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                        "data": base64.b64encode(pcm_bytes()).decode("ascii"),
                    }}]}}]})
                return
            pair = {
                "transcript": "Travelling by bike is healthier.",
                "reply": "What makes it healthier for you?",
            }
            self._json({"candidates": [{"content": {"parts": [
                {"text": json.dumps(pair)}
            ]}}]})
            return
        self._json({"choices": [{"message": {
            "role": "assistant",
            "content": json.dumps(WRITING_OK, ensure_ascii=False),
        }}]})


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), ProviderStub)
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()
STUB_URL = "http://127.0.0.1:%d" % stub_srv.server_address[1]

os.environ["B2_OWNER_UIDS"] = OWNER_UID
os.environ["B2_AI_PROVIDER"] = "deepseek"
os.environ["B2_AI_BASE"] = STUB_URL
os.environ["B2_AI_MODEL"] = "deepseek-chat"
os.environ["B2_AI_KEY"] = "FAKE-OWNER-TEST-KEY"
os.environ["B2_AI_DAILY_PER_USER"] = "5"
os.environ["B2_AI_DAILY_TOTAL"] = "20"
os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "15"
os.environ["B2_SPK_MIN_DAILY_TOTAL"] = "25"
os.environ["B2_SPK_GOOGLE_KEY"] = "FAKE-SPK-TEST-KEY"
os.environ["B2_SPK_GOOGLE_TOKEN_URL"] = STUB_URL + "/v1beta/auth_tokens"
os.environ["B2_SPK_TURN_BASE"] = STUB_URL
os.environ["B2_SPK_TURN_MODEL"] = "gemini-2.5-flash"
os.environ["B2_SPK_TTS_MODEL"] = "gemini-2.5-flash-preview-tts"
os.environ.pop("B2_SPK_LIVE", None)

import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2owner-unlim-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.B2_AI_BASE = STUB_URL
S.B2_AI_MODEL = "deepseek-chat"
S.migrate_legacy()

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
URL = "http://127.0.0.1:%d" % srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def api(path, payload=None, token=None, clear_rate=False):
    if clear_rate:
        S._AI_RATE.clear()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        URL + path, data=data, headers=headers,
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw.decode("utf-8")) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return e.code, {}


def register_user(name, password):
    S._RATE.clear()
    st, body = api("/api/register", {"name": name, "password": password})
    assert st == 200, f"register {name} failed: {st} {body}"
    return body["token"]


def turn_body(session_id):
    pcm = b"\x01\x00" * 16000
    return {
        "audio_b64": base64.b64encode(pcm).decode("ascii"),
        "mime": "audio/pcm;rate=16000",
        "part": 2,
        "role": "examiner",
        "history": [{"who": "candidate", "text": "I think cycling is healthier."}],
        "task_id": "p2-1",
        "session_id": session_id,
        "tts": "none",
    }


def main():
    out = {}

    owner_token = register_user(OWNER_UID, OWNER_PASS)
    reg_token = register_user(REG_UID, REG_PASS)
    reg2_token = register_user(REG2_UID, REG2_PASS)

    assert S.plans.is_owner(OWNER_UID), "B2_OWNER_UIDS did not recognise owner"
    assert not S.plans.is_owner(REG_UID), "regular account treated as owner"

    # 1. /api/plan reflects unlimited daily caps for owner and default caps for service.
    st, owner_plan = api("/api/plan", token=owner_token)
    assert st == 200 and owner_plan["plan"] == "owner", (st, owner_plan)
    assert owner_plan["limits"]["writing"]["limit"] == 1_000_000, owner_plan
    assert owner_plan["limits"]["speaking"]["mocks"] == 1_000_000, owner_plan
    assert owner_plan["limits"]["speaking"]["minutes"] == 1_000_000, owner_plan

    st, reg_plan = api("/api/plan", token=reg_token)
    assert st == 200 and reg_plan["plan"] == "service", (st, reg_plan)
    assert reg_plan["limits"]["writing"]["limit"] == 5, reg_plan
    assert reg_plan["limits"]["speaking"]["mocks"] == 3, reg_plan
    assert reg_plan["limits"]["speaking"]["minutes"] == 45, reg_plan
    out["1_plans"] = {"owner": owner_plan["plan"], "regular": reg_plan["plan"]}

    # 2. Regular account hits 429 on writing call #6 (B2_AI_DAILY_PER_USER=5).
    for i in range(5):
        st, body = api("/api/ai/writing",
                       {"text": LEGIT_ESSAY, "task": "essay"},
                       token=reg_token, clear_rate=True)
        assert st == 200, f"regular writing #{i + 1} failed: {st} {body}"
    st, body = api("/api/ai/writing",
                   {"text": LEGIT_ESSAY, "task": "essay"},
                   token=reg_token, clear_rate=True)
    assert st == 429 and body.get("error") == "limit_reached" and body.get("limit") == "writing", \
        f"regular writing #6 should 429 limit_reached: {st} {body}"
    out["2_regular_writing_429"] = {"after": 5, "status": st, "error": body.get("error")}

    # 3. Owner completes 25 text writing calls in the same day (past per-user=5 and total=20).
    for i in range(25):
        st, body = api("/api/ai/writing",
                       {"text": LEGIT_ESSAY, "task": "essay"},
                       token=owner_token, clear_rate=True)
        assert st == 200, f"owner writing #{i + 1} failed: {st} {body}"
    # Another regular user is blocked because the instance daily total (20) is spent.
    st, body = api("/api/ai/writing",
                   {"text": LEGIT_ESSAY, "task": "essay"},
                   token=reg2_token, clear_rate=True)
    assert st == 429 and body.get("error") == "daily AI quota reached", \
        f"second regular user should hit daily AI total: {st} {body}"
    out["3_owner_writing_25"] = {"owner_calls": 25, "reg2_instance_429": st}

    # 4. Regular account hits 429 on speaking session #4 (3 mocks/day).
    for idx in range(1, 4):
        st, body = api("/api/speaking/turn", turn_body(f"reg-s{idx}"),
                       token=reg_token, clear_rate=True)
        assert st == 200, f"regular speaking #{idx} failed: {st} {body}"
    st, body = api("/api/speaking/turn", turn_body("reg-s4"),
                   token=reg_token, clear_rate=True)
    assert st == 429 and body.get("error") == "limit_reached" and body.get("limit") == "speaking", \
        f"regular speaking #4 should 429: {st} {body}"
    out["4_regular_speaking_429"] = {"after": 3, "status": st, "error": body.get("error")}

    # 5. Owner logs 30 speaking minutes (> 15/user and > 25/instance) and still
    # opens 3 fresh speaking sessions + mints a Live token without 429.
    for _ in range(6):
        st, body = api("/api/speaking/minute", {"seconds": 300},
                       token=owner_token, clear_rate=True)
        assert st == 200 and body.get("remaining_s", 0) > 0, (st, body)
    for sid in ("owner-s1", "owner-s2", "owner-s3"):
        st, body = api("/api/speaking/turn", turn_body(sid),
                       token=owner_token, clear_rate=True)
        assert st == 200, f"owner speaking {sid} failed: {st} {body}"
    st, tok = api("/api/speaking/token",
                  {"part": 1, "role": "examiner", "session_id": "owner-live-1"},
                  token=owner_token, clear_rate=True)
    assert st == 200 and tok.get("token") == "ephemeral-token-stub", (st, tok)

    # A fresh regular user is blocked by the daily instance speaking minute ceiling.
    st, body = api("/api/speaking/turn", turn_body("reg2-s1"),
                   token=reg2_token, clear_rate=True)
    assert st == 429 and body.get("error") == "daily speaking limit reached", \
        f"regular user should hit daily speaking minute limit: {st} {body}"
    out["5_owner_speaking_3"] = {"owner_sessions": 3, "live_mint": 200, "reg2_minutes_429": st}

    # 6. Global monthly Gemini Live budget (SPK_MONTH_MINUTES) still returns 429 for owner.
    S._spk_month_add(S.SPK_MONTH_MINUTES * 60)
    st, body = api("/api/speaking/token",
                   {"part": 1, "role": "examiner", "session_id": "owner-live-2"},
                   token=owner_token, clear_rate=True)
    assert st == 429, f"monthly guard did not block owner: {st} {body}"
    assert body.get("limit") == "voice_month", body
    assert body.get("limit_minutes") == S.SPK_MONTH_MINUTES, body
    out["6_monthly_live_guard_429"] = {
        "status": st,
        "limit": body.get("limit"),
        "limit_minutes": body.get("limit_minutes"),
    }

    srv.shutdown()
    stub_srv.shutdown()
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
