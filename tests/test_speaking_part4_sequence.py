"""Offline acceptance test: Part 4 (and Part 1) examiner advances across task questions.

Runs against an isolated server and a local Gemini stub (no network, no secrets):

  - Sends POST /api/speaking/turn for Part 4 (`p4-01` "School trips") with a
    history that already contains "Why do you think school trips are useful?"
    and the candidate's full answer explaining why.
  - Verifies the outgoing Gemini `systemInstruction`:
      (a) names the next question from `task["questions"]` ("Should parents pay
          for school trips, or should the school pay?") and instructs the model
          to track asked questions in history and advance in order;
      (b) does NOT contain "Why are they useful" (and forbids rephrasing or
          asking the candidate to justify what they already explained);
      (c) keeps the 20-word-per-line limit, no praise/corrections, and the
          Part 4 closing line ("Thank you. That is the end of the speaking test.").
  - Verifies the same sequence and 20-word criteria for Part 1 (`role="examiner"`).

Run:
    cd tests && uv run --no-project --quiet --with playwright --with httpx python test_speaking_part4_sequence.py
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

NEXT_P4_QUESTION = "Should parents pay for school trips, or should the school pay?"
CANDIDATE_TRANSCRIPT = (
    "I think school trips are really useful because you remember what you see "
    "much better than what you read. Last year we visited a museum and I "
    "finally understood the history lesson."
)


class GeminiStub(BaseHTTPRequestHandler):
    """Local stub recording every Gemini :generateContent payload."""

    bodies = []
    lock = threading.Lock()

    def log_message(self, *_a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8"))
        with self.lock:
            self.bodies.append((self.path.split("?")[0], body))
        reply_text = (
            "What do you think? " + NEXT_P4_QUESTION
            if "PART 4" in json.dumps(body.get("systemInstruction") or {})
            else "What do you like most about your work or your studies?"
        )
        # Keep stub reply within 20 words, matching the prompt rule.
        assert len(reply_text.split()) <= 20, reply_text
        resp = json.dumps({
            "candidates": [{
                "content": {"parts": [{"text": json.dumps({
                    "transcript": CANDIDATE_TRANSCRIPT,
                    "reply": reply_text,
                })}]},
                "finishReason": "STOP",
            }]
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), GeminiStub)
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()
STUB_URL = "http://127.0.0.1:%d" % stub_srv.server_address[1]

os.environ["B2_SPK_GOOGLE_KEY"] = "FAKE-P4-SEQ-KEY"
os.environ["B2_SPK_TURN_BASE"] = STUB_URL
os.environ["B2_SPK_TURN_MODEL"] = "gemini-2.5-flash"
os.environ["B2_SPK_TTS_MODEL"] = "gemini-2.5-flash-preview-tts"
os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "60"
os.environ["B2_SPK_MIN_DAILY_TOTAL"] = "600"
os.environ.pop("B2_SPK_LIVE", None)

from helpers import _api, _ensure_account, isolated_server  # noqa: E402
import speaking_prompts  # noqa: E402

BASE_URL = isolated_server()


def post_json(path, payload, token):
    req = urllib.request.Request(
        BASE_URL + path,
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


def system_text(gemini_body):
    parts = (gemini_body.get("systemInstruction") or {}).get("parts") or []
    return "\n".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))


def load_p4_task(task_id="p4-01"):
    with open(os.path.join(REPO, "material", "speaking.json"), encoding="utf-8") as fh:
        bank = json.load(fh)
    p4 = [p for p in bank["parts"] if p["part"] == 4][0]
    return [t for t in p4["tasks"] if t["id"] == task_id][0]


def main():
    username = "p4-seq-user"
    password = "p4-seq-pass-9"
    _ensure_account(BASE_URL + "/", username, password)
    user = _api(BASE_URL + "/", "api/login", {"name": username, "password": password})
    token = user["token"]

    p4_task = load_p4_task("p4-01")
    assert NEXT_P4_QUESTION in p4_task["questions"], p4_task

    pcm = b"\x02\x00" * 16000
    history = [
        {"who": "examiner", "text": "Why do you think school trips are useful?"},
        {"who": "candidate", "text": CANDIDATE_TRANSCRIPT},
    ]

    GeminiStub.bodies.clear()
    status, body = post_json("/api/speaking/turn", {
        "audio_b64": base64.b64encode(pcm).decode("ascii"),
        "mime": "audio/pcm;rate=16000",
        "part": 4,
        "role": "examiner",
        "tts": "none",
        "session_id": "p4-seq-check",
        "task": p4_task,
        "history": history,
    }, token)
    assert status == 200, (status, body)
    assert GeminiStub.bodies, "stub received no Gemini turn request"

    _path, sent = GeminiStub.bodies[-1]
    sys_txt = system_text(sent)
    contents_txt = json.dumps(sent.get("contents") or [], ensure_ascii=False)

    # History travelled in contents
    assert "Why do you think school trips are useful?" in contents_txt, contents_txt
    assert CANDIDATE_TRANSCRIPT in contents_txt, contents_txt

    # (a) Next question from task["questions"] is named, with sequence tracking
    assert NEXT_P4_QUESTION in sys_txt, sys_txt
    for q in p4_task["questions"]:
        assert q in sys_txt, (q, sys_txt)
    assert "conversation history" in sys_txt.lower(), sys_txt
    assert "next unasked question" in sys_txt.lower(), sys_txt
    assert "justify" in sys_txt.lower() and "rephrase" in sys_txt.lower(), sys_txt

    # (b) Does NOT contain "Why are they useful"
    assert "why are they useful" not in sys_txt.lower(), sys_txt

    # (c) Keeps 20-word limit, no praise/corrections, and Part 4 closing formula
    assert "20 words" in sys_txt, sys_txt
    assert "no praise" in sys_txt.lower() or "never teach" in sys_txt.lower(), sys_txt
    assert "Thank you. That is the end of the speaking test." in sys_txt, sys_txt
    assert "Thank you, that is the end of Part 4." in sys_txt, sys_txt
    assert speaking_prompts.PART4_INSTRUCTION in sys_txt, sys_txt
    assert len((body.get("reply") or "").split()) <= 20, body

    # (d) _SPK_TURN_RULE itself advances Part 1/4 questions, forbids rephrasing/chaining
    # "Why?", keeps 10-word / REACT FIRST / silence rules, and leaves Part 2/3 as fallback.
    turn_rule = sys_txt[sys_txt.index("VOICE LINE, TURN BY TURN"):]
    assert "PART 1 and PART 4" in turn_rule, turn_rule
    assert "next unasked question" in turn_rule.lower(), turn_rule
    assert "never rephrase" in turn_rule.lower(), turn_rule
    assert 'never chain "why?"' in turn_rule.lower(), turn_rule
    assert "10 words" in turn_rule and "short version" in turn_rule.lower(), turn_rule
    assert "closing line" in turn_rule.lower(), turn_rule
    assert "REACT FIRST" in turn_rule, turn_rule
    assert "empty" in turn_rule.lower() and "repeat" in turn_rule.lower(), turn_rule
    assert "for part 2 and part 3" in turn_rule.lower(), turn_rule
    assert "fallback for silence" in turn_rule.lower(), turn_rule
    # Ensure the old "Bike — why is it healthier" chaining example is gone.
    assert "why is it healthier" not in turn_rule.lower(), turn_rule

    # Part 1 uses the same sequence, non-repetition, and 20-word rules
    _ensure_account(BASE_URL + "/", "p1-seq-user", password)
    p1_user = _api(BASE_URL + "/", "api/login", {"name": "p1-seq-user", "password": password})
    p1_token = p1_user["token"]
    p1_task = {
        "id": "p1-work",
        "questions": [
            "Do you work, or are you a student?",
            "What do you like most about your work or your studies?",
        ],
    }
    GeminiStub.bodies.clear()
    status1, body1 = post_json("/api/speaking/turn", {
        "audio_b64": base64.b64encode(pcm).decode("ascii"),
        "mime": "audio/pcm;rate=16000",
        "part": 1,
        "role": "examiner",
        "tts": "none",
        "session_id": "p1-seq-check",
        "task": p1_task,
        "history": [
            {"who": "examiner", "text": "Do you work, or are you a student?"},
            {"who": "candidate", "text": "I am a student at university."},
        ],
    }, p1_token)
    assert status1 == 200, (status1, body1)
    sys_p1 = system_text(GeminiStub.bodies[-1][1])
    assert p1_task["questions"][1] in sys_p1, sys_p1
    assert "next unasked question" in sys_p1.lower(), sys_p1
    assert "20 words" in sys_p1, sys_p1
    assert "Thank you, that is the end of Part 1." in sys_p1, sys_p1
    assert len((body1.get("reply") or "").split()) <= 20, body1

    # Partner contract untouched
    partner_p4 = speaking_prompts.partner_instruction(4, p4_task)
    assert "Candidate B" in partner_p4, partner_p4
    assert "Thank you. That is the end of the speaking test." not in partner_p4, partner_p4

    print("OK: Part 4 and Part 1 examiner sequence prompt verified")


if __name__ == "__main__":
    main()
