"""Backlog 15: POST /api/speaking/partner refuses bodies over 8000 bytes.

Boots the real server over a throwaway data dir, stubs the text model so every
call is counted, and posts valid JSON bodies of exactly 8000 and 8001 bytes.
The 8000 one must reach the model; anything larger must get a 413 without a
single model call. Run:

    cd tests && python3 test_speaking_partner_limit.py
"""
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

import helpers  # noqa: E402

LIMIT = 8000

data_dir = helpers.isolated_data_dir("b2spkpartner-")
url = helpers.isolated_server({"B2_DEMO": "0"}, data_dir=data_dir)

import server as S  # noqa: E402

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else "FAIL " + str(detail or name)
    if not cond:
        failed.append(name)


def body_of_size(total):
    """A valid partner request whose encoded body is exactly `total` bytes."""
    payload = {"question": "", "topic": "Cities",
               "candidate_said": "I like living in the city.",
               "mode": "partner"}
    base = len(json.dumps(payload, separators=(",", ":")).encode())
    payload["question"] = "q" * (total - base)
    raw = json.dumps(payload, separators=(",", ":")).encode()
    assert len(raw) == total, (len(raw), total)
    return raw


calls = []


def fake_complete(system, user_block, byo=None):
    calls.append(user_block)
    return json.dumps({"line": "That is a good point."}), None


S._ai_text_complete = fake_complete
os.environ["B2_AI_KEY"] = "partner-limit-test"
token = S.new_token("partner-limit-test")


def post(raw):
    req = urllib.request.Request(url + "/api/speaking/partner", data=raw,
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


status, body = post(body_of_size(LIMIT))
check("P1_limit_reaches_model",
      status == 200 and body.get("line") and len(calls) == 1,
      f"status={status} calls={len(calls)} body={body}")

status, body = post(body_of_size(LIMIT + 1))
check("P2_one_byte_over_413",
      status == 413 and body.get("error") == "payload too large",
      f"status={status} body={body}")
check("P3_over_limit_never_calls_model",
      len(calls) == 1 and "line" not in body,
      f"calls={len(calls)} body={body}")

status, body = post(body_of_size(64 * 1024))
check("P4_large_body_413", status == 413, f"status={status} body={body}")
check("P5_large_body_never_calls_model", len(calls) == 1, f"calls={len(calls)}")

shutil.rmtree(data_dir, ignore_errors=True)

print(json.dumps(out, ensure_ascii=False, indent=1))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print("OK: the partner endpoint caps its body at %d bytes before the model"
      % LIMIT)
