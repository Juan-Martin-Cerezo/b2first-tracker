"""Phase 53: the privacy page states how Speaking recognition works.

The claim has three parts, and each one is checked against something real:

1. recognition runs in the browser — the recogniser in `index.html` is the
   browser's `SpeechRecognition`, and the function that starts it captures and
   uploads nothing;
2. no audio leaves the application — no `getUserMedia`, `MediaRecorder` or
   `fetch` in that path, and the privacy text says so;
3. the recognised text is sent only when an AI provider is configured — every
   call to the partner/examiner provider is guarded, and a server with no key
   answers `503 ai_not_configured` instead of calling a model.

Boots its own server over a temporary data dir with no key, so it never touches
`data/` and never calls the network.

    cd tests && python3 test_privacy_speaking.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

os.environ.pop("B2_AI_KEY", None)
os.environ.pop("B2_SPK_GOOGLE_KEY", None)

import helpers  # noqa: E402
import legal  # noqa: E402

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else ("FAIL " + (detail or name))
    if not cond:
        failed.append(name)


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as handle:
        return handle.read()


def js_function(script, name):
    """Return (body, start, end) of `function name(...) { ... }` by brace count."""
    start = script.index("function " + name + "(")
    i = script.index("{", start)
    depth = 0
    for j in range(i, len(script)):
        if script[j] == "{":
            depth += 1
        elif script[j] == "}":
            depth -= 1
            if depth == 0:
                return script[start:j + 1], start, j
    raise AssertionError("unbalanced braces in " + name)


doc = read("docs/PRIVACY.md")
index = read("index.html")
scripts = re.findall(r"<script[^>]*>(.*?)</script>", index, re.S)
script = max(scripts, key=len)

# ---------------------------------------------------------------------------
# 1. The document says what the item asks, inside §3 (before the third parties).
# ---------------------------------------------------------------------------
head = "**Speech recognition in the Speaking exam.**"
check("P0_section_present", head in doc)
section = doc.split(head, 1)[1].split("## 4.", 1)[0] if head in doc else ""
section = re.sub(r"\s+", " ", section)
check("P1_inside_never_stored_section",
      doc.index("## 3.") < doc.index(head) < doc.index("## 4."))
check("P2_browser_recogniser",
      "browser's own speech recogniser" in section
      and "`SpeechRecognition`" in section
      and "`webkitSpeechRecognition`" in section,
      section[:120])
check("P3_no_audio_uploaded",
      "never records your voice" in section
      and "never uploads audio" in section
      and "no audio passes through this server" in section)
check("P4_text_without_ai_stays_local",
      "With no AI provider configured, the recognised text stays in the browser"
      in section)
check("P5_text_only_with_provider",
      "only text leaves the browser" in section
      and "/api/speaking/partner" in section
      and "/api/speaking/report" in section)
check("P6_renderer_keeps_section",
      "<b>Speech recognition in the Speaking exam.</b>" in legal.render_markdown(doc)
      and "<code>SpeechRecognition</code>" in legal.render_markdown(doc))

# ---------------------------------------------------------------------------
# 2. The code the document describes: browser recognition, nothing captured.
# ---------------------------------------------------------------------------
check("C1_recognition_is_browsers",
      "window.SpeechRecognition||window.webkitSpeechRecognition" in script)
start_body, start_at, start_end = js_function(script, "spxSpeechStart")
check("C2_start_captures_nothing",
      not re.search(r"getUserMedia|MediaRecorder|XMLHttpRequest|new WebSocket|fetch\(",
                    start_body),
      "capture/upload call inside spxSpeechStart")
check("C3_recogniser_from_browser",
      "window.SpeechRecognition||window.webkitSpeechRecognition" in start_body
      and "SPX_REC=new SR()" in start_body
      and "SPX_REC.start()" in start_body)

# Every provider call must sit behind an availability guard.
calls = [m.start() for m in re.finditer(r"spxPartnerFromProvider\(", script)]
check("C4_two_guarded_call_sites", len(calls) == 3,
      f"{len(calls)} occurrences (1 definition + 2 calls expected)")
turn_body, turn_at, turn_end = js_function(script, "spxPartnerTurn")
next_body, next_at, next_end = js_function(script, "spxNextPhase")
follow_body, follow_at, follow_end = js_function(script, "spxFollowUpWanted")
check("C5_partner_turn_guarded",
      "if(!spxPartnerProviderWanted())" in turn_body
      and turn_at < calls[1] < turn_end)
check("C6_next_phase_guarded",
      "spxFollowUpWanted(ph)" in next_body
      and next_at < calls[2] < next_end
      and "return spxPartnerProviderWanted();" in follow_body)

# ---------------------------------------------------------------------------
# 3. Served page and a keyless server: no model call without a provider.
# ---------------------------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="b2privacy-")
url = helpers.isolated_server({"B2_DEMO": "0", "B2_REGISTER": "open"}, data_dir=tmp)


def request(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            raw = res.read().decode()
            try:
                parsed = json.loads(raw) if raw else None
            except ValueError:
                parsed = None
            return res.status, parsed, raw
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        return err.code, parsed, raw


status, _body, page = request("GET", "/privacy")
check("S1_served_page",
      status == 200 and "Speech recognition in the Speaking exam." in page
      and "Version 1.2" in page,
      f"{status}")
check("S2_served_says_browser",
      "browser's own speech recogniser" in page
      and "no audio passes through this server" in page)

name = "Privacy Speaking 7a1e"
password = "privacy-speaking-9!"
status, account, raw = request("POST", "/api/register", {"name": name, "password": password})
check("S3_account", status == 200 and account and account.get("token"),
      f"{status} {raw[:120]}")
token = (account or {}).get("token", "")

status, body, raw = request("GET", "/api/speaking/partner", token=token)
check("S4_partner_unavailable_without_key",
      status == 200 and body and body.get("available") is False,
      f"{status} {raw[:120]}")

status, body, raw = request(
    "POST", "/api/speaking/partner",
    {"question": "Do you play any sport?",
     "topic": "Sport",
     "candidate_said": "I play football with my friends on Sundays.",
     "mode": "partner"},
    token=token,
)
check("S5_text_not_sent_without_provider",
      status == 503 and body and body.get("error") == "ai_not_configured",
      f"{status} {raw[:120]}")

shutil.rmtree(tmp, ignore_errors=True)

print(json.dumps(out, ensure_ascii=False, indent=1))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print(f"OK {len(out)} checks")
sys.exit(0)
