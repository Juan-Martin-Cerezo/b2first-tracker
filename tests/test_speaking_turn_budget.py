"""Offline regression test for the speaking turn output budget and truncation.

Proves two things against an isolated server and a local Gemini stub (no network,
no disk audio fixtures):

  1. The payload sent by POST /api/speaking/turn to Gemini requests
     maxOutputTokens >= 300, thinkingConfig.thinkingBudget == 0, and a
     responseSchema requiring both `transcript` and `reply`.
  2. A truncated upstream response (finishReason == "MAX_TOKENS" or unparseable
     JSON) is mapped to the explicit `turn_truncated` error (HTTP 422), never
     a generic 502 `upstream_failed` — while a genuinely empty response still
     returns 502 `upstream_failed`.

Run:
    cd tests && uv run --no-project --quiet --with playwright --with httpx python test_speaking_turn_budget.py
"""
import base64
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

SAMPLE_TRANSCRIPT = (
    "In my free time I usually go cycling along the river because it helps me "
    "switch off after work and stay active during the week."
)
SAMPLE_REPLY = "Cycling by the river sounds relaxing — do you go alone?"


class ProviderStub(BaseHTTPRequestHandler):
    """Local Gemini stand-in matching the test_speaking_v2.py stub pattern."""

    mode = "ok"
    bodies = []
    lock = threading.Lock()

    def log_message(self, *_a):
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length)
        with self.lock:
            self.bodies.append((self.path.split("?")[0], json.loads(raw.decode("utf-8"))))
            mode = self.mode

        if mode == "ok":
            self._send_json({
                "candidates": [{
                    "content": {"parts": [{"text": json.dumps({
                        "transcript": SAMPLE_TRANSCRIPT,
                        "reply": SAMPLE_REPLY,
                    })}]},
                    "finishReason": "STOP",
                }]
            })
            return

        if mode == "max_tokens":
            # Exact production failure: Gemini cuts off mid-JSON at MAX_TOKENS.
            self._send_json({
                "candidates": [{
                    "content": {"parts": [{"text": '{"transcript": "In my free time I usually go'}]},
                    "finishReason": "MAX_TOKENS",
                }]
            })
            return

        if mode == "max_tokens_complete_json":
            # Even if the text happens to parse, finishReason == MAX_TOKENS is truncated.
            self._send_json({
                "candidates": [{
                    "content": {"parts": [{"text": json.dumps({
                        "transcript": "In my free time",
                        "reply": "Tell me more",
                    })}]},
                    "finishReason": "MAX_TOKENS",
                }]
            })
            return

        if mode == "bad_json":
            self._send_json({
                "candidates": [{
                    "content": {"parts": [{"text": '{"transcript": "cut off without flag'}]},
                    "finishReason": "STOP",
                }]
            })
            return

        # "empty": no text part and not MAX_TOKENS -> genuine upstream_failed (502).
        self._send_json({
            "candidates": [{
                "content": {"parts": []},
                "finishReason": "STOP",
            }]
        })


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), ProviderStub)
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()
STUB_URL = "http://127.0.0.1:%d" % stub_srv.server_address[1]

os.environ["B2_SPK_GOOGLE_KEY"] = "FAKE-TURN-BUDGET-KEY"
os.environ["B2_SPK_TURN_BASE"] = STUB_URL
os.environ["B2_SPK_TURN_MODEL"] = "gemini-2.5-flash"
os.environ["B2_SPK_TTS_MODEL"] = "gemini-2.5-flash-preview-tts"
os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "60"
os.environ["B2_SPK_MIN_DAILY_TOTAL"] = "600"
os.environ.pop("B2_SPK_LIVE", None)

from helpers import _api, _ensure_account, isolated_server  # noqa: E402

BASE_URL = isolated_server()


def post_turn(token, session_id):
    pcm = b"\x01\x00" * 16000  # 1 s of synthetic 16 kHz mono PCM, no disk fixture
    payload = {
        "audio_b64": base64.b64encode(pcm).decode("ascii"),
        "mime": "audio/pcm;rate=16000",
        "part": 1,
        "role": "examiner",
        "tts": "none",
        "session_id": session_id,
        "history": [],
    }
    req = urllib.request.Request(
        BASE_URL + "/api/speaking/turn",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"raw": raw}


def main():
    _ensure_account(BASE_URL + "/", "turn-budget-user", "turn-budget-pass-9")
    user = _api(BASE_URL + "/", "api/login", {
        "name": "turn-budget-user",
        "password": "turn-budget-pass-9",
    })
    token = user["token"]

    # 1. Normal turn: inspect outgoing Gemini generationConfig & responseSchema.
    ProviderStub.mode = "ok"
    status, body = post_turn(token, "budget-ok")
    assert status == 200, (status, body)
    assert body.get("transcript") == SAMPLE_TRANSCRIPT, body
    assert body.get("reply") == SAMPLE_REPLY, body

    assert ProviderStub.bodies, "stub received no Gemini request"
    _path, sent = ProviderStub.bodies[-1]
    gen = sent.get("generationConfig") or {}
    assert isinstance(gen.get("maxOutputTokens"), int) and gen["maxOutputTokens"] >= 300, gen
    assert gen.get("thinkingConfig") == {"thinkingBudget": 0}, gen
    assert gen.get("responseMimeType") == "application/json", gen
    schema = gen.get("responseSchema") or {}
    props = schema.get("properties") or {}
    req_fields = schema.get("required") or []
    assert "transcript" in props and "reply" in props, schema
    assert "transcript" in req_fields and "reply" in req_fields, schema

    # 2. MAX_TOKENS with truncated JSON -> explicit turn_truncated (not 502).
    ProviderStub.mode = "max_tokens"
    status, body = post_turn(token, "budget-ok")
    assert status != 502, (status, body)
    assert status == 422, (status, body)
    assert body.get("error") == "turn_truncated", body
    assert body.get("reason") == "turn_truncated", body

    # 3. MAX_TOKENS even with syntactically complete JSON -> turn_truncated.
    ProviderStub.mode = "max_tokens_complete_json"
    status, body = post_turn(token, "budget-ok")
    assert status == 422, (status, body)
    assert body.get("error") == "turn_truncated", body

    # 4. Unparseable JSON without MAX_TOKENS flag -> turn_truncated (not 502).
    ProviderStub.mode = "bad_json"
    status, body = post_turn(token, "budget-ok")
    assert status == 422, (status, body)
    assert body.get("error") == "turn_truncated", body

    # 5. Genuine empty upstream body -> still 502 upstream_failed.
    ProviderStub.mode = "empty"
    status, body = post_turn(token, "budget-ok")
    assert status == 502, (status, body)
    assert body.get("error") == "turn_failed", body
    assert body.get("reason") == "upstream_failed", body

    print(json.dumps({
        "maxOutputTokens": gen["maxOutputTokens"],
        "thinkingBudget": gen["thinkingConfig"]["thinkingBudget"],
        "schema_required": req_fields,
        "truncated_status": 422,
        "truncated_error": "turn_truncated",
    }))
    print("OK: speaking turn budget and truncation mapping verified")


if __name__ == "__main__":
    main()
