"""Offline acceptance test for custom speaking tasks, Part 2 examiner prompt, and partner contract.

Runs against an isolated server and a local Gemini + text-model stub (no network,
no secrets, no real audio):

  1. Custom exam task (UI + persistence + validation + /api/speaking/turn payload):
     - Empty, HTML, >16 items, and >300-char items are rejected on the client.
     - Valid custom task persists in D.spxCustom and localStorage['b2.spxCustom']
       across page reload, shows the "Your task" / "Tu tarea" chip on choose, brief,
       and exam screens, keeps the pasted task text intact across ES/EN switch, and
       sends the exact custom task in `task` to POST /api/speaking/turn (and token).
     - "Remove my task" clears it from D.spxCustom and localStorage across reload.
  2. Part 2 with role="examiner":
     - Upstream systemInstruction asks `prompts[1]` (or fallback preference question
       when only one prompt is given) and NEVER contains "Your partner will answer".
     - PART2_PARTNER_TURN is only used for role="partner".
  3. POST /api/speaking/partner with {question, topic, candidate_said, mode}:
     - Responds HTTP 200 with a non-empty `line`, and the upstream request payload
       includes the exact `question`.
     - `tools/speaking_smoke.py --partner` exits 0 and prints `{http, ms, line}`.

Run:
    cd tests && uv run --no-project --quiet --with playwright --with httpx python test_speaking_custom_task.py
"""
import base64
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

PARTNER_LINE = "I think school trips are brilliant, because you remember what you experience."
EXAMINER_FOLLOWUP = "What kind of trip would you enjoy most?"
TURN_TRANSCRIPT = "Both photos show people working, one at home and one in an office."
TURN_REPLY = "Thank you. Which workspace would you prefer? Why?"


class UpstreamStub(BaseHTTPRequestHandler):
    """Local stub for both Gemini turn (:generateContent) and text partner (/v1/...)."""

    gemini_bodies = []
    text_bodies = []
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
        path = self.path.split("?")[0]
        body = json.loads(raw.decode("utf-8"))
        if ":generateContent" in path:
            with self.lock:
                self.gemini_bodies.append((path, body))
            self._send_json({
                "candidates": [{
                    "content": {"parts": [{"text": json.dumps({
                        "transcript": TURN_TRANSCRIPT,
                        "reply": TURN_REPLY,
                    })}]},
                    "finishReason": "STOP",
                }]
            })
            return

        with self.lock:
            self.text_bodies.append((path, body))
        blob = raw.decode("utf-8", "replace")
        line = EXAMINER_FOLLOWUP if "speaking examiner" in blob else PARTNER_LINE
        self._send_json({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"line": line}),
                }
            }]
        })


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamStub)
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()
STUB_URL = "http://127.0.0.1:%d" % stub_srv.server_address[1]

os.environ["B2_AI_PROVIDER"] = "deepseek"
os.environ["B2_AI_BASE"] = STUB_URL + "/v1"
os.environ["B2_AI_MODEL"] = ""
os.environ["B2_AI_KEY"] = "FAKE-PARTNER-KEY"
os.environ["B2_AI_DAILY_PER_USER"] = "200"
os.environ["B2_AI_DAILY_TOTAL"] = "1000"
os.environ["B2_SPK_GOOGLE_KEY"] = "FAKE-TURN-KEY"
os.environ["B2_SPK_TURN_BASE"] = STUB_URL
os.environ["B2_SPK_TURN_MODEL"] = "gemini-2.5-flash"
os.environ["B2_SPK_TTS_MODEL"] = "gemini-2.5-flash-preview-tts"
os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "60"
os.environ["B2_SPK_MIN_DAILY_TOTAL"] = "600"
os.environ.pop("B2_SPK_LIVE", None)

from playwright.sync_api import sync_playwright  # noqa: E402
from helpers import _api, _ensure_account, isolated_server, login_owner  # noqa: E402
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


def system_text_from_gemini(body):
    parts = (body.get("systemInstruction") or {}).get("parts") or []
    return "\n".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))


