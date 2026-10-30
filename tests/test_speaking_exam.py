"""Phase 35 acceptance: the Speaking studio is a real exam simulation.

What this suite proves, in the owner's words: a task is on screen, the clock is
visible, and the examiner is a scripted role instead of a chat partner.

Everything runs against a temporary `data/` and a local text-model stub, so it
never touches the owner's account and never needs a real key:

  1. `material/speaking.json` parses, every part has the required keys, and
     every Part 2 photograph exists on disk and is served with 200.
  2. The five screens render in order (choose → brief → exam → feedback →
     report) and one screenshot per screen lands in tests/out/.
  3. The speaker indicator flips to "Your turn" only after the examiner's audio
     has ended (state, not pixels).
  4. A full Part 2 run in `?spk=sim` finishes under 200 s and produces the four
     bands; Pronunciation is null (no Azure key) and renders "not measured".
  5. Six seconds of silence issue exactly one prompt and `silence_prompts` is 1.
  6. The report lands in D.log as {type:"sp", part:2, min>=3, bands}.
  7. In Spanish there is no English chrome left (the task text is allow-listed).

    cd tests && uv run --with playwright python test_speaking_exam.py
"""
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BANK_PATH = os.path.join(REPO, "material", "speaking.json")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

MODEL_OK = {
    "bands": {
        "grammar_vocabulary": 4,
        "discourse_management": 3,
        "interactive_communication": 4,
    },
    "evidence": [
        {"scale": "grammar_vocabulary", "quote": "My name is Juan",
         "note": "simple forms used accurately"},
        {"scale": "discourse_management", "quote": "On the other hand",
         "note": "contrast marker, but the turns are short"},
        {"scale": "interactive_communication", "quote": "What do you think?",
         "note": "invites the partner instead of answering for them"},
    ],
    "fixes": [
        "Use a wider range of conditional forms in Part 3.",
        "Link ideas with more than 'and' and 'because'.",
        "Extend each answer with one concrete example.",
    ],
}


class TextModelStub(BaseHTTPRequestHandler):
    """Stand-in for DeepSeek: the report only needs a valid JSON answer."""

    def log_message(self, fmt, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        self.rfile.read(length)
        envelope = {"choices": [{"message": {"role": "assistant",
                                             "content": json.dumps(MODEL_OK)}}]}
        body = json.dumps(envelope).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), TextModelStub)
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()

os.environ["B2_AI_PROVIDER"] = "deepseek"
os.environ["B2_AI_BASE"] = "http://127.0.0.1:%d" % stub_srv.server_address[1]
os.environ["B2_AI_MODEL"] = ""
os.environ["B2_AI_KEY"] = "FAKE-EXAM-KEY"
os.environ["B2_AI_DAILY_PER_USER"] = "200"
os.environ["B2_AI_DAILY_TOTAL"] = "1000"
os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "20"

import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2spxexam-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.migrate_legacy()

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
URL = "http://127.0.0.1:%d" % srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
S._RATE.clear()

SCAN_JS = r"""
() => {
  const panel = document.getElementById('spxPanel');
  const screens = [...panel.querySelectorAll('.spx-screen')]
    .filter(el => el.classList.contains('is-on'));
  const out = [];
  screens.forEach(root => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const raw = (node.nodeValue || '').replace(/\s+/g, ' ').trim();
      if (!raw) continue;
      const el = node.parentElement;
      if (!el) continue;
      if (el.closest('[data-exam-task]')) continue;   // the exam is English on purpose
      if (el.closest('script,style')) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      out.push(raw);
    }
  });
  return {items: out, es: Object.values(I18N.es), en: Object.values(I18N.en),
          lang: LANG, screen: SP_EXAM.screen};
}
"""

ALLOW = [
    r"^Part(?:e)? \d+$", r"\bPart(?:s)? [1-4]\b", r"\bB2 First\b", r"\bCambridge\b",
    r"^\d+ min$", r"^\d+/\d+$",
]
ALLOW_RE = [re.compile(p, re.I) for p in ALLOW]

