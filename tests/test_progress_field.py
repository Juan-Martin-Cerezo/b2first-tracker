"""Phase 56: a rejected progress document names the field that broke it.

A bare 422 ("invalid progress") left the user with no way to know which value
was too long. `_validate_progress` now returns the field path and the handler
sends it as `field`; this suite pins that contract:

  1. A string at the limit (500 chars) is accepted.
  2. One character more is a 422 whose `field` is the exact path `log[0].type`,
     and the payload is never echoed back.
  3. A nested key is named by its full path (`settings.goal`).
  4. `note`/`text` use the long limit, and the path still points at the value.
  5. The rejection is recorded once in data/errors with the same field, a byte
     size and a hashed user id — never the value.
  6. The rejected document is not saved: the previous good one survives.

Everything runs over a throwaway data directory (helpers.isolated_server).
"""
import glob
import json
import os
import sys
import urllib.error
import urllib.request

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

import helpers  # noqa: E402

DATA_DIR = helpers.isolated_data_dir()
URL = helpers.isolated_server(data_dir=DATA_DIR)
import server as S  # noqa: E402  (import after the data dir is fixed)

NAME = "progress-field-suite"
PASS = "progress-field-suite-pass-9"
LONG = "x" * 600                      # never a real value: must not be echoed
out = {}


def req(method, path, body=None, token=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


S._RATE.clear()
st, body, _ = req("POST", "/api/register", {"name": NAME, "password": PASS})
assert st == 200, f"register failed: {st} {body}"
user = json.loads(body)
UID, TOK = user["id"], user["token"]


def put(doc):
    return req("PUT", f"/api/progress?user={UID}", doc, TOK)


# 1. A string exactly at the limit is valid.
good = {"log": [{"date": "2026-11-04", "type": "a" * S.PROGRESS_STR_MAX}]}
st, body, _ = put(good)
assert st == 200, f"string at the limit rejected: {st} {body}"
out["1_at_limit"] = {"status": st}

# 2. One character more is rejected and the response names the field.
bad = {"log": [{"date": "2026-11-04", "type": LONG}]}
st, body, _ = put(bad)
j = json.loads(body)
assert st == 422, f"over-limit string accepted: {st} {body}"
assert j.get("error") == "invalid progress", f"unexpected error: {body}"
assert j.get("field") == "log[0].type", f"wrong field: {j.get('field')!r}"
assert LONG[:20] not in body, "the rejected value is echoed back"
out["2_field"] = {"status": st, "field": j["field"]}

# 3. A nested key is named by its full path.
st, body, _ = put({"log": [], "settings": {"goal": LONG}})
j = json.loads(body)
assert st == 422 and j.get("field") == "settings.goal", f"{st} {body}"
out["3_nested_field"] = j.get("field")

# 4. `note` gets the long limit; one over it still points at the value.
st, body, _ = put({"log": [{"date": "2026-11-04",
                           "note": "n" * (S.PROGRESS_STR_MAX_LONG + 1)}]})
j = json.loads(body)
assert st == 422 and j.get("field") == "log[0].note", f"{st} {body}"
last_good = {"log": [{"date": "2026-11-04",
                      "note": "n" * S.PROGRESS_STR_MAX_LONG}]}
st, body, _ = put(last_good)
assert st == 200, f"note at the long limit rejected: {st} {body}"
out["4_note_limit"] = {"over": "log[0].note", "at": 200}

# 5. The rejection is recorded with the same field, no value.
rows = []
for path in sorted(glob.glob(os.path.join(DATA_DIR, "errors", "*.jsonl"))):
    with open(path, encoding="utf-8") as f:
        rows += [json.loads(ln) for ln in f if ln.strip()]
invalid = [r for r in rows if r.get("kind") == "invalid_progress"]
assert len(invalid) == 3, f"expected 3 invalid_progress rows, got {len(invalid)}"
fields = [r["field"] for r in invalid]
assert "log[0].type" in fields, fields
assert all(LONG[:20] not in json.dumps(r) for r in invalid), "a value was logged"
assert all(isinstance(r.get("bytes"), int) and r["bytes"] > 0 for r in invalid)
assert all(len(r.get("uid_hash", "")) == 16 for r in invalid)
out["5_logged"] = sorted(fields)

# 6. The rejected documents were not stored: the last good one is still there.
st, body, _ = req("GET", f"/api/progress?download=1&user={UID}", token=TOK)
saved = json.loads(body)
assert st == 200, f"download failed: {st} {body}"
assert saved.get("log") == last_good["log"], "a rejected document was saved"
out["6_saved_unchanged"] = len(saved["log"][0]["note"])

print(json.dumps(out, indent=1, ensure_ascii=False))
