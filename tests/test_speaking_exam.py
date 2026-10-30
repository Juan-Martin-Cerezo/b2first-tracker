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

Phase 36 adds the turn-based voice contract, all against a stubbed Gemini:

  8. `GET /api/speaking/capabilities` says {live:false, turn:true} on this key.
  9. One turn round-trips: transcript + reply + a real WAV, and the measured
     stop-talking → first-audio latency is printed (flagged when > 4000 ms).
 10. A 30 s payload is refused with 413 before any decoding or upstream call.
 11. Nothing is stored: the transcript text never appears anywhere under data/.
 12. The free plan allows 1 mock a week (2nd session → 429 plan_limit); the
     owner is never limited.
 13. The UI shows the turn note and never advertises "real-time" wording.

    cd tests && uv run --with playwright python test_speaking_exam.py
"""
import base64
import json
import math
import os
import re
import struct
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


TURN_TRANSCRIPT = "It is healthier because it has less sugar."
TURN_REPLY = "What makes it healthier?"


def pcm_bytes(seconds=0.4, rate=24000):
    """Raw 16-bit mono PCM, i.e. exactly what Gemini TTS returns."""
    n = int(rate * seconds)
    return b"".join(
        struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(n))


class TextModelStub(BaseHTTPRequestHandler):
    """Stand-in for both providers: the text report and the Gemini turn path.

    The route decides the answer. `:generateContent` on the TTS model returns
    raw PCM; on the turn model it returns the JSON transcript+reply. Everything
    else is the OpenAI-shaped report the rest of the suite expects.
    """

    calls = []          # [(path, had_audio)] so a test can assert what was sent
    lock = threading.Lock()

    def log_message(self, fmt, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length)
        path = self.path.split("?")[0]
        if ":generateContent" in path:
            with self.lock:
                self.calls.append((path, b'"inlineData"' in raw))
            if "flash-preview-tts" in path:
                self._json({"candidates": [{"content": {"parts": [{
                    "inlineData": {
                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                        "data": base64.b64encode(pcm_bytes()).decode("ascii")}}]}}]})
                return
            self._json({"candidates": [{"content": {"parts": [{"text": json.dumps(
                {"transcript": TURN_TRANSCRIPT, "reply": TURN_REPLY})}]}}]})
            return
        self._json({"choices": [{"message": {"role": "assistant",
                                             "content": json.dumps(MODEL_OK)}}]})


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), TextModelStub)
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()

STUB_URL = "http://127.0.0.1:%d" % stub_srv.server_address[1]
os.environ["B2_AI_PROVIDER"] = "deepseek"
os.environ["B2_AI_BASE"] = STUB_URL
os.environ["B2_AI_MODEL"] = ""
os.environ["B2_AI_KEY"] = "FAKE-EXAM-KEY"
os.environ["B2_AI_DAILY_PER_USER"] = "200"
os.environ["B2_AI_DAILY_TOTAL"] = "1000"
os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "20"
# Phase 36: the key has no bidiGenerateContent, so Live must stay off and the
# examiner runs turn by turn against the same local stub.
os.environ["B2_SPK_GOOGLE_KEY"] = "FAKE-TURN-KEY"
os.environ["B2_SPK_TURN_BASE"] = STUB_URL
os.environ["B2_SPK_TURN_MODEL"] = "gemini-2.5-flash"
os.environ["B2_SPK_TTS_MODEL"] = "gemini-2.5-flash-preview-tts"
os.environ.pop("B2_SPK_LIVE", None)

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

    # --- 8-12. Phase 36: the turn-based voice contract ---------------------
    def api(path, payload=None, token=None, timeout=25):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(URL + path, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST" if payload is not None else "GET")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw.decode("utf-8")) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return e.code, {}

    def turn_body(session, seconds=1.0, **extra):
        pcm = b"\x01\x00" * int(16000 * seconds)
        body = {
            "audio_b64": base64.b64encode(pcm).decode("ascii"),
            "mime": "audio/pcm;rate=16000",
            "part": 2,
            "role": "examiner",
            "history": [{"who": "candidate", "text": "I think the first one."}],
            "task_id": "p2-1",
            "session_id": session,
        }
        body.update(extra)
        return body

    owner_token = S.new_token("owner")

    status, caps = api("/api/speaking/capabilities", token=owner_token)
    assert status == 200, (status, caps)
    assert caps == {"live": False, "turn": True}, caps
    out["8_capabilities"] = caps

    before_calls = len(TextModelStub.calls)
    status, turn = api("/api/speaking/turn", turn_body("api-owner-1"), owner_token)
    assert status == 200, (status, turn)
    assert turn.get("transcript") == TURN_TRANSCRIPT, turn.get("transcript")
    assert turn.get("reply") == TURN_REPLY, turn.get("reply")
    assert turn.get("mime") == "audio/wav", turn.get("mime")
    wav = base64.b64decode(turn.get("audio_b64") or "")
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE", wav[:16]
    assert len(wav) > 44, len(wav)
    ms = turn.get("ms") or {}
    assert all(isinstance(ms.get(k), int) and ms[k] >= 0 for k in ("stt", "llm", "tts")), ms
    total = ms.get("total")
    assert isinstance(total, int) and total >= 0, ms
    print("turn latency (server ms, stubbed): %r" % ms)
    assert total < 4000, "a turn took %d ms — over the 4 s ceiling" % total
    # One upload with audio, one TTS call, and no second model round trip.
    new_calls = TextModelStub.calls[before_calls:]
    assert any(had for _p, had in new_calls), new_calls
    assert any(not had for _p, had in new_calls), new_calls
    out["9_turn_roundtrip"] = {"ms": ms, "wav_bytes": len(wav)}

    # The controller line: TTS only, no candidate audio, no model call.
    before_calls = len(TextModelStub.calls)
    status, said = api("/api/speaking/turn",
                       {"say": "Good morning. Can you tell me your name, please?",
                        "part": 2, "role": "examiner", "session_id": "api-owner-1"},
                       owner_token)
    assert status == 200, (status, said)
    assert said.get("reply") == "Good morning. Can you tell me your name, please?", said
    assert said.get("transcript") == "", said
    assert base64.b64decode(said.get("audio_b64") or "")[:4] == b"RIFF"
    assert len(TextModelStub.calls) == before_calls + 1, TextModelStub.calls[before_calls:]
    assert not TextModelStub.calls[-1][1], "the say path uploaded audio"

    # --- 10. A 30 s payload is refused before any decode or upstream call ---
    before_calls = len(TextModelStub.calls)
    status, body = api("/api/speaking/turn", turn_body("api-owner-2", seconds=30.0),
                       owner_token)
    assert status == 413, (status, body)
    assert len(TextModelStub.calls) == before_calls, "a rejected payload reached Gemini"
    out["10_413"] = {"status": status, "error": body.get("error")}

    # --- 12. Quota: free is 1 mock a week, the owner is never limited -------
    from helpers import _ensure_account, _api

    _ensure_account(URL + "/", "turn-free", "turn-free-pass-9")
    free = _api(URL + "/", "api/login",
                {"name": "turn-free", "password": "turn-free-pass-9"})
    free_token = free["token"]
    status, body = api("/api/speaking/turn", turn_body("free-a"), free_token)
    assert status == 200, (status, body)
    status, body = api("/api/speaking/turn", turn_body("free-b"), free_token)
    assert status == 429, (status, body)
    assert body.get("error") == "plan_limit" and body.get("limit") == "speaking", body
    assert body.get("plan") == "free" and body.get("unlock") == "pro", body
    for session in ("owner-a", "owner-b", "owner-c"):
        status, body = api("/api/speaking/turn", turn_body(session), owner_token)
        assert status == 200, "owner was limited on %s: %r %r" % (session, status, body)
    out["12_quota"] = {"second_free": 429, "owner_sessions": 3}

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

        # --- 9b. The same turn through the real client transport -----------
        caps = pg.evaluate("spkCapabilities(true)")
        assert caps == {"live": False, "turn": True}, caps
        pg.evaluate("""
            () => {
              SPK.running=true;SPK.mode='turn';SPK.muted=false;SPK.speaking=false;
              SPK.lines=[];SPK.turns=[];SPK.turnState='';SPK.turnLatencyMs=null;
              spkEnsureCtx();
              const v=spkVoice('examiner');
              v.transport=makeTurnTransport({mode:'turn',role:'examiner',part:2,
                on:spkHandlers('examiner'),session_id:'browser-turn-1'});
              v.offline=false;v.muted=null;v.gainLevel=null;
              v.transport.start();
              return true;
            }
        """)
        audio_before = pg.evaluate("SPK.ctx.currentTime")
        # 1.2 s of speech then 1 s of silence: exactly what the VAD produces.
        pg.evaluate("""
            () => {
              const v=SPK.voices.examiner;
              const frame=new Int16Array(320);
              for(let i=0;i<frame.length;i++){
                frame[i]=Math.round(Math.sin(2*Math.PI*300*i/16000)*8000);
              }
              for(let k=0;k<60;k++)v.transport.sendAudio(frame,true);
              const quiet=new Int16Array(320);
              for(let k=0;k<50;k++)v.transport.sendAudio(quiet,false);
              return true;
            }
        """)
        assert wait_until(pg, "SPK.turnLatencyMs!==null", 20), "the turn never came back"
        assert pg.evaluate("SPK.turnError") in (None, ""), pg.evaluate("SPK.turnError")
        lines = pg.evaluate("SPK.lines.map(l=>({who:l.who,text:l.text}))")
        assert {"who": "candidate", "text": TURN_TRANSCRIPT} in lines, lines
        assert {"who": "examiner", "text": TURN_REPLY} in lines, lines
        assert pg.evaluate("SPK.voices.examiner.nextTime") > audio_before + 0.3, \
            "the reply WAV never reached the playback queue"
        pg.evaluate("SP_EXAM.txShown=0;spxRenderTx()")
        hud = pg.evaluate("document.getElementById('spxTx').textContent")
        assert TURN_TRANSCRIPT in hud and TURN_REPLY in hud, hud
        latency = pg.evaluate("SPK.turnLatencyMs")
        print("turn latency (client, stop-talking -> first audio): %d ms" % latency)
        out["9b_client_turn"] = {"latency_ms": latency,
                                 "server_ms": pg.evaluate("SPK.lastTurnMs")}

        # A failed request is said plainly, never passed off as an answer, and
        # the same turn can be retried without recording it again.
        pg.evaluate("""
            () => {
              SPK.examMode=true;SPK.turnState='';SPK.turnError='';
              SPK.lines=[];SPK.turns=[];
              SPK.__fetch=window.fetch;
              window.fetch=function(){return Promise.reject(new Error('network down'))};
              const v=SPK.voices.examiner;
              const frame=new Int16Array(320);
              for(let k=0;k<20;k++)v.transport.sendAudio(frame,true);
              for(let k=0;k<45;k++)v.transport.sendAudio(frame,false);
              return true;
            }
        """)
        assert wait_until(pg, "SPK.turnError!==''", 10), "the failure was swallowed"
        assert pg.evaluate("SPK.lines.length") == 0, \
            "a failed turn invented a transcript line"
        assert pg.evaluate(
            "document.getElementById('spxVoiceRetry').style.display") != "none", \
            "no retry was offered after a failed turn"
        pg.evaluate("window.fetch=SPK.__fetch;SPK.retryTurn()")
        assert wait_until(pg, "SPK.turnError===''", 15), "the retry never completed"
        assert pg.evaluate(
            "document.getElementById('spxVoiceRetry').style.display") == "none", \
            "the retry button stayed after a successful retry"
        out["9c_failure_retry"] = True

        # Back to a clean slate for the simulated exam below.
        pg.evaluate("""
            () => {
              SPK.running=false;SPK.turnState='';SPK.mode='sim';
              SPK.turnLatencyMs=null;SPK.lastTurnMs=null;spkReset();
              document.getElementById('spxTx').replaceChildren();
              return true;
            }
        """)
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
            "SPK.mode='turn';spxRenderVoiceMode();"
            "SP_EXAM.phases=spxPhases();SP_EXAM.phase=0;"
            "spxRenderTask();spxSetScreen('exam');spxRenderClock(30);"
            "spxRenderWho();spxRenderTx();")
        found, _ = scan_current("exam")
        offenders += found
        # The honest wording: turn-based and upload-on-stop, never "real-time".
        panel_text = pg.evaluate("document.getElementById('spxPanel').textContent")
        assert not re.search(r"real[\s-]?time|tiempo real|full[\s-]?duplex",
                             panel_text, re.I), \
            "the UI advertises real-time voice without Live access"
        note = pg.evaluate("document.getElementById('spxTurnNote')")
        assert note is not None, "the turn note is missing"
        note_state = pg.evaluate(
            "({text: document.getElementById('spxTurnNote').textContent,"
            " shown: getComputedStyle(document.getElementById('spxTurnNote')).display})")
        assert note_state["shown"] != "none", note_state
        assert "turnos" in note_state["text"].lower(), note_state
        out["13_turn_note"] = note_state
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

    # --- 11. Nothing was stored: no transcript anywhere under data/ ---------
    # The turn payloads lived in memory only. This greps every byte the server
    # wrote during the whole suite, including the meter and the audit chain.
    blob = b""
    for dirpath, _dirs, files in os.walk(_tmp):
        for name in files:
            try:
                with open(os.path.join(dirpath, name), "rb") as f:
                    blob += b"\n" + f.read()
            except OSError:
                pass
    for needle in (TURN_TRANSCRIPT, TURN_REPLY, "I think the first one."):
        assert needle.encode("utf-8") not in blob, "the server stored %r" % needle
    assert b"FAKE-TURN-KEY" not in blob, "the provider key reached disk"
    out["11_no_storage"] = {"bytes_scanned": len(blob)}

    srv.shutdown()
    srv.server_close()
    stub_srv.shutdown()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("OK: phase 36 speaking exam acceptance passed (turn-based voice)")


if __name__ == "__main__":
    main()