def test_part2_prompts_and_api(token):
    """2. Part 2 examiner asks prompts[1] and never says 'Your partner will answer'."""
    p0 = "Compare the two photos of remote work and office work."
    p1 = "Which workspace would you prefer for your first job? Why?"
    custom_p2 = {"id": "custom-p2", "title": "Workspaces", "prompts": [p0, p1]}

    # Direct module assertions
    ex_prompt = speaking_prompts.examiner_instruction(2, custom_p2)
    assert p1 in ex_prompt, ex_prompt
    assert "Your partner will answer" not in ex_prompt, ex_prompt

    ex_lines = speaking_prompts.scripted_lines(2, custom_p2, role="examiner")
    assert p1 in ex_lines, ex_lines
    assert all("Your partner will answer" not in line for line in ex_lines), ex_lines

    pa_prompt = speaking_prompts.partner_instruction(2, custom_p2)
    assert speaking_prompts.PART2_PARTNER_TURN in pa_prompt, pa_prompt
    pa_lines = speaking_prompts.scripted_lines(2, custom_p2, role="partner")
    assert speaking_prompts.PART2_PARTNER_TURN in pa_lines, pa_lines

    # Fallback when only prompts[0] is provided
    ex_single = speaking_prompts.examiner_instruction(2, {"prompts": [p0]})
    assert "Which of these two" in ex_single and "would you prefer? Why?" in ex_single, ex_single
    assert "Your partner will answer" not in ex_single, ex_single

    # Part 3 & Part 4 coherence guards
    p3_prompt = speaking_prompts.examiner_instruction(3, {
        "topic": "A school trip abroad",
        "prompts": ["where to go", "how to travel"],
        "decision": "Which two ideas are best?",
    })
    assert "Part 1" in p3_prompt and "where to go" in p3_prompt, p3_prompt
    p4_prompt = speaking_prompts.examiner_instruction(4, {
        "questions": ["Why do you think school trips are useful for students?"],
    })
    assert "Why do you think school trips are useful for students?" in p4_prompt, p4_prompt

    # Live HTTP call to POST /api/speaking/turn (role=examiner, part=2)
    pcm = b"\x02\x00" * 16000
    UpstreamStub.gemini_bodies.clear()
    status, body = post_json("/api/speaking/turn", {
        "audio_b64": base64.b64encode(pcm).decode("ascii"),
        "mime": "audio/pcm;rate=16000",
        "part": 2,
        "role": "examiner",
        "tts": "none",
        "session_id": "custom-p2-check",
        "task": custom_p2,
        "history": [],
    }, token)
    assert status == 200, (status, body)
    assert UpstreamStub.gemini_bodies, "stub received no Gemini turn request"
    _path, sent = UpstreamStub.gemini_bodies[-1]
    sys_txt = system_text_from_gemini(sent)
    assert p0 in sys_txt, sys_txt
    assert p1 in sys_txt, sys_txt
    assert "Your partner will answer" not in sys_txt, sys_txt


