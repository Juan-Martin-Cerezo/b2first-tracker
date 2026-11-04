"""Backlog 32: the README says what the product does not do.

The section is documentation, so the test checks the claims that can drift:
it exists once with the three limits the backlog asked for, and every route,
variable, path and UI string it names exists in the shipped code. The claims
are checked against the code, not just re-read from the text: no Azure key ->
503 speech_not_configured and a "not measured" band, the browser owns the
recogniser, and the model's pronunciation band is discarded.

Run: cd tests && python3 test_readme_limits.py
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(REPO, "README.md")
LANDING = os.path.join(REPO, "landing.html")
SERVER = os.path.join(REPO, "server.py")
STORE = os.path.join(REPO, "store.py")
INDEX = os.path.join(REPO, "index.html")
REPORT = os.path.join(REPO, "speaking_report.py")
BANK = os.path.join(REPO, "material", "speaking.json")

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else "FAIL " + str(detail or name)
    if not cond:
        failed.append(name)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


readme = read(README)
landing = read(LANDING)
server = read(SERVER)
store = read(STORE)
index = read(INDEX)
report = read(REPORT)

# --- 1. The section exists once, is substantial and sits where it reads ---
heads = re.findall(r"^## What it does not do$", readme, re.M)
check("section_present", len(heads) == 1, len(heads))
match = re.search(r"^## What it does not do$(.*?)(?=^## )", readme, re.M | re.S)
section = match.group(1) if match else ""
prose = re.sub(r"\s+", " ", section)
check("section_substantial", len(section) >= 800, len(section))
check("after_speaking",
      readme.find("## What it does not do") > readme.find("## The Speaking exam"))
check("before_quick_start",
      readme.find("## What it does not do") < readme.find("## Quick start"))

# --- 2. The three limits the backlog named are stated --------------------
bullets = re.findall(r"^- \*\*", section, re.M)
check("two_bullets", len(bullets) >= 2, len(bullets))
check("no_official_assessment_claim",
      "not an official" in prose and "not a certificate" in prose, prose[:200])
check("not_affiliated_claim", "not affiliated" in prose and "Cambridge" in prose)
check("landing_agrees", "It is practice, not a certificate" in landing)
check("pronunciation_limit_claim",
      "No pronunciation feedback without Azure" in prose)
check("recognition_limit_claim",
      "The live transcript depends on the browser" in prose)

# --- 3. Every repository path named in the section exists ---------------
paths = set()
for token in re.findall(r"`([^`\n]+)`", section):
    token = token.strip()
    if token.startswith("/") or "<" in token or " " in token:
        continue
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+/?", token):
        continue
    if "." not in token.rsplit("/", 1)[-1]:
        continue
    paths.add(token)
check("paths_named", bool(paths), sorted(paths))
missing = [p for p in sorted(paths) if not os.path.exists(os.path.join(REPO, p))]
check("paths_exist", not missing, missing)

# --- 4. The PA route and its Azure key are real -------------------------
check("pa_route_claim", "/api/speaking/pa" in section)
check("pa_route_served", '"/api/speaking/pa"' in server)
config = re.search(r"^## Configuration$(.*?)(?=^## )", readme, re.M | re.S)
config = config.group(1) if config else ""
check("azure_key_documented", "| `B2_SPK_AZURE_KEY` |" in config)
check("azure_key_read", '"B2_SPK_AZURE_KEY"' in server and "_spk_azure_key()" in server)

# --- 5. No key -> 503 speech_not_configured, not a guessed band ---------
check("no_key_claim", "503 speech_not_configured" in prose)
pa_disabled = server.find("speaking/pa disabled")
pa_503 = server.find('self._send_json(503, {"error": "speech_not_configured"})',
                     pa_disabled if pa_disabled >= 0 else 0)
check("pa_no_key_503", pa_disabled >= 0 and pa_503 > pa_disabled,
      "the PA handler does not answer 503 without a key")
pa_handler = server[server.find('if path == "/api/speaking/pa":'):]
key_at = pa_handler.find("_spk_azure_key()")
read_at = pa_handler.find("rfile.read")
check("pa_checks_key_before_audio",
      key_at >= 0 and 0 <= key_at < read_at,
      {"key_at": key_at, "read_at": read_at})

# --- 6. "not measured" is the UI answer, in both languages --------------
check("not_measured_claim", "not measured" in prose)
check("not_measured_en", "spx_not_measured:'not measured'" in index)
check("not_measured_es", "spx_not_measured:'no medida'" in index)
check("report_band_from_pa",
      'speaking_report.band_from_pa(clean["pa"])' in server
      and "pronunciation\": pron[\"band\"]" in server)

# --- 7. The model is told not to grade pronunciation --------------------
check("model_told_not_to_grade", "DO NOT GRADE PRONUNCIATION" in report)
check("no_worst_claim", "lists no mispronounced" in prose)
check("worst_comes_from_azure",
      '"worst": pron["worst"]' in server and '"worst": worst' in
      read(os.path.join(REPO, "speech.py")))
check("worst_empty_message", "No Azure assessment attached to this session." in index)

# --- 8. The recogniser belongs to the browser, not the app --------------
check("browser_api_claim",
      "Web Speech API" in prose and "SpeechRecognition" in prose)
check("browser_api_used",
      "window.SpeechRecognition||window.webkitSpeechRecognition" in index)
check("browser_api_gates_exam",
      "if(!h||!h.supported)return;" in index
      and "h.supported=!!(window.SpeechRecognition||window.webkitSpeechRecognition);" in index)
check("no_own_recognizer_route", "speaking/recogn" not in server)

# --- 9. Denied microphone: a note, and the exam continues --------------
check("denied_mic_claim", "deny the" in prose and "microphone" in prose)
check("denied_mic_note",
      "spx_mic_denied:'Microphone access was denied. The exam continues without speech recognition.'" in index
      and "spx_mic_denied:'Se denegó el acceso al micrófono. El examen sigue sin reconocimiento de voz.'" in index)
check("denied_mic_shown", "spxMicNotice(true)" in index)
check("script_survives", "the examiner keeps the written script" in prose)

# --- 10. "stores neither" is true of the server and the store -----------
check("stores_neither_claim", "stores neither." in prose)
check("audio_dropped", "del audio" in server)
check("store_keeps_no_audio", not re.search(r"audio|wav|ogg", store, re.I))

# --- 11. The exam bank mentioned by the section exists -------------------
bank = json.loads(read(BANK))
check("bank_parts", sorted(int(p["part"]) for p in bank["parts"]) == [1, 2, 3, 4])

print(json.dumps(out, indent=1, ensure_ascii=False))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print("ALL OK")