EN_MARKERS = re.compile(
    r"\b(?:the|your|you|and|with|this|that|from|what|will|happen|minutes|"
    r"examiner|partner|start|ready|save|report|close|back|turn|silence)\b", re.I)


def strip_tags(value):
    return re.sub(r"<[^>]+>", "", value).strip()


def dict_patterns(values):
    patterns = []
    for value in values:
        plain = strip_tags(value)
        if not plain:
            continue
        parts = re.split(r"\{[^}]+\}", plain)
        patterns.append(re.compile("^" + ".*?".join(re.escape(p) for p in parts) + "$", re.S))
    return patterns


def wait_until(pg, expression, timeout_s, step=100):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pg.evaluate(expression):
            return True
        pg.wait_for_timeout(step)
    return False


def get(path):
    with urllib.request.urlopen(URL + path, timeout=10) as r:
        return r.status, r.read()


def main():
    out = {}
    os.makedirs(OUT_DIR, exist_ok=True)

    # --- 1. The task bank is data, and its assets exist ---------------------
    bank = json.load(open(BANK_PATH, encoding="utf-8"))
    assert bank.get("version") == 1, bank.get("version")
    parts = bank.get("parts")
    assert isinstance(parts, list) and len(parts) == 4, parts
    required = {
        1: ("sets", ("id", "questions")),
        2: ("tasks", ("id", "photos", "title", "prompts")),
        3: ("tasks", ("id", "topic", "prompts", "decision")),
        4: ("tasks", ("id", "linkedTo", "questions")),
    }
    photo_count = 0
    for part in parts:
        n = part["part"]
        assert isinstance(part.get("minutes"), int) and part["minutes"] > 0, part
        key, fields = required[n]
        items = part.get(key)
        assert isinstance(items, list) and items, "part %s has no %s" % (n, key)
        for item in items:
            for field in fields:
                assert field in item, "part %s task %s lacks %s" % (n, item.get("id"), field)
        if n == 1:
            for q in items[0]["questions"]:
                assert q.strip().endswith("?") or q.strip().endswith("."), q
        if n == 2:
            assert 1 <= len(items[0]["prompts"]) <= 2
            for task in items:
                assert len(task["photos"]) == 2, task["id"]
                for rel in task["photos"]:
                    photo_count += 1
                    assert os.path.isfile(os.path.join(REPO, rel)), rel
                    status, body = get("/" + rel)
                    assert status == 200 and body, (rel, status)
        if n == 3:
            for task in items:
                assert len(task["prompts"]) == 5, task["id"]
        if n == 4:
            for task in items:
                assert len(task["questions"]) >= 6, task["id"]
    status, body = get("/material/speaking.json")
    assert status == 200 and json.loads(body) == bank, "served bank differs from disk"
    out["1_bank"] = {"parts": len(parts), "photos": photo_count}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright missing: cd tests && uv run --with playwright "
                         "python test_speaking_exam.py")
    from helpers import login_owner

    page_errors, console_errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
        ])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.on("console", lambda m: console_errors.append(m.text)
              if m.type == "error" else None)

        pg.goto(URL + "/?spk=sim", wait_until="networkidle")
        user = login_owner(pg, URL + "/")
        pg.evaluate("showView('hoy');selectSessionStudio('fri-b')")

        # --- 2. Choose: the part list and the single Start button ----------
        pg.evaluate("SP_EXAM.open()")
        assert wait_until(pg, "SP_EXAM.screen==='choose' && !!SP_EXAM.bank", 10), \
            "the choose screen never rendered"
        assert pg.evaluate("document.querySelectorAll('#spxDots .spx-dot').length") == 5
        assert pg.evaluate("document.querySelectorAll('#spxParts [data-part]').length") == 4
        assert pg.evaluate("document.querySelector('#spxParts [data-part=\"2\"]')"
                           ".textContent.includes('2 min') === false")
        assert "Part 2" in pg.evaluate(
            "document.querySelector('#spxParts [data-part=\"2\"]').textContent")
        assert pg.evaluate("document.querySelectorAll('#spxPanel .spx-screen.is-on').length") == 1
        assert pg.evaluate("document.querySelector('#spxDots [aria-current=\"step\"]')"
                           ".getAttribute('aria-label')") == "Choose a part"
        pg.screenshot(path=os.path.join(OUT_DIR, "spx_1_choose.png"))
        out["2_choose"] = {"parts": 4, "dots": 5}

        # Keyboard: the part cards are a radiogroup and ArrowRight moves it.
        pg.focus("[data-part='2']")
        pg.keyboard.press("ArrowRight")
        assert pg.evaluate("SP_EXAM.part") == 3, "arrow keys do not move the selection"
        pg.keyboard.press("ArrowLeft")
        assert pg.evaluate("SP_EXAM.part") == 2
        pg.click("#spxParts [data-part='2']")
        pg.click("#spxStartBtn")

        # --- 3. Brief: three bullets, timings and the one rule -------------
        assert wait_until(pg, "SP_EXAM.screen==='brief'", 5), "the brief never rendered"
        assert pg.evaluate("document.querySelectorAll('.spx-brief li').length") == 3
        rule = pg.evaluate("document.querySelector('[data-i18n=\"spx_rule\"]').textContent")
        assert "5 seconds" in rule and "English" in rule, rule
        assert "Part 2" in pg.evaluate("document.getElementById('spxBriefTime').textContent")
        pg.screenshot(path=os.path.join(OUT_DIR, "spx_2_brief.png"))
        out["3_brief"] = {"rule": rule}

        # --- 4. Exam: task on screen, clock visible, indicator live --------
        t_start = time.time()
        pg.click("#spxReadyBtn")
        assert wait_until(pg, "SP_EXAM.screen==='exam' && SPK.running===true", 20), \
            "the exam never started"
        assert pg.evaluate("SPK.mode") == "sim", pg.evaluate("SPK.mode")
        assert pg.evaluate("document.querySelectorAll('#spxTask .spx-photo img').length") == 2, \
            "the photo pair is not on screen"
        dims = pg.evaluate("""() => [...document.querySelectorAll('#spxTask img')]
            .map(i => [i.getAttribute('loading'), i.getAttribute('width'),
                       i.getAttribute('height'), i.complete])""")
        assert all(d == ["lazy", "960", "640", True] for d in dims), dims
        assert pg.evaluate("document.getElementById('spxClock').getAttribute('aria-live')") is None
        assert pg.evaluate("document.getElementById('spxWho')"
                           ".getAttribute('aria-live')") == "polite"
        assert pg.evaluate("document.querySelectorAll('#spxTask [data-q]').length") == 2, \
            "the two Part 2 prompts are not on screen"

        # The indicator is audio-derived: "Examiner speaking" while the queue is
        # busy, and "Your turn" only once it has drained.
        assert wait_until(pg, "SPK.voices.examiner.speaking===true", 20), \
            "the examiner never spoke"
        assert pg.evaluate("document.getElementById('spxWho').textContent") != "Your turn", \
            "the indicator said 'Your turn' while the examiner was still talking"
        assert wait_until(
            pg, "(SPK.voices.examiner.speaking===false) && "
                "(document.getElementById('spxWho').textContent==='Your turn')", 40), \
            "the indicator never flipped to 'Your turn' after the examiner stopped"
        assert pg.evaluate("SP_EXAM.phase") == 1, pg.evaluate("SP_EXAM.phase")
        pg.screenshot(path=os.path.join(OUT_DIR, "spx_3_exam.png"))
        out["4_exam"] = pg.evaluate(
            "({clock: document.getElementById('spxClock').textContent,"
            " who: document.getElementById('spxWho').textContent,"
            " phase: SP_EXAM.phase})")

        # --- 5. The full Part 2 run completes in under 200 s ---------------
        # The feedback screen opens before the report returns ("Marking your
        # part…"), so wait for the report itself, not just the screen.
        assert wait_until(
            pg,
            "SP_EXAM.screen==='feedback' && "
            "(!!(SPK.reportData&&SPK.reportData.bands) || SPK.lastReportError!=='')",
            200), "the exam never reached feedback"
        wall = time.time() - t_start
        assert wall < 200, "Part 2 took %.1f s" % wall
        assert pg.evaluate("SPK.lastReportError") in (None, ""), \
            pg.evaluate("SPK.lastReportError")
        bands = pg.evaluate("(SPK.reportData||{}).bands||null")
        assert bands, "the report produced no bands (duration %r s, %r turns)" % (
            pg.evaluate("(SPK.reportPayload||{}).duration_s"),
            pg.evaluate("((SPK.reportPayload||{}).transcript||[]).length"))
        assert isinstance(bands["grammar_vocabulary"], int), bands
        assert isinstance(bands["discourse_management"], int), bands
        assert isinstance(bands["interactive_communication"], int), bands
        assert bands["pronunciation"] is None, bands
        assert pg.evaluate("(SPK.reportData||{}).duration_s") >= 120, \
            pg.evaluate("(SPK.reportData||{}).duration_s")
        pronoun = pg.evaluate(
            "document.querySelectorAll('#spxFbScales .spk-scale')[2].textContent")
        assert "not measured" in pronoun, pronoun
        assert "4 / 5" in pg.evaluate(
            "document.querySelectorAll('#spxFbScales .spk-scale')[0].textContent")
        assert pg.evaluate("document.getElementById('spxFbNext').textContent.length") > 10
        pg.screenshot(path=os.path.join(OUT_DIR, "spx_4_feedback.png"))
        out["5_run"] = {"wall_s": round(wall, 1), "bands": bands,
                        "duration_s": pg.evaluate("(SPK.reportData||{}).duration_s")}

        # --- 6. Report screen + the row in D.log ---------------------------
        pg.click("#spxFbSave")
        assert wait_until(pg, "SP_EXAM.screen==='report'", 5), "the report screen never showed"
        entry = pg.evaluate("D.log.filter(e=>e.type==='sp').slice(-1)[0]")
        assert entry["type"] == "sp" and entry["part"] == 2, entry
        assert entry["min"] >= 3, entry
        assert isinstance(entry["bands"], dict) and len(entry["bands"]) == 4, entry
        assert isinstance(entry["bands"]["interactive_communication"], int), entry
        assert entry["bands"]["pronunciation"] is None, entry
        assert "silence_prompts" in entry, entry
        pg.screenshot(path=os.path.join(OUT_DIR, "spx_5_report.png"))
        # Persisted through the real sync, not only in memory.
        assert wait_until(pg, "SYNC_STATE==='ok'", 10), "the log never synced"
        saved_path = os.path.join(_tmp, "users", user["id"], "progress.json")
        deadline = time.time() + 10
        saved = None
        while time.time() < deadline:
            try:
                saved = json.load(open(saved_path, encoding="utf-8"))
                if any(e.get("type") == "sp" for e in saved.get("log", [])):
                    break
            except (OSError, ValueError):
                pass
            pg.wait_for_timeout(250)
        rows = [e for e in (saved or {}).get("log", []) if e.get("type") == "sp"]
        assert rows and rows[-1]["part"] == 2 and rows[-1]["min"] >= 3, rows[-1:]
        out["6_log"] = {"min": entry["min"], "bands": entry["bands"]}

        # --- 7. Silence: 6 s muted -> exactly one prompt -------------------
        pg.evaluate("SP_EXAM.close(); SP_EXAM.open()")
        assert wait_until(pg, "SP_EXAM.screen==='choose'", 5)
        pg.evaluate("SP_EXAM.select(1)")
        pg.click("#spxStartBtn")
        assert wait_until(pg, "SP_EXAM.screen==='brief'", 5)
        pg.evaluate("SP_EXAM.muteMic(true)")
        pg.click("#spxReadyBtn")
        assert wait_until(pg, "SP_EXAM.screen==='exam' && SP_EXAM.phase>=1", 25), \
            "the silence run never reached the candidate's turn"
        pg.wait_for_timeout(6200)
        assert pg.evaluate("SP_EXAM.silencePrompts") == 1, \
            pg.evaluate("SP_EXAM.silencePrompts")
        assert pg.evaluate("SPK.lines.filter(l=>l.who==='examiner').length") >= 2, \
            "the silence prompt never arrived"
        out["7_silence"] = {"prompts": pg.evaluate("SP_EXAM.silencePrompts")}
        pg.evaluate("SP_EXAM.close()")

        # --- 8. Spanish: no English chrome left ----------------------------
        pg.evaluate("setLang('es')")
        pg.wait_for_timeout(400)

        def scan_current(label):
            pg.wait_for_timeout(150)
            data = pg.evaluate(SCAN_JS)
            assert data["lang"] == "es", data["lang"]
            patterns = dict_patterns(data["es"])
            found = []
            for text in data["items"]:
                if len(re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]", "", text)) < 3:
                    continue
                if any(rx.match(text) for rx in ALLOW_RE):
                    continue
                if any(rx.match(text) for rx in patterns):
                    continue
                if EN_MARKERS.search(text):
                    found.append((label, text))
            return found, data["screen"]

        offenders = []
        pg.evaluate("SP_EXAM.open()")
        assert wait_until(pg, "SP_EXAM.screen==='choose'", 5)
        found, _ = scan_current("choose")
        offenders += found
        assert pg.evaluate("document.getElementById('spxStartBtn').textContent") == "Empezar"
        assert "Parte 1" in pg.evaluate(
            "document.querySelector('#spxParts [data-part=\"1\"]').textContent")
        pg.screenshot(path=os.path.join(OUT_DIR, "spx_2b_es_choose.png"))

        pg.evaluate("SP_EXAM.select(2)")
        pg.click("#spxStartBtn")
        assert wait_until(pg, "SP_EXAM.screen==='brief'", 5)
        found, _ = scan_current("brief")
        offenders += found
        brief = pg.evaluate(
            "[...document.querySelectorAll('#spxPanel .spx-screen.is-on li')]"
            ".map(el=>el.textContent)")
        assert "examinador" in brief[0].lower(), brief

        # The remaining three screens are rendered from state, not from a second
        # model call: the chrome is what this check is about.
        pg.evaluate(
            "SP_EXAM.phases=spxPhases();SP_EXAM.phase=0;"
            "spxRenderTask();spxSetScreen('exam');spxRenderClock(30);"
            "spxRenderWho();spxRenderTx();")
        found, _ = scan_current("exam")
        offenders += found
        pg.evaluate(
            "SPK.reportData={bands:{grammar_vocabulary:4,discourse_management:3,"
            "pronunciation:null,interactive_communication:4},"
            "evidence:[{scale:'grammar_vocabulary',quote:'x',note:'y'}],"
            "fixes:['fix'],derived:{pronunciation_source:'none'},duration_s:150};"
            "SP_EXAM.saved=false;SP_EXAM.entry=null;"
            "spxRenderFeedback();spxSetScreen('feedback');")
        found, _ = scan_current("feedback")
        offenders += found
        pg.evaluate("spxRenderReportScreen();spxSetScreen('report');")
        found, _ = scan_current("report")
        offenders += found
        assert not offenders, "English chrome left in ES: %r" % offenders[:5]
        out["8_es"] = {"brief": brief[0], "screens_scanned": 5}
        pg.evaluate("setLang('en')")

        assert not page_errors, "page errors: %s" % page_errors
        assert not console_errors, "console errors: %s" % console_errors
        out["9_no_console_errors"] = True

        browser.close()

    srv.shutdown()
    srv.server_close()
    stub_srv.shutdown()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("OK: phase 35 speaking exam acceptance passed")


if __name__ == "__main__":
    main()