def test_partner_endpoint_and_smoke(token, username, password):
    """3. /api/speaking/partner accepts real contract and passes question upstream."""
    question = "Should parents pay for school trips, or should the school pay?"
    topic = "School trips"
    said = "I think the school should help pay so every student can join."

    UpstreamStub.text_bodies.clear()
    status, body = post_json("/api/speaking/partner", {
        "question": question,
        "topic": topic,
        "candidate_said": said,
        "mode": "partner",
        "candidate_context": [],
    }, token)
    assert status == 200, (status, body)
    assert body.get("line") == PARTNER_LINE, body
    assert UpstreamStub.text_bodies, "stub received no partner request"
    _path, sent = UpstreamStub.text_bodies[-1]
    msgs = json.dumps(sent, ensure_ascii=False)
    assert question in msgs, msgs
    assert said in msgs, msgs

    # Examiner follow-up mode on the same endpoint
    status_ex, body_ex = post_json("/api/speaking/partner", {
        "question": question,
        "topic": topic,
        "candidate_said": said,
        "mode": "examiner",
        "candidate_context": ["I went on a museum trip last year."],
    }, token)
    assert status_ex == 200, (status_ex, body_ex)
    assert body_ex.get("line") == EXAMINER_FOLLOWUP, body_ex

    # tools/speaking_smoke.py --partner
    smoke_script = os.path.join(REPO, "tools", "speaking_smoke.py")
    proc = subprocess.run(
        [
            sys.executable, smoke_script,
            "--url", BASE_URL,
            "--user", username,
            "--password", password,
            "--partner",
            "--question", question,
            "--topic", topic,
            "--said", said,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    smoke_out = json.loads(proc.stdout.strip())
    assert smoke_out.get("http") == 200, smoke_out
    assert isinstance(smoke_out.get("ms"), int) and smoke_out["ms"] >= 0, smoke_out
    assert smoke_out.get("line") == PARTNER_LINE, smoke_out


def test_custom_task_ui_and_turn_payload():
    """1. Custom task UI, validation, persistence across reload, and /api/speaking/turn payload."""
    prompt_a = "Compare these two photos of cyclists in a city and hikers in the mountains."
    prompt_b = "Which of these outdoor activities would you prefer at the weekend? Why?"
    raw_task = prompt_a + "\n" + prompt_b

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
        ])
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        page_errors = []
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.goto(BASE_URL + "/app", wait_until="networkidle")
        login_owner(pg, BASE_URL + "/")
        pg.evaluate("setLang('en')")
        pg.wait_for_timeout(300)

        # Open Speaking exam -> choose screen
        pg.evaluate("SP_EXAM.open()")
        pg.wait_for_selector("#spxPanel[style*='block']", timeout=5000)
        pg.evaluate("SP_EXAM.select(2)")

        # Open "Use my own task" details panel
        assert pg.locator("#spxCustomSummary").inner_text().strip().startswith("Use my own task")
        pg.locator("#spxCustomSummary").click()
        pg.wait_for_selector("#spxCustomInput:visible", timeout=3000)

        # Validation 1: empty task -> clear error
        pg.locator("#spxCustomInput").fill("   \n  ")
        pg.locator("#spxCustomSaveBtn").click()
        err_empty = pg.locator("#spxCustomErr").inner_text().strip()
        assert err_empty, "empty custom task did not show an error"

        # Validation 2: HTML rejected
        pg.locator("#spxCustomInput").fill("<script>alert(1)</script>")
        pg.locator("#spxCustomSaveBtn").click()
        err_html = pg.locator("#spxCustomErr").inner_text().strip()
        assert "HTML" in err_html, err_html

        # Validation 3: >16 items rejected
        pg.locator("#spxCustomInput").fill("\n".join("Line %d" % i for i in range(17)))
        pg.locator("#spxCustomSaveBtn").click()
        err_max = pg.locator("#spxCustomErr").inner_text().strip()
        assert "16" in err_max, err_max

        # Validation 4: >300 chars rejected
        pg.locator("#spxCustomInput").fill("A" * 301)
        pg.locator("#spxCustomSaveBtn").click()
        err_chars = pg.locator("#spxCustomErr").inner_text().strip()
        assert "300" in err_chars, err_chars

        # Save valid custom task for Part 2
        pg.locator("#spxCustomInput").fill(raw_task)
        pg.locator("#spxCustomSaveBtn").click()
        assert pg.locator("#spxCustomErr").inner_text().strip() == ""
        assert pg.locator("#spxCustomChooseChip").is_visible()
        assert pg.locator("#spxCustomChooseChip").inner_text().strip() == "Your task"
        assert pg.locator("#spxCustomRemoveBtn").is_visible()

        stored = pg.evaluate("""() => ({
            doc: D.spxCustom && D.spxCustom['2'],
            ls: JSON.parse(localStorage.getItem('b2.spxCustom') || '{}')['2']
        })""")
        assert stored["doc"]["prompts"] == [prompt_a, prompt_b], stored
        assert stored["ls"]["prompts"] == [prompt_a, prompt_b], stored

        # Wait for sync push, then reload and verify persistence
        pg.wait_for_timeout(1200)
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(600)
        pg.evaluate("SP_EXAM.open()")
        pg.wait_for_selector("#spxPanel[style*='block']", timeout=5000)
        pg.evaluate("SP_EXAM.select(2)")
        after_reload = pg.evaluate("""() => ({
            doc: D.spxCustom && D.spxCustom['2'],
            ls: JSON.parse(localStorage.getItem('b2.spxCustom') || '{}')['2'],
            val: document.getElementById('spxCustomInput').value
        })""")
        assert after_reload["doc"]["prompts"] == [prompt_a, prompt_b], after_reload
        assert after_reload["ls"]["prompts"] == [prompt_a, prompt_b], after_reload
        assert after_reload["val"] == raw_task, after_reload

        # Switch to Spanish: chrome translates, pasted task text stays unchanged
        pg.evaluate("setLang('es')")
        pg.wait_for_timeout(200)
        assert pg.locator("#spxCustomSummary").inner_text().strip().startswith("Usar mi tarea")
        assert pg.locator("#spxCustomChooseChip").inner_text().strip() == "Tu tarea"
        assert pg.locator("#spxCustomInput").input_value() == raw_task
        pg.evaluate("setLang('en')")
        pg.wait_for_timeout(200)

        # Intercept /api/speaking/turn requests from the browser
        turn_payloads = []

        def on_request(req):
            if "/api/speaking/turn" in req.url and req.method == "POST":
                try:
                    turn_payloads.append(req.post_data_json)
                except Exception:
                    pass

        pg.on("request", on_request)

        # Start -> brief screen shows "Your task" chip
        pg.locator("#spxStartBtn").click()
        pg.wait_for_function("() => SP_EXAM.screen === 'brief'", timeout=5000)
        assert pg.locator("#spxBriefCustomChip").is_visible()
        assert pg.locator("#spxBriefCustomChip").inner_text().strip() == "Your task"

        # Ready -> exam screen shows "Your task" chip and renders custom prompts
        pg.locator("#spxReadyBtn").click()
        pg.wait_for_function("() => SP_EXAM.screen === 'exam' && SPK.running", timeout=8000)
        assert pg.evaluate("SPK.mode") == "turn", pg.evaluate("SPK.mode")
        assert pg.locator("#spxExamCustomChip").is_visible()
        assert pg.locator("#spxExamCustomChip").inner_text().strip() == "Your task"
        task_text = pg.locator("#spxTask").inner_text()
        assert prompt_a in task_text and prompt_b in task_text, task_text

        # Trigger a real turn flush on the turn transport with synthetic PCM frames
        UpstreamStub.gemini_bodies.clear()
        pg.evaluate("""() => {
            const v = SPK.voices && SPK.voices.examiner;
            if (!v || !v.transport || !v.transport.sendAudio) {
                throw new Error('turn transport not active: mode=' + SPK.mode);
            }
            SPK.speaking = false;
            SPK.lastExaminerAt = 0;
            const frame = new Int16Array(320);
            frame.fill(800);
            for (let i = 0; i < 20; i++) v.transport.sendAudio(frame, true);
            const quiet = new Int16Array(320);
            for (let i = 0; i < 45; i++) v.transport.sendAudio(quiet, false);
        }""")
        pg.wait_for_function(
            "() => SPK.lines.some(l => l.who === 'candidate')",
            timeout=10000,
        )

        audio_turns = [p for p in turn_payloads if isinstance(p, dict) and p.get("audio_b64")]
        assert audio_turns, f"no /api/speaking/turn audio payload captured: {turn_payloads}"
        sent_task = audio_turns[-1].get("task") or {}
        assert sent_task.get("id") == "custom-p2", sent_task
        assert sent_task.get("prompts") == [prompt_a, prompt_b], sent_task
        assert audio_turns[-1].get("part") == 2, audio_turns[-1]

        # Confirm the stub received the custom task and NO "Your partner will answer"
        assert UpstreamStub.gemini_bodies, "stub did not receive browser turn"
        sys_txt = system_text_from_gemini(UpstreamStub.gemini_bodies[-1][1])
        assert prompt_a in sys_txt and prompt_b in sys_txt, sys_txt
        assert "Your partner will answer" not in sys_txt, sys_txt

        # Close exam, reopen, remove custom task, verify removed across reload
        pg.evaluate("SP_EXAM.close()")
        pg.evaluate("SP_EXAM.open()")
        pg.wait_for_selector("#spxPanel[style*='block']", timeout=5000)
        pg.evaluate("SP_EXAM.select(2)")
        pg.locator("#spxCustomSummary").click()
        pg.locator("#spxCustomRemoveBtn").click()
        assert not pg.locator("#spxCustomChooseChip").is_visible()
        pg.wait_for_timeout(1200)
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(600)
        cleared = pg.evaluate("""() => ({
            doc: D.spxCustom && D.spxCustom['2'],
            ls: localStorage.getItem('b2.spxCustom')
        })""")
        assert not cleared["doc"], cleared
        assert not cleared["ls"] or "custom-p2" not in cleared["ls"], cleared

        assert page_errors == [], page_errors
        browser.close()


def main():
    username = "custom-task-user"
    password = "custom-task-pass-9"
    _ensure_account(BASE_URL + "/", username, password)
    user = _api(BASE_URL + "/", "api/login", {"name": username, "password": password})
    token = user["token"]

    test_part2_prompts_and_api(token)
    test_partner_endpoint_and_smoke(token, username, password)
    test_custom_task_ui_and_turn_payload()
    print("OK: custom speaking task, Part 2 examiner prompt, and partner contract verified")


if __name__ == "__main__":
    main()
