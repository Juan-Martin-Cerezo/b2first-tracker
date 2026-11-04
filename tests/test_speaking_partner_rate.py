"""Backlog 24: POST /api/speaking/partner is capped at 30 calls per minute.

Boots the real server over a throwaway data dir, stubs the text model so every
call is counted and replaces `server.time` with a clock the test moves by hand.
The first 30 requests of a user must reach the model; the 31st must answer 429
without a model call, another user must keep working, and 61 s later the first
user must be allowed again. Run:

    cd tests && python3 test_speaking_partner_rate.py
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

LIMIT = 30
WINDOW_S = 60

data_dir = helpers.isolated_data_dir("b2spkpartnerrate-")
url = helpers.isolated_server({"B2_DEMO": "0"}, data_dir=data_dir)

import server as S  # noqa: E402

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else "FAIL " + str(detail or name)
    if not cond:
        failed.append(name)


calls = []


def fake_complete(system, user_block, byo=None):
    calls.append(user_block)
    return json.dumps({"line": "That is a good point."}), None


S._ai_text_complete = fake_complete
os.environ["B2_AI_KEY"] = "partner-rate-test"

# A hand-driven clock: server.py reads time.time() through its own `time`
# global, so replacing it only affects this process' server module.
real_time = S.time


class FakeClock:
    def __init__(self, now):
        self.now = now

    def time(self):
        return self.now

    def __getattr__(self, name):
        return getattr(real_time, name)


clock = FakeClock(real_time.time())
S.time = clock

token_a = S.new_token("partner-rate-a")
token_b = S.new_token("partner-rate-b")

RAW = json.dumps({"question": "Do you prefer the city or the countryside?",
                  "topic": "Cities",
                  "candidate_said": "I like living in the city.",
                  "mode": "partner"}, separators=(",", ":")).encode()


def post(token):
    req = urllib.request.Request(url + "/api/speaking/partner", data=RAW,
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, dict(res.headers), json.loads(
                res.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(
            exc.read().decode() or "{}")


statuses = []
for _ in range(LIMIT):
    status, _headers, _body = post(token_a)
    statuses.append(status)
check("R1_first_30_allowed",
      statuses == [200] * LIMIT and len(calls) == LIMIT,
      f"statuses={statuses} calls={len(calls)}")

status, headers, body = post(token_a)
check("R2_31st_is_429",
      status == 429 and body.get("error") == "too many requests",
      f"status={status} body={body}")
check("R3_429_keeps_retry_after",
      str(headers.get("Retry-After") or "").isdigit()
      and 1 <= int(headers["Retry-After"]) <= WINDOW_S + 1,
      headers.get("Retry-After"))
check("R4_429_never_calls_model",
      len(calls) == LIMIT and "line" not in body,
      f"calls={len(calls)} body={body}")

status, _headers, body = post(token_b)
check("R5_other_user_not_blocked",
      status == 200 and bool(body.get("line")) and len(calls) == LIMIT + 1,
      f"status={status} calls={len(calls)} body={body}")

clock.now += WINDOW_S + 1
status, _headers, body = post(token_a)
check("R6_window_expires",
      status == 200 and bool(body.get("line")) and len(calls) == LIMIT + 2,
      f"status={status} calls={len(calls)} body={body}")

S.time = real_time
shutil.rmtree(data_dir, ignore_errors=True)

print(json.dumps(out, ensure_ascii=False, indent=1))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print("OK: the partner endpoint allows %d calls per user per minute and then"
      " answers 429 without a model call" % LIMIT)
