"""S2 acceptance: POST /api/speaking/pa against a local Azure stub.

No network, no real key: a stdlib HTTP server plays Azure Speech and records
what it receives, so the whole path (auth -> limits -> urllib -> parse) is
exercised. The fake key `FAKEKEY123` must never appear in a response, in
audit.log or in the server's own stdout log.

    python3 tests/test_speaking_pa.py
"""
import base64
import io
import json
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

FAKE_KEY = "FAKEKEY123"
USER = "pa-runner"
PASS = "pa-runner-pass-9"

AZURE_OK = {
    "RecognitionStatus": "Success",
    "Offset": 0,
    "Duration": 94000000,
    "DisplayText": "thought idea was",
    "NBest": [{
        "Confidence": 0.91,
        "PronunciationAssessment": {
            "AccuracyScore": 87.5,
            "FluencyScore": 81.0,
            "CompletenessScore": 100.0,
            "ProsodyScore": 79.2,
        },
        "Words": [
            {
                "Word": "thought",
                "PronunciationAssessment": {"AccuracyScore": 41, "ErrorType": "None"},
                "Phonemes": [
                    {"Phoneme": "th", "PronunciationAssessment": {"AccuracyScore": 71}},
                    {"Phoneme": "ao", "PronunciationAssessment": {"AccuracyScore": 38}},
                ],
            },
            {
                "Word": "idea",
                "PronunciationAssessment": {"AccuracyScore": 93, "ErrorType": "None"},
                "Phonemes": [
                    {"Phoneme": "ay", "PronunciationAssessment": {"AccuracyScore": 95}},
                ],
            },
            {
                "Word": "was",
                "PronunciationAssessment": {"AccuracyScore": 12, "ErrorType": "Omission"},
                "Phonemes": [],
            },
        ],
    }],
}

STUB = {"headers": {}, "body": b"", "calls": 0, "status": 200}


class StubHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        STUB["body"] = self.rfile.read(length) if length > 0 else b""
        STUB["headers"] = {k.lower(): v for k, v in self.headers.items()}
        STUB["calls"] += 1
        body = json.dumps(AZURE_OK).encode("utf-8")
        self.send_response(STUB["status"])
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
STUB_PORT = stub_srv.server_address[1]
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()

os.environ["B2_SPK_AZURE_KEY"] = FAKE_KEY
os.environ["B2_SPK_AZURE_REGION"] = "eastus"
os.environ["B2_SPK_AZURE_ENDPOINT"] = f"http://127.0.0.1:{STUB_PORT}"
os.environ["B2_SPK_PA_DAILY_PER_USER"] = "60"

import server as S  # noqa: E402
import store  # noqa: E402
import speech  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2pa-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.migrate_legacy()

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORT}"


def http(path, body=None, token=None, method="POST"):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def wav(seconds, rate=16000):
    """Mono 16-bit PCM silence with a correct RIFF/WAVE header."""
    data = b"\x00\x00" * int(seconds * rate)
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


def pa(audio, fmt="wav", token=None, ref_text=None):
    body = {"audio_b64": base64.b64encode(audio).decode("ascii"), "format": fmt}
    if ref_text is not None:
        body["ref_text"] = ref_text
    return http("/api/speaking/pa", body, token=token)


def reset_limits():
    S._RATE.clear()
    with S._SPK_QUOTA_LOCK:
        S._SPK_QUOTA.clear()


def register():
    st, body, _ = http("/api/register", {"name": USER, "password": PASS})
    assert st == 200, f"register failed: {st} {body}"
    return json.loads(body)["token"]


out = {}
reset_limits()
TOKEN = register()
CLIP = wav(1.0)

# 1. The PA header decodes to the verified Azure config.
cfg = json.loads(base64.b64decode(speech.pa_config_header("hello")).decode())
assert cfg["Granularity"] == "Phoneme", cfg
assert cfg["EnableProsodyAssessment"] is True, cfg
assert cfg["EnableMiscue"] is True, cfg
assert cfg["GradingSystem"] == "HundredMark", cfg
assert cfg["ReferenceText"] == "hello", cfg
out["1_config_header"] = cfg["Granularity"]

# From here on the server's stdout access/config log is captured, to prove the
# key never gets printed.
saved_stdout = sys.stdout
LOG = io.StringIO()
sys.stdout = LOG

# 2. Full path HTTP -> stub -> parse: the contract, field by field.
st, body, headers = pa(CLIP, token=TOKEN, ref_text="thought idea")
assert st == 200, f"expected 200, got {st}: {body}"
OK_BODY = body
j = json.loads(body)
assert j["ok"] is True and j["provider"] == "azure", j
assert j["accuracy"] == 87.5 and j["fluency"] == 81.0, j
assert j["completeness"] == 100 and j["prosody"] == 79.2, j
assert j["duration_s"] == 9.4, j
assert [w["w"] for w in j["words"]] == ["thought", "idea", "was"], j["words"]
assert set(j["words"][0]) == {"w", "err", "score", "phonemes"}, j["words"][0]
out["2_contract"] = True

# 3. The stub received the key, the PA config and the audio bytes verbatim.
assert STUB["headers"].get("ocp-apim-subscription-key") == FAKE_KEY, STUB["headers"]
sent_cfg = json.loads(base64.b64decode(STUB["headers"]["pronunciation-assessment"]).decode())
assert sent_cfg["ReferenceText"] == "thought idea", sent_cfg
assert STUB["headers"]["content-type"].startswith("audio/wav"), STUB["headers"]
assert STUB["body"] == CLIP, "the audio was not forwarded byte-for-byte"
out["3_upstream_headers"] = True

