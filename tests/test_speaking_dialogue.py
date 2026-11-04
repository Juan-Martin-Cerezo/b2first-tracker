"""Phase 51-52: the partner and the examiner hear the candidate.

Five checks, in order:

  1. Recognition. A stubbed Web Speech emits one sentence; the transcript shows
     it as the faded draft while the turn is open and as a normal `You:` line
     once the turn closes. The closed Part 3 dialogue (your line plus the
     partner's answer) is saved to `tests/out/dy_part3.png`.
  2. Reactive partner. The same sentence reaches the provider request body,
     together with `mode: 'partner'`.
  3. Two Part 3 exchanges. Both partner events ask the provider and both carry
     `candidate_said`; when the model returns the same line twice, the second
     reaction is a different line from the task bank, never a repeat.
  4. Server. The follow-up prompt carries the candidate's words and asks for a
     question; the partner prompt names Alex. With no key there is no call at
     all (503).
  5. Follow-up cap. Two candidate answers in the same part produce exactly one
     examiner follow-up: `SPK.followUps` stays at 1, the provider is asked once
     and the transcript prints the extra question once. The written script
     resumes. A new part gets a fresh budget.
  6. No support. With SpeechRecognition removed, the whole exam still reaches
     the report and the page raises nothing.
  7. Denied microphone. A recogniser that reports `not-allowed` shows one
     quiet note in the transcript area (both languages have the key) and the
     exam moves on to the next phase without asking for permission again.
  8. Real speech counts. The exam report prints the words and the hesitation
     markers (um, uh, like, you know) found in the recognised candidate text,
     with the per-marker breakdown, and never counts examiner or partner turns.

Run:  uv run --with playwright python test_speaking_dialogue.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

os.environ.pop("B2_AI_KEY", None)

import helpers  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT_DIR = os.path.join(TESTS, "out")
URL = helpers.isolated_server() + "/"
PHRASE = "I think living in a big city is exciting but too noisy"
PARTNER_LINE = "That sounds exciting, but I prefer the quiet."
SAME_REACTION = "That's true, cities are expensive."
P3_BANK = [
    "I would start with where to go.",
    "Maybe we should travel by coach instead.",
]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

SPEECH_STUB = r"""
window.__srLog = [];
const __PHRASE = "I think living in a big city is exciting but too noisy";
function FakeRecognition() {
  this.lang = '';
  this.continuous = false;
  this.interimResults = false;
  this.maxAlternatives = 1;
  this.onstart = null;
  this.onresult = null;
  this.onerror = null;
  this.onend = null;
  this.started = false;
}
FakeRecognition.prototype.start = function () {
  this.started = true;
  window.__srLog.push('start');
  if (this.onstart) this.onstart();
  const result = {isFinal: true, 0: {transcript: __PHRASE, confidence: 0.9}, length: 1};
  const results = [result];
  results.length = 1;
  if (this.onresult) this.onresult({resultIndex: 0, results: results});
};
FakeRecognition.prototype.stop = function () {
  this.started = false;
  window.__srLog.push('stop');
  if (this.onend) this.onend();
};
FakeRecognition.prototype.abort = FakeRecognition.prototype.stop;
try {
  Object.defineProperty(window, 'webkitSpeechRecognition', {
    configurable: true, get: function () { return FakeRecognition; }
  });
} catch (e) { window.webkitSpeechRecognition = FakeRecognition; }
try {
  Object.defineProperty(window, 'SpeechRecognition', {
    configurable: true, get: function () { return FakeRecognition; }
  });
} catch (e) { window.SpeechRecognition = FakeRecognition; }
"""

DENIED_SPEECH_STUB = r"""
window.__srLog = [];
function DeniedRecognition() {
  this.lang = '';
  this.continuous = false;
  this.interimResults = false;
  this.maxAlternatives = 1;
  this.onstart = null;
  this.onresult = null;
  this.onerror = null;
  this.onend = null;
}
DeniedRecognition.prototype.start = function () {
  const self = this;
  window.__srLog.push('start');
  setTimeout(function () {
    if (self.onstart) self.onstart();
    if (self.onerror) self.onerror({error: 'not-allowed'});
    if (self.onend) self.onend();
  }, 0);
};
DeniedRecognition.prototype.stop = function () {
  window.__srLog.push('stop');
  if (this.onend) this.onend();
};
DeniedRecognition.prototype.abort = DeniedRecognition.prototype.stop;
try {
  Object.defineProperty(window, 'webkitSpeechRecognition', {
    configurable: true, get: function () { return DeniedRecognition; }
  });
} catch (e) { window.webkitSpeechRecognition = DeniedRecognition; }
try {
  Object.defineProperty(window, 'SpeechRecognition', {
    configurable: true, get: function () { return DeniedRecognition; }
  });
} catch (e) { window.SpeechRecognition = DeniedRecognition; }
"""

NO_SPEECH_STUB = r"""
try {
  Object.defineProperty(window, 'webkitSpeechRecognition', {
    configurable: true, value: undefined
  });
} catch (e) { window.webkitSpeechRecognition = undefined; }
try {
  Object.defineProperty(window, 'SpeechRecognition', {
    configurable: true, value: undefined
  });
} catch (e) { window.SpeechRecognition = undefined; }
"""

SILENT_SPEECH_SYNTH = r"""
window.__utts = [];
const __stub = {
  speak: function (u) {
    window.__utts.push(u.text);
    try { if (u.onstart) u.onstart(); } catch (e) {}
    try { if (u.onend) u.onend(); } catch (e) {}
  },
  cancel: function () {},
  getVoices: function () { return []; },
  pause: function () {}, resume: function () {},
  speaking: false, pending: false
};
try {
  Object.defineProperty(window, 'speechSynthesis', {
    configurable: true, get: function () { return __stub; }
  });
} catch (e) { window.speechSynthesis = __stub; }
"""


def wait_until(pg, expression, timeout_s, step=100):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pg.evaluate(expression):
            return True
        pg.wait_for_timeout(step)
    return False


def open_app(p, query, init_script):
    browser = p.chromium.launch(args=[
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
    ])
    context = browser.new_context(viewport={"width": 1200, "height": 900},
                                  permissions=["microphone"])
    context.add_init_script(init_script)
    context.add_init_script(SILENT_SPEECH_SYNTH)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(URL + "app" + query, wait_until="networkidle")
    helpers.login_owner(page, URL)
    page.evaluate("localStorage.setItem('spx_test','1')")
    page.goto(URL + "app" + query, wait_until="networkidle")
    page.wait_for_timeout(350)
    helpers.dismiss_onboarding(page)
    assert page.evaluate("!!window.SPX_TEST"), "SPX_TEST was not exposed"
    return browser, page, errors


# ---------------------------------------------------------------------------
# 3. The server side (no browser): prompt selection and the no-key contract.
# ---------------------------------------------------------------------------
def test_server_prompts():
    import server as S

    calls = []

    def fake_complete(system, user_block, byo=None):
        calls.append((system, user_block))
        if "examiner" in system.lower():
            return json.dumps({"line": "Why do you think that is?"}), None
        return json.dumps({"line": "I agree, but I prefer the countryside."}), None

    S._ai_text_complete = fake_complete
    token = S.new_token("dialogue-test")

    def post(payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            URL + "api/speaking/partner", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw.decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                return exc.code, {}

    base = {
        "question": "Do you like living in a big city?",
        "topic": "Cities",
        "candidate_said": PHRASE,
    }

    os.environ["B2_AI_KEY"] = "dialogue-test-key"

    status, body = post(dict(base, mode="examiner"))
    assert status == 200, (status, body)
    assert str(body.get("line", "")).endswith("?"), body
    system, block = calls[-1]
    assert "examiner" in system.lower(), system
    assert PHRASE in block, block

    status, body = post(dict(base, mode="partner"))
    assert status == 200, (status, body)
    system, block = calls[-1]
    assert "Alex" in system, system
    assert PHRASE in block, block

    # Sanitising: newlines and control bytes never survive into the prompt.
    status, body = post({
        "question": "Do you like living in a big city?",
        "topic": "Cities",
        "candidate_said": "I think living in a big city\n\tis exciting\x00 but too noisy",
        "mode": "examiner",
    })
    assert status == 200, (status, body)
    _system, block = calls[-1]
    said_line = block.split("The candidate said:", 1)[1].split("One follow-up", 1)[0]
    assert "\n" not in said_line.strip(), block
    assert "\x00" not in block and "\t" not in said_line, block

    # No key, no BYO: refuse before touching the provider.
    os.environ.pop("B2_AI_KEY", None)
    before = len(calls)
    status, body = post(dict(base, mode="examiner"))
    assert status == 503, (status, body)
    assert len(calls) == before, calls[before:]
    print("3. server prompts: OK (examiner/partner/503)")


# ---------------------------------------------------------------------------
# 1-2. The browser: recognition, draft line, and the reactive partner.
# ---------------------------------------------------------------------------
def test_recognition_and_partner(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB)

    page.evaluate("async () => { await SP_EXAM.open(); }")

    # A deterministic candidate turn: the exam screen is open, the floor is
    # the candidate's and the turn lasts long enough to inspect the draft.
    page.evaluate("""() => {
        spxSetScreen('exam');
        SP_EXAM.part = 1;
        SP_EXAM.phases = [{key: 'spx_response', who: 'candidate', sec: 60,
                           qi: 0, prompt: 'Tell me about your city.'}];
        SP_EXAM.phase = 0;
        SP_EXAM.txShown = 0;
        document.getElementById('spxTx').replaceChildren();
        spxEnterPhase(0);
    }""")

    assert page.evaluate("SPK.heard.supported") is True, "the stub was not seen as support"
    assert wait_until(page, "SPK.heard.final.indexOf(%r)>=0" % PHRASE, 10), \
        page.evaluate("SPK.heard")
    assert page.evaluate("SPK.heard.active") is True, page.evaluate("SPK.heard")

    assert page.evaluate("document.querySelectorAll('#spxTx .spx-tx-draft').length") == 1, \
        "the open turn should show exactly one faded draft row"
    draft = page.evaluate("""() => {
        const el = document.querySelector('#spxTx .spx-tx-draft');
        return el ? el.textContent : '';
    }""")
    assert PHRASE in draft, draft

    page.evaluate("spxSpeechStop()")
    assert page.evaluate("SPK.heard.active") is False
    assert page.evaluate("document.querySelectorAll('#spxTx .spx-tx-draft').length") == 0, \
        "the draft must disappear once the turn closes"

    shown = page.evaluate("document.getElementById('spxTx').textContent")
    assert ("You: " + PHRASE) in shown, (
        shown, page.evaluate("SPK.lines"), page.evaluate("SP_EXAM.txShown"),
        page.evaluate("SPK.heard"),
        page.evaluate("document.getElementById('spxTx').innerHTML"))
    assert shown.count(PHRASE) == 1, shown

    # 2. The partner request carries what was heard and its mode.
    page.evaluate("""() => {
        window.__partnerPayload = null;
        window.__partnerLine = %r;
        SPX_TEST.partnerProvider = function (question, body) {
            window.__partnerPayload = body;
            return window.__partnerLine;
        };
        SP_EXAM.part = 3;
        spxSetScreen('exam');
        SP_EXAM.phases = [{key: 'spx_discuss', who: 'both', sec: 60, qi: 0}];
        SP_EXAM.phase = 0;
        spxPartnerTurn({prompt: 'Where would you like to live?',
                        text: 'I like the city.'});
    }""" % PARTNER_LINE)
    assert wait_until(page, "!!window.__partnerPayload", 10), "the provider was never called"
    payload = page.evaluate("window.__partnerPayload")
    assert payload.get("mode") == "partner", payload
    assert PHRASE in (payload.get("candidate_said") or ""), payload
    assert wait_until(
        page,
        "SPK.lines.some(l=>l.who==='partner'&&l.text.indexOf('That sounds exciting')===0)",
        10), page.evaluate("SPK.lines")

    # The closed Part 3 dialogue, on screen: your committed line and the
    # partner's answer, with no faded draft left behind.
    page.evaluate("spxRenderTx()")
    part3 = page.evaluate("document.getElementById('spxTx').textContent")
    assert ("You: " + PHRASE) in part3, part3
    assert ("Alex: " + PARTNER_LINE) in part3, part3
    assert page.evaluate("document.querySelectorAll('#spxTx .spx-tx-draft').length") == 0, \
        "the closed dialogue must not keep a draft row"

    os.makedirs(OUT_DIR, exist_ok=True)
    shot = os.path.join(OUT_DIR, "dy_part3.png")
    page.locator("#spxOverlay").screenshot(path=shot)
    with open(shot, "rb") as fh:
        head = fh.read(8)
    assert head == PNG_SIGNATURE, head
    assert os.path.getsize(shot) > 10000, os.path.getsize(shot)

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("1-2. recognition + reactive partner: OK")
    browser.close()


# ---------------------------------------------------------------------------
# 3. Part 3: two exchanges, both conditioned on what the candidate said.
# ---------------------------------------------------------------------------
def test_part3_two_reactions(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB)

    # One recognised candidate turn, so both reactions have something to answer.
    page.evaluate("async () => { await SP_EXAM.open(); }")
    page.evaluate("""() => {
        spxSetScreen('exam');
        SP_EXAM.part = 1;
        SP_EXAM.phases = [{key: 'spx_response', who: 'candidate', sec: 60,
                           qi: 0, prompt: 'Tell me about your city.'}];
        SP_EXAM.phase = 0;
        SP_EXAM.txShown = 0;
        document.getElementById('spxTx').replaceChildren();
        spxEnterPhase(0);
    }""")
    assert wait_until(page, "SPK.heard.final.indexOf(%s)>=0" % json.dumps(PHRASE), 10), \
        page.evaluate("SPK.heard")
    page.evaluate("spxSpeechStop()")

    # The real Part 3 phase model, with a hook that always answers the same line.
    page.evaluate("""() => {
        window.__p3 = [];
        SPX_TEST.partnerProvider = function (question, body) {
            window.__p3.push(body);
            return %s;
        };
        SP_EXAM.part = 3;
        SP_EXAM.task = {partnerLines: %s};
        SP_EXAM.phases = spxPhasesFor(3, SP_EXAM.task, 1, 'p3-two-reactions');
        SP_EXAM.phase = 1;
        SP_EXAM.partnerSaid = [];
        spxSetScreen('exam');
        window.__p3events = SP_EXAM.phases[1].events.map(function (ev) {
            return ev.who;
        });
        SP_EXAM.phases[1].events.forEach(function (ev) { spxFireEvent(ev); });
    }""" % (json.dumps(SAME_REACTION), json.dumps(P3_BANK)))

    assert page.evaluate("window.__p3events.length") == 2, \
        page.evaluate("window.__p3events")
    assert page.evaluate(
        "window.__p3events.every(function (who) { return who === 'partner'; })"), \
        page.evaluate("window.__p3events")

    assert wait_until(page, "window.__p3.length===2", 10), page.evaluate("window.__p3")
    payloads = page.evaluate("window.__p3")
    assert len(payloads) == 2, payloads
    for payload in payloads:
        assert payload.get("mode") == "partner", payload
        assert payload.get("candidate_said") == PHRASE, payload

    assert wait_until(
        page,
        "SPK.lines.filter(function (l) { return l.who === 'partner'; }).length >= 2",
        10), page.evaluate("SPK.lines")
    lines = page.evaluate(
        "SPK.lines.filter(function (l) { return l.who === 'partner'; })"
        ".map(function (l) { return l.text; })")
    assert lines[0] == SAME_REACTION, lines
    assert lines[1] != lines[0], lines
    assert lines[1] == P3_BANK[1], lines

    page.evaluate("spxRenderTx()")
    shown = page.evaluate("document.getElementById('spxTx').textContent")
    assert SAME_REACTION in shown, shown
    assert P3_BANK[1] in shown, shown
    assert shown.count(SAME_REACTION) == 1, shown

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("3. Part 3: two exchanges, both conditioned, no repeat")
    browser.close()


# ---------------------------------------------------------------------------
# 5. One examiner follow-up per part; the script resumes after it.
# ---------------------------------------------------------------------------
FOLLOW_LINE = "Why do you think that is?"
SCRIPT_LINE = "Thank you, that is the end of the questions."


def test_followup_capped(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB)

    # One recognised candidate turn, so the follow-up has something to answer.
    page.evaluate("async () => { await SP_EXAM.open(); }")
    page.evaluate("""() => {
        spxSetScreen('exam');
        SP_EXAM.part = 1;
        SP_EXAM.phases = [{key: 'spx_response', who: 'candidate', sec: 60,
                           qi: 0, prompt: 'Tell me about your city.'}];
        SP_EXAM.phase = 0;
        SP_EXAM.txShown = 0;
        document.getElementById('spxTx').replaceChildren();
        spxEnterPhase(0);
    }""")
    assert wait_until(page, "SPK.heard.final.indexOf(%s)>=0" % json.dumps(PHRASE), 10), \
        page.evaluate("SPK.heard")
    page.evaluate("spxSpeechStop()")

    # Two candidate answers in the same part, then a scripted close.
    page.evaluate("""() => {
        window.__fu = [];
        SPX_TEST.partnerProvider = function (question, body) {
            window.__fu.push({question: question, payload: body});
            return %s;
        };
        SPK.followUps = 0;
        SP_EXAM.part = 1;
        SP_EXAM.task = {topic: 'Cities'};
        SP_EXAM.phases = [
            {key: 'spx_response', who: 'candidate', sec: 60, qi: 0,
             prompt: 'Tell me about your city.'},
            {key: 'spx_response', who: 'candidate', sec: 60, qi: 1,
             prompt: 'Do you like sport?'},
            {key: 'spx_close', who: 'examiner', sec: 5, line: %s}
        ];
        SP_EXAM.phase = 0;
        SP_EXAM.followUpBusy = false;
        spxNextPhase();
    }""" % (json.dumps(FOLLOW_LINE), json.dumps(SCRIPT_LINE)))

    # The first answer earns exactly one follow-up, carrying what was heard.
    assert wait_until(page, "SPK.followUps === 1", 10), page.evaluate("SPK.followUps")
    calls = page.evaluate("window.__fu")
    assert len(calls) == 1, calls
    assert calls[0]["payload"].get("mode") == "examiner", calls[0]
    assert calls[0]["payload"].get("candidate_said") == PHRASE, calls[0]
    assert wait_until(page, "SP_EXAM.phase === 1", 10), page.evaluate("SP_EXAM.phase")

    page.evaluate("spxRenderTx()")
    shown = page.evaluate("document.getElementById('spxTx').textContent")
    assert shown.count(FOLLOW_LINE) == 1, shown

    # The second original candidate phase (index 3: the follow-up pair was
    # spliced in at 1) hits the cap, so the script moves on.
    page.evaluate("""() => {
        SP_EXAM.phase = 3;
        spxNextPhase();
    }""")
    page.wait_for_timeout(600)
    assert page.evaluate("SPK.followUps") == 1, page.evaluate("SPK.followUps")
    assert page.evaluate("window.__fu.length") == 1, page.evaluate("window.__fu")
    assert page.evaluate("SP_EXAM.phase") == 4, page.evaluate("SP_EXAM.phase")
    page.evaluate("spxRenderTx()")
    shown = page.evaluate("document.getElementById('spxTx').textContent")
    assert shown.count(FOLLOW_LINE) == 1, shown
    assert SCRIPT_LINE in shown, shown

    # A new part starts a new budget: entering it zeroes the counter and the
    # first answer there may ask again.
    page.evaluate("""() => {
        SP_EXAM.session = {full: true, seed: 1, partner: 'Alex', partnerRot: 0,
            plan: {parts: [{part: 4, task: {topic: 'Trips',
                questions: ['Would you travel alone?', 'Why?']}}]},
            partIndex: 0, turns: {examiner: 0, partner: 0, candidate: 0},
            partStats: {}, currentPart: 1};
        SP_EXAM.part = 4;
        spxEnterSessionPart(0);
        clearInterval(SP_EXAM.timer);
        SP_EXAM.timer = null;
    }""")
    assert page.evaluate("SPK.followUps") == 0, page.evaluate("SPK.followUps")
    page.evaluate("""() => {
        window.__fu = [];
        SP_EXAM.part = 4;
        SP_EXAM.phases = [
            {key: 'spx_response', who: 'candidate', sec: 30, qi: 0,
             prompt: 'Would you travel alone?'},
            {key: 'spx_close', who: 'examiner', sec: 5, line: %s}
        ];
        SP_EXAM.phase = 0;
        SP_EXAM.followUpBusy = false;
        spxNextPhase();
    }""" % json.dumps(SCRIPT_LINE))
    assert wait_until(page, "SPK.followUps === 1", 10), page.evaluate("SPK.followUps")
    assert page.evaluate("window.__fu.length") == 1, page.evaluate("window.__fu")

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("5. follow-up cap: one per part, script resumes")
    browser.close()


# ---------------------------------------------------------------------------
# 6. No Web Speech: the exam still runs to the report.
# ---------------------------------------------------------------------------
def test_no_support(p):
    browser, page, errors = open_app(p, "?spx_test=1&spk=sim", NO_SPEECH_STUB)

    assert page.evaluate("SPK.heard.supported") is False, \
        "SpeechRecognition was not actually removed"

    page.evaluate("async () => { SPX_TEST.timeScale = 0.05; await SPX_TEST.startFull(51) }")
    assert wait_until(
        page,
        "SP_EXAM.screen==='feedback' || SP_EXAM.screen==='report'", 180, step=300), \
        page.evaluate("SPX_TEST.state()")
    assert errors == [], errors
    print("4. no Web Speech: exam completed")
    browser.close()


# ---------------------------------------------------------------------------
# 7. Denied microphone: one quiet note, and the exam keeps going.
# ---------------------------------------------------------------------------
def test_mic_denied(p):
    browser, page, errors = open_app(p, "?spx_test=1", DENIED_SPEECH_STUB)

    page.evaluate("async () => { await SP_EXAM.open(); }")
    page.evaluate("""() => {
        spxSetScreen('exam');
        SP_EXAM.part = 1;
        SP_EXAM.phases = [
          {key: 'spx_response', who: 'candidate', sec: 60, qi: 0,
           prompt: 'Tell me about your city.'},
          {key: 'spx_close', who: 'examiner', sec: 5, line: 'Thank you.'}
        ];
        SP_EXAM.phase = 0;
        SP_EXAM.txShown = 0;
        document.getElementById('spxTx').replaceChildren();
        spxEnterPhase(0);
    }""")

    assert wait_until(page, "SPK.heard.error === 'not-allowed'", 10), \
        page.evaluate("SPK.heard")
    assert page.evaluate("SPK.heard.denied") is True, page.evaluate("SPK.heard")

    assert wait_until(
        page,
        "getComputedStyle(document.getElementById('spxMicNotice')).display !== 'none'",
        10), "the denied-mic notice never appeared"
    notice = page.evaluate("""() => {
        const el = document.getElementById('spxMicNotice');
        const tx = document.getElementById('spxTx');
        return {
          text: el.textContent,
          expected: t('spx_mic_denied'),
          sameSection: el.closest('[data-spx-screen="exam"]') ===
            tx.closest('[data-spx-screen="exam"]'),
          display: getComputedStyle(el).display
        };
    }""")
    assert notice["display"] == "block", notice
    assert notice["sameSection"] is True, notice
    assert notice["text"] == notice["expected"], notice
    assert "Microphone access was denied" in notice["text"], notice

    # The key exists in both dictionaries and each says it in its own language.
    keys = page.evaluate("({en: I18N.en.spx_mic_denied, es: I18N.es.spx_mic_denied})")
    assert keys["en"] and keys["es"], keys
    assert keys["en"] != keys["es"], keys

    # The exam continues on its script: the next phase runs and the page does
    # not retry the refused permission.
    assert page.evaluate("SPK.heard.active") is False, page.evaluate("SPK.heard")
    page.evaluate("spxNextPhase()")
    assert page.evaluate("SP_EXAM.phase") == 1, page.evaluate("SP_EXAM.phase")
    assert page.evaluate("SP_EXAM.screen") == "exam", page.evaluate("SP_EXAM.screen")
    page.wait_for_timeout(300)
    starts = page.evaluate("window.__srLog.filter(function (x) { return x === 'start'; }).length")
    assert starts == 1, page.evaluate("window.__srLog")
    assert page.evaluate("getComputedStyle(document.getElementById('spxMicNotice')).display") == "block"

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("7. denied microphone: quiet note, exam continues")
    browser.close()


# ---------------------------------------------------------------------------
# 8. The report counts what was said: words and the four hesitation markers.
# ---------------------------------------------------------------------------
COUNT_TURNS = [
    {"who": "candidate",
     "text": "Um, I like living here, you know, because it is close to work."},
    {"who": "examiner",
     "text": "Um, do you like it, you know, like the city?"},
    {"who": "partner", "text": "Uh, I know, like, it is noisy."},
    {"who": "candidate", "text": "Uh, the transport is cheap but it gets crowded."},
]
COUNT_WORDS = 22
COUNT_FILLERS = 4
COUNT_LINE = "Words you said: 22 · fillers: 4 (um 1 · uh 1 · like 1 · you know 1)"


def test_speech_counts(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB)

    page.evaluate("async () => { await SP_EXAM.open(); }")
    page.evaluate("""(turns) => {
        SPK.part = 1;
        SPK.lines = turns.map(function (t, i) {
            return {side: 'in', who: t.who, t: i + 1, text: t.text};
        });
        SPK.reportDuration = 120;
        SPK.reportPayload = spkBuildPayload();
        SPK.reportData = {
            bands: {grammar_vocabulary: 3, discourse_management: 3,
                    pronunciation: null, interactive_communication: null},
            metrics: SPK.reportPayload.metrics, evidence: [], fixes: []
        };
        spxFinalizeReport(SPK.reportData);
        SP_EXAM.part = 1;
        spxSetScreen('feedback');
        spxRenderFeedback();
    }""", COUNT_TURNS)

    speech = page.evaluate("SPK.reportData.speech")
    assert speech["words"] == COUNT_WORDS, speech
    assert speech["fillers"] == COUNT_FILLERS, speech
    assert speech["breakdown"] == {"um": 1, "uh": 1, "like": 1, "you know": 1}, speech

    shown = page.evaluate("document.getElementById('spxFbSpeech').textContent")
    assert shown == COUNT_LINE, shown
    assert page.evaluate(
        "getComputedStyle(document.getElementById('spxFbSpeech')).display") != "none"

    # The saved-report screen reads the same counts, not a second computation.
    page.evaluate("""() => {
        SP_EXAM.entry = {min: 2, silence_prompts: 0};
        SP_EXAM.full = false;
        spxRenderReportScreen();
    }""")
    saved = page.evaluate("document.getElementById('spxRpSpeech').textContent")
    assert saved == COUNT_LINE, saved

    # Nothing said, nothing invented.
    zero = page.evaluate("spxSpeechCounts([{who: 'candidate', text: ''}])")
    assert zero["words"] == 0 and zero["fillers"] == 0, zero
    assert zero["breakdown"] == {"um": 0, "uh": 0, "like": 0, "you know": 0}, zero

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("8. report counts: 22 words, 4 fillers, candidate turns only")
    browser.close()


def main():
    test_server_prompts()
    with sync_playwright() as p:
        test_recognition_and_partner(p)
        test_part3_two_reactions(p)
        test_followup_capped(p)
        test_no_support(p)
        test_mic_denied(p)
        test_speech_counts(p)
    print("OK: the partner reacts twice, the examiner follows up, and no support is safe")


if __name__ == "__main__":
    main()