# 4. Phonemes survive per word.
ph = j["words"][0]["phonemes"]
assert [p["p"] for p in ph] == ["th", "ao"] and ph[1]["score"] == 38, ph
out["4_phonemes"] = ph

# 5. worst is ascending by score, capped at 5, with phonemes attached.
scores = [w["score"] for w in j["worst"]]
assert scores == sorted(scores), scores
assert j["worst"][0]["w"] == "thought" and j["worst"][0]["score"] == 41, j["worst"]
assert j["worst"][0]["phonemes"] == ph, j["worst"][0]
assert len(j["worst"]) <= 5, len(j["worst"])
out["5_worst_sorted"] = scores

# 6. Omission words are excluded from worst.
assert all(w["w"] != "was" for w in j["worst"]), j["worst"]
assert any(w["err"] == "Omission" for w in j["words"]), "fixture lost its Omission word"
out["6_omission_excluded"] = True

# 7. Base64 over 2 MB -> 413, before any upstream call.
before = STUB["calls"]
st, body, _ = http("/api/speaking/pa",
                   {"audio_b64": "A" * (2 * 1024 * 1024 + 100), "format": "wav"},
                   token=TOKEN)
assert st == 413, f"2 MB+ payload accepted: {st} {body}"
assert STUB["calls"] == before, "oversized payload reached Azure"
out["7_b64_413"] = st

# 8. 15 s of real audio -> 422 too_long (the cap is 10 s).
st, body, _ = pa(wav(15.0), token=TOKEN)
j8 = json.loads(body)
assert st == 422 and j8.get("reason") == "too_long", f"{st} {body}"
out["8_too_long_422"] = j8["reason"]

# 9. No Authorization header -> 401.
st, body, _ = pa(CLIP)
assert st == 401, f"anonymous call accepted: {st} {body}"
out["9_no_auth_401"] = st

# 10. A buffer that is not RIFF/WAVE -> 422, whatever `format` claims.
bad = b"OggS" + b"\x00" * 60
st, body, _ = pa(bad, fmt="wav", token=TOKEN)
j10 = json.loads(body)
assert st == 422 and j10.get("reason") == "container_mismatch", f"{st} {body}"
out["10_bad_container_422"] = j10["reason"]

# 11. No key configured -> 503 speech_not_configured, no Retry-After, one log line.
saved_key = S.SPK_AZURE_KEY
saved_env = os.environ.pop("B2_SPK_AZURE_KEY", None)
S.SPK_AZURE_KEY = ""
try:
    before_calls = STUB["calls"]
    disabled_before = LOG.getvalue().count("speaking/pa disabled")
    st, body, headers = pa(CLIP, token=TOKEN)
    j11 = json.loads(body)
    assert st == 503 and j11.get("error") == "speech_not_configured", f"{st} {body}"
    assert "Retry-After" not in {k.title() for k in headers}, headers
    assert STUB["calls"] == before_calls, "Azure was called without a key"
    assert LOG.getvalue().count("speaking/pa disabled") == disabled_before + 1, \
        "expected exactly one log line for the missing key"
finally:
    S.SPK_AZURE_KEY = saved_key
    if saved_env is not None:
        os.environ["B2_SPK_AZURE_KEY"] = saved_env
out["11_no_key_503"] = j11["error"]

# 12. Daily quota exhausted -> 429 with a reset date (same pattern as AI).
reset_limits()
os.environ["B2_SPK_PA_DAILY_PER_USER"] = "0"
try:
    st, body, _ = pa(CLIP, token=TOKEN)
    j12 = json.loads(body)
    assert st == 429 and "quota" in j12.get("error", ""), f"{st} {body}"
    assert "reset" in j12, j12
finally:
    os.environ["B2_SPK_PA_DAILY_PER_USER"] = "60"
out["12_daily_quota_429"] = j12.get("reset")

# 13. 30 calls/min/user allowed, the 31st -> 429 + Retry-After.
reset_limits()
codes = [pa(CLIP, token=TOKEN)[0] for _ in range(30)]
assert codes == [200] * 30, codes[-3:]
st, body, headers = pa(CLIP, token=TOKEN)
assert st == 429, f"31st call allowed: {st} {body}"
assert "Retry-After" in {k.title() for k in headers}, headers
out["13_rate_limit_429"] = st

sys.stdout = saved_stdout
server_log = LOG.getvalue()

# 14. The audio never reached the disk: no .wav anywhere under data/.
stray = []
for dirpath, _dirs, files in os.walk(_tmp):
    for fn in files:
        if fn.lower().endswith((".wav", ".ogg")):
            stray.append(os.path.join(dirpath, fn))
assert not stray, f"audio written to disk: {stray}"
out["14_no_audio_on_disk"] = True

# 15. No leak: the fake key is in no response, no audit line and no stdout log.
audit_path = os.path.join(_tmp, "audit.log")
audit_text = open(audit_path, "r", encoding="utf-8").read() if os.path.exists(audit_path) else ""
assert FAKE_KEY not in audit_text, "the Azure key leaked into audit.log"
assert FAKE_KEY not in server_log, "the Azure key leaked into the stdout log"
assert FAKE_KEY not in body, "the Azure key leaked into a response"
assert FAKE_KEY not in OK_BODY, "the Azure key leaked into the success response"
assert "audio_b64" not in audit_text and "audio_b64" not in server_log, "audio logged"
out["15_no_key_leak"] = True

srv.shutdown()
stub_srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
