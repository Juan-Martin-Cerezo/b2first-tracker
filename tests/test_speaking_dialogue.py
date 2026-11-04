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
  9. Keyboard. The transcript is a polite live region, Space mutes and unmutes
     the microphone with real key presses, and Escape asks before leaving a
     part that is in progress (dismiss keeps the exam, accept closes it).
     Outside a part, Escape closes without asking.
  10. Accessibility. Every overlay button carries an aria-label that follows
      the language switch, Tab and Shift+Tab stay inside the open dialog, and
      every visible button is at least 44x44 px.
  11. No repeated partner line. The Part 4 script asks the partner four times
       from a three-line task bank; the session says four different lines, and
       the memory of what was said survives the change of part.
  12. Mobile. At 380x740 the overlay fits without sideways scrolling, Part 2
       stacks its two photographs, the panel scrolls, every visible button is
       inside the viewport, and the end-of-part button can be scrolled to and
       pressed. The state is saved to `tests/out/dy_mobile.png`.
  13. Part 4 context. The examiner's follow-up carries the last three answers
       the candidate already gave, oldest first, never the fourth-oldest; a new
       answer pushes the window forward. Checked inside the follow-up test.
  14. One turn, one story. Across a whole Part 3 the phase title and the green
       turn badge name the same speaker in every frame; a phase that carries a
       key belonging to someone else falls back to the floor's own label
       instead of printing a contradictory title.
  15. Report transcript. The saved report prints every line of the session
       (you, the partner and the examiner) and its Copy button writes that
       same plain text to the clipboard, in both languages, with no request
       to the server.
  16. Saved measurements. The `sp` row written to D.log carries the words and
        hesitation markers recognised in the session and the seconds and turns
        of every part in the plan, with no score when no band was measured.
  17. Part 1 silence. A candidate who never starts keeps the question open:
        past 15 s the examiner repeats the same written bank question once
        (never twice) and only then does the script move to the next one.
  18. Honest brief. Before the part starts, the brief says where the partner's
        answers come from: written lines from the task bank with nothing sent
        to an AI provider, or AI-generated lines that send the task question
        and what you say to the provider. Both statements exist in English and
        Spanish, and the probe's real answer repaints an open brief.

Run:  uv run --with playwright python test_speaking_dialogue.py
"""
import json
import os
import struct
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
OWNER_SESSION = {}

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


def open_app(p, query, init_script, reuse_login=False):
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
    # The server allows 10 logins per 10 minutes per IP and this suite already
    # uses all of them, so a later test can adopt the session an earlier one
    # opened instead of asking for another. A standalone run logs in normally.
    if reuse_login and OWNER_SESSION:
        page.evaluate("localStorage.setItem('b2first_user', %s)"
                      % json.dumps(json.dumps(OWNER_SESSION)))
        page.reload(wait_until="networkidle")
    else:
        OWNER_SESSION.clear()
        OWNER_SESSION.update(helpers.login_owner(page, URL))
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

    # Phase 52: the examiner gets the earlier answers, oldest first, never more
    # than the last three, and still sees the current turn on its own line.
    earlier = ["EARLIER-ONE", "EARLIER-TWO", "EARLIER-THREE",
               "EARLIER-FOUR", "EARLIER-FIVE"]
    status, body = post(dict(base, mode="examiner", candidate_context=earlier))
    assert status == 200, (status, body)
    _system, block = calls[-1]
    for line in ("EARLIER-THREE", "EARLIER-FOUR", "EARLIER-FIVE"):
        assert line in block, block
    for line in ("EARLIER-ONE", "EARLIER-TWO"):
        assert line not in block, block
    assert block.index("EARLIER-THREE") < block.index("EARLIER-FOUR") \
        < block.index("EARLIER-FIVE"), block
    assert PHRASE in block, block

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
# 4b. No written partner line twice in one session.
# ---------------------------------------------------------------------------
P4_BANK = [
    "I would start with the cost, because that decides the rest.",
    "And the journey matters too, since a long trip tires everybody.",
    "So let us put both options side by side before we choose.",
]
FRESH_LINE = "A fresh answer for the next part, not said before."


def test_partner_no_repeat(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB)

    page.evaluate("async () => { await SP_EXAM.open(); }")

    # The real Part 4 script: the partner is asked four times and the bank of
    # the task holds three lines, so the fourth scripted turn wraps onto the
    # first one. The session has to answer with an unused variant instead.
    first = page.evaluate("""() => {
        spxSetScreen('exam');
        SP_EXAM.part = 4;
        SP_EXAM.task = {partnerLines: %s};
        SP_EXAM.partnerSaid = [];
        SP_EXAM.partnerIdx = 0;
        const phases = spxPhasesFor(4, SP_EXAM.task, 1, 'nr-part4');
        const partner = phases.filter(function (ph) { return ph.who === 'partner'; });
        partner.forEach(function (ph) {
            spxFireEvent({who: 'partner', text: ph.line, prompt: ph.prompt});
        });
        return {
            scripted: partner.map(function (ph) { return ph.line; }),
            lines: SPK.lines.filter(function (l) { return l.who === 'partner'; })
                .map(function (l) { return l.text; }),
            pool: spxPartnerPool(SP_EXAM.task),
            said: SP_EXAM.partnerSaid.slice()
        };
    }""" % json.dumps(P4_BANK))

    assert len(first["scripted"]) == 4, first
    assert len(set(first["scripted"])) == 3, (
        "the script itself should repeat once: %s" % first["scripted"])

    assert len(first["lines"]) == 4, first
    assert len(set(first["lines"])) == 4, (
        "the partner repeated a written line: %s" % first["lines"])
    for i in range(3):
        assert first["lines"][i] != first["lines"][i + 1], first
    assert first["lines"][:3] == P4_BANK, first
    assert first["lines"][3] in first["pool"], first
    assert first["said"] == first["lines"], first

    page.evaluate("spxRenderTx()")
    shown = page.evaluate("document.getElementById('spxTx').textContent")
    for line in first["lines"]:
        assert shown.count(line) == 1, (line, shown)

    # A new part continues the same session: what was already said stays known,
    # so the same line cannot come back at the start of the next part.
    second = page.evaluate("""() => {
        const used = SP_EXAM.partnerSaid.slice();
        SP_EXAM.partnerRot = 0;
        SP_EXAM.session = {full: true, partIndex: 0,
            plan: {parts: [
                {part: 4, task: {partnerLines: %s}, taskId: 'nr-a'},
                {part: 4, task: {partnerLines: %s}, taskId: 'nr-b'}
            ]},
            turns: {examiner: 0, partner: 0, candidate: 0}, partStats: {}};
        spxEnterSessionPart(1);
        const kept = SP_EXAM.partnerSaid.slice();
        spxPartnerTurn({prompt: 'Would you go again?', text: %s});
        const said = SPK.lines.filter(function (l) { return l.who === 'partner'; })
            .map(function (l) { return l.text; });
        return {used: used, kept: kept, last: said[said.length - 1]};
    }""" % (json.dumps(P4_BANK), json.dumps([P4_BANK[0], FRESH_LINE]),
            json.dumps(P4_BANK[0])))

    assert second["kept"] == second["used"], (
        "a part change forgot what the partner already said: %s" % second)
    assert second["last"] != P4_BANK[0], second
    assert second["last"] == FRESH_LINE, second

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("4b. no repeated partner line, not even across parts")
    browser.close()


# ---------------------------------------------------------------------------
# 5. One examiner follow-up per part; the script resumes after it. The Part 4
#    follow-up also carries the last three answers already in the transcript.
# ---------------------------------------------------------------------------
FOLLOW_LINE = "Why do you think that is?"
SCRIPT_LINE = "Thank you, that is the end of the questions."
P4_EARLIER = [
    "I usually travel by train because airports are stressful.",
    "My last holiday was a week in the mountains with friends.",
    "I would like to try travelling alone next summer.",
    "The cost matters more than the destination for me.",
]


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
    # Phase 52: four answers already in the session transcript. The Part 4
    # follow-up must carry the last three of them, oldest first.
    page.evaluate("""() => {
        window.__fu = [];
        %s.forEach(function (line) { spkAddLine('in', line, 'candidate'); });
        SP_EXAM.part = 4;
        SP_EXAM.phases = [
            {key: 'spx_response', who: 'candidate', sec: 30, qi: 0,
             prompt: 'Would you travel alone?'},
            {key: 'spx_close', who: 'examiner', sec: 5, line: %s}
        ];
        SP_EXAM.phase = 0;
        SP_EXAM.followUpBusy = false;
        spxNextPhase();
    }""" % (json.dumps(P4_EARLIER), json.dumps(SCRIPT_LINE)))
    assert wait_until(page, "SPK.followUps === 1", 10), page.evaluate("SPK.followUps")
    assert page.evaluate("window.__fu.length") == 1, page.evaluate("window.__fu")

    first = page.evaluate("window.__fu[0]['payload']")
    assert first.get("mode") == "examiner", first
    assert first.get("candidate_context") == P4_EARLIER[-3:], first
    assert P4_EARLIER[0] not in first.get("candidate_context"), first

    # A new answer pushes the window forward: the oldest of the three leaves.
    page.evaluate("""() => {
        const next = 'A new answer after the follow-up.';
        window.__next = next;
        window.__fu = [];
        spkAddLine('in', next, 'candidate');
        spxPartnerFromProvider('What about next year?', 'examiner');
    }""")
    assert wait_until(page, "window.__fu.length === 1", 10), page.evaluate("window.__fu")
    second = page.evaluate("window.__fu[0]['payload']")
    assert second.get("candidate_context") == P4_EARLIER[-2:] + [
        page.evaluate("window.__next")], second

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


# ---------------------------------------------------------------------------
# 15. The saved report keeps the whole session transcript and copies it.
# ---------------------------------------------------------------------------
REPORT_TURNS = [
    {"who": "examiner", "text": "How do you get to school?"},
    {"who": "candidate", "text": "I usually walk, because it is only ten minutes."},
    {"who": "partner", "text": "I take the bus when it rains."},
]
REPORT_TEXT = (
    "Examiner: How do you get to school?\n"
    "You: I usually walk, because it is only ten minutes.\n"
    "Alex: I take the bus when it rains."
)


def test_report_transcript(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB)
    page.evaluate("setLang('en')")
    page.evaluate("async () => { await SP_EXAM.open(); }")
    page.evaluate("""(turns) => {
        SPK.part = 1;
        SPK.lines = turns.map(function (t, i) {
            return {side: 'out', who: t.who, t: i + 1, text: t.text};
        });
        SP_EXAM.part = 1;
        SP_EXAM.full = false;
        SP_EXAM.entry = {min: 2, silence_prompts: 0};
        SPK.reportData = {bands: {}, evidence: [], fixes: []};
        spxSetScreen('report');
        spxRenderReportScreen();
    }""", REPORT_TURNS)

    # Every line of the session is printed with its speaker's label.
    shown = page.eval_on_selector_all(
        "#spxRpTx .spx-tx-line", "els => els.map(e => e.textContent)")
    assert shown == REPORT_TEXT.split("\n"), shown
    assert page.evaluate(
        "getComputedStyle(document.getElementById('spxRpTxWrap')).display") \
        != "none"
    assert page.is_visible("#spxRpCopy")

    # Copy puts exactly that text on the clipboard and calls no endpoint.
    page.evaluate("""() => {
        window.__copied = null;
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {writeText: function (text) {
                window.__copied = text;
                return Promise.resolve();
            }}
        });
    }""")
    requests = []
    # Let any save the page scheduled before the click reach the server first,
    # then watch the copy on its own.
    page.wait_for_timeout(900)
    page.on("request", lambda req: requests.append(req.url))
    page.click("#spxRpCopy")
    assert wait_until(page, "window.__copied !== null", 3), "Copy wrote nothing"
    assert page.evaluate("window.__copied") == REPORT_TEXT, \
        page.evaluate("window.__copied")
    page.wait_for_timeout(250)
    api_calls = [u for u in requests if "/api/" in u]
    assert api_calls == [], api_calls

    # The language switch repaints the labels and the copied text with them.
    page.evaluate("setLang('es')")
    page.wait_for_timeout(120)
    es_shown = page.evaluate("document.getElementById('spxRpTx').textContent")
    assert "Vos: " in es_shown and "Examinador: " in es_shown, es_shown
    page.evaluate("window.__copied = null")
    page.click("#spxRpCopy")
    assert wait_until(page, "window.__copied !== null", 3)
    es_copied = page.evaluate("window.__copied")
    assert es_copied.startswith("Examinador: "), es_copied
    assert "Vos: " in es_copied, es_copied

    # Nothing said, nothing to show and nothing to copy.
    page.evaluate("""() => {
        SPK.lines = [];
        spxRenderReportScreen();
    }""")
    assert page.evaluate(
        "getComputedStyle(document.getElementById('spxRpTxWrap')).display") \
        == "none"
    assert page.evaluate("SP_EXAM.copyTranscript()") == ""

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("15. report transcript: every line shown and copied, no server call")
    browser.close()


# ---------------------------------------------------------------------------
# 16. The saved `sp` row keeps the session's own measurements.
# ---------------------------------------------------------------------------
LOG_TURNS = [
    {"who": "examiner", "text": "Where do you live?"},
    {"who": "candidate", "text": "Um, I live in Buenos Aires, you know, near the park."},
    {"who": "partner", "text": "Uh, I know, like, a quiet place."},
    {"who": "candidate", "text": "Like, the transport is cheap and it works."},
]
LOG_SPEECH = {
    "words": 19,
    "fillers": 3,
    "breakdown": {"um": 1, "uh": 0, "like": 1, "you know": 1},
}
LOG_PARTS = [
    {"part": 1, "seconds": 47,
     "turns": {"examiner": 2, "partner": 0, "candidate": 1}},
    {"part": 3, "seconds": 92,
     "turns": {"examiner": 1, "partner": 2, "candidate": 2}},
]


def test_saved_measurements(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB,
                                     reuse_login=True)
    page.evaluate("setLang('en')")
    page.evaluate("async () => { await SP_EXAM.open(); }")

    # A session with two parts already measured. The bands are all null: this
    # row must not invent a score out of unmeasured scales.
    page.evaluate("""(turns) => {
        SPK.part = 1;
        SPK.lines = turns.map(function (t, i) {
            return {side: 'out', who: t.who, t: i + 1, text: t.text};
        });
        SP_EXAM.full = false;
        SP_EXAM.part = 3;
        SP_EXAM.session = {
            full: false, seed: 1, partner: 'Alex',
            plan: {parts: [{part: 1}, {part: 3}]},
            turns: {examiner: 3, partner: 2, candidate: 3},
            partStats: {
                1: {part: 1, planned: 120, seconds: 47, wall: 47,
                    turns: {examiner: 2, partner: 0, candidate: 1}},
                3: {part: 3, planned: 240, seconds: 92, wall: 92,
                    turns: {examiner: 1, partner: 2, candidate: 2}}
            }
        };
        SPK.reportData = {
            bands: {grammar_vocabulary: null, discourse_management: null,
                    pronunciation: null, interactive_communication: null},
            metrics: {wpm: 0, fillers: 0, longest_silence: 0, overlap_ms: 0},
            evidence: [], fixes: []
        };
        spxFinalizeReport(SPK.reportData);
        SP_EXAM.saved = false;
        SP_EXAM.entry = null;
        SP_EXAM.saveReport();
    }""", LOG_TURNS)

    saved = page.evaluate("""() => {
        const doc = JSON.parse(localStorage.getItem(userKey()));
        const rows = doc.log.filter(e => e.type === 'sp');
        return rows.length ? rows[rows.length - 1] : null;
    }""")
    assert saved is not None, "no sp row reached D.log"

    assert saved["speech"] == LOG_SPEECH, saved.get("speech")
    assert saved["part_stats"] == LOG_PARTS, saved.get("part_stats")
    assert saved["turns"] == {"examiner": 3, "partner": 2, "candidate": 3}, \
        saved.get("turns")
    assert "score" not in saved, "a score was invented from unmeasured bands"
    assert all(v is None for v in saved["bands"].values()), saved["bands"]

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("16. saved measurements: %d words, %d fillers, %d parts, no score"
          % (saved["speech"]["words"], saved["speech"]["fillers"],
             len(saved["part_stats"])))
    browser.close()


def test_keyboard_overlay(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB)

    page.evaluate("async () => { await SP_EXAM.open(); }")

    # The transcript announces new lines instead of staying silent to a reader.
    assert page.evaluate(
        "document.getElementById('spxTx').getAttribute('aria-live')") == "polite"

    # A part in progress: the phase model owns the floor, so mute/unmute is
    # the only thing Space does.
    page.evaluate("""() => {
        SP_EXAM.part = 1;
        SP_EXAM.phases = [{key: 'spx_response', who: 'candidate', sec: 60,
                           qi: 0, prompt: 'Tell me about your city.'}];
        SP_EXAM.phase = 0;
        spxSetScreen('exam');
    }""")
    assert page.evaluate("SP_EXAM.screen") == "exam"
    # Move the focus off the Start button so the key press reaches the page
    # with no button activation in the way.
    page.evaluate("document.activeElement && document.activeElement.blur()")
    assert page.evaluate("SP_EXAM.micMuted") is False

    page.keyboard.press("Space")
    assert page.evaluate("SP_EXAM.micMuted") is True, "Space did not mute the mic"
    page.keyboard.press("Space")
    assert page.evaluate("SP_EXAM.micMuted") is False, "Space did not unmute the mic"

    dialogs = []
    accept = {"value": False}

    def on_dialog(dialog):
        dialogs.append(dialog.message)
        if accept["value"]:
            dialog.accept()
        else:
            dialog.dismiss()

    page.on("dialog", on_dialog)

    # Escape during a part asks first. Dismissing keeps the exam on screen.
    page.keyboard.press("Escape")
    assert len(dialogs) == 1, dialogs
    assert dialogs[0] == page.evaluate("t('spx_confirm_quit')"), dialogs
    assert page.evaluate("SP_EXAM.screen") == "exam", "dismiss must not leave the part"
    assert page.evaluate(
        "getComputedStyle(document.getElementById('spxOverlay')).display") != "none"

    # Accepting the same question does close the overlay.
    accept["value"] = True
    page.keyboard.press("Escape")
    assert page.evaluate("SP_EXAM.screen") == ""
    assert page.evaluate(
        "getComputedStyle(document.getElementById('spxOverlay')).display") == "none"

    # With no part running, Escape just closes: no question to answer.
    dialogs.clear()
    page.evaluate("async () => { await SP_EXAM.open(); }")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("Escape")
    assert dialogs == [], dialogs
    assert page.evaluate(
        "getComputedStyle(document.getElementById('spxOverlay')).display") == "none"

    # The key works in both dictionaries and each says it in its own language.
    keys = page.evaluate(
        "({en: I18N.en.spx_confirm_quit, es: I18N.es.spx_confirm_quit})")
    assert keys["en"] and keys["es"], keys
    assert keys["en"] != keys["es"], keys

    assert errors == [], errors
    print("9. keyboard: aria-live transcript, Space mute, Escape confirms")
    browser.close()


# ---------------------------------------------------------------------------
# 10. Accessibility: labelled buttons, trapped focus and 44 px targets.
# ---------------------------------------------------------------------------
SCREENS = ["choose", "brief", "exam", "feedback", "report"]


def visible_overlay_buttons(page):
    return page.evaluate("""() => {
        const ov = document.getElementById('spxOverlay');
        return Array.from(ov.querySelectorAll('button')).filter(function (el) {
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden';
        }).map(function (el) {
            const r = el.getBoundingClientRect();
            return {
                id: el.id,
                part: el.dataset.part || '',
                label: (el.getAttribute('aria-label') || '').trim(),
                text: el.textContent.trim().replace(/\\s+/g, ' '),
                w: r.width,
                h: r.height
            };
        });
    }""")


def test_overlay_accessibility(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB)

    page.evaluate("async () => { await SP_EXAM.open(); }")
    assert page.evaluate("SP_EXAM.screen") == "choose"

    # Every button that exists in the overlay is labelled, hidden or not.
    unlabelled = page.evaluate("""() => Array.from(
        document.querySelectorAll('#spxOverlay button')).filter(function (el) {
            return !(el.getAttribute('aria-label') || '').trim();
        }).map(function (el) { return el.id || el.textContent.trim(); })""")
    assert unlabelled == [], unlabelled

    # Each screen's visible buttons: labelled, and at least 44x44.
    per_screen = {}
    for screen in SCREENS:
        page.evaluate("(name) => spxSetScreen(name)", screen)
        page.wait_for_timeout(60)
        buttons = visible_overlay_buttons(page)
        assert buttons, screen
        for b in buttons:
            assert b["label"], (screen, b)
            assert b["w"] >= 43.5 and b["h"] >= 43.5, (screen, b)
        per_screen[screen] = buttons

    parts = [b for b in per_screen["choose"] if b["part"]]
    assert len(parts) == 4, parts
    for i, b in enumerate(parts, start=1):
        assert b["label"].startswith("Part %d, " % i), b

    # The labels follow the language switch instead of staying in English.
    page.evaluate("() => spxSetScreen('choose')")
    page.evaluate("setLang('es')")
    page.wait_for_timeout(120)
    es = {b["id"]: b["label"] for b in visible_overlay_buttons(page) if b["id"]}
    page.evaluate("setLang('en')")
    page.wait_for_timeout(120)
    en = {b["id"]: b["label"] for b in visible_overlay_buttons(page) if b["id"]}
    assert es["spxCloseBtn"] == page.evaluate("I18N.es.spx_aria_close"), es
    assert en["spxCloseBtn"] == page.evaluate("I18N.en.spx_aria_close"), en
    assert es["spxCloseBtn"] != en["spxCloseBtn"], (es, en)
    assert page.evaluate(
        "I18N.es.spx_aria_close !== I18N.en.spx_aria_close")

    # Focus stays in the dialog: Tab from the last control wraps to the first
    # (the close button) and Shift+Tab from the first wraps back to the last
    # (Start).
    page.evaluate("() => spxSetScreen('choose')")
    assert page.evaluate("spxFocusables()[0].id") == "spxCloseBtn"
    assert page.evaluate("spxFocusables().slice(-1)[0].id") == "spxStartBtn"

    page.evaluate("() => spxFocusables().slice(-1)[0].focus()")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "spxCloseBtn", \
        page.evaluate("document.activeElement.id")
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("document.activeElement.id") == "spxStartBtn", \
        page.evaluate("document.activeElement.id")

    # A focus that escaped the overlay is pulled back in on the next Tab.
    page.evaluate("() => document.getElementById('themeToggle').focus()")
    assert page.evaluate(
        "!document.getElementById('spxOverlay').contains(document.activeElement)")
    page.keyboard.press("Tab")
    assert page.evaluate(
        "document.getElementById('spxOverlay').contains(document.activeElement)")
    assert page.evaluate("document.activeElement.id") == "spxCloseBtn"

    # Closed, the trap lets the page navigate again.
    page.evaluate("SP_EXAM.close()")
    page.evaluate("() => document.getElementById('themeToggle').focus()")
    page.keyboard.press("Tab")
    assert page.evaluate(
        "!document.getElementById('spxOverlay').contains(document.activeElement)")

    assert errors == [], errors
    print("10. overlay a11y: every button labelled, 44px targets, focus trapped")
    browser.close()


# ---------------------------------------------------------------------------
# 12. Mobile: the whole overlay works on a 380x740 screen.
# ---------------------------------------------------------------------------
MOBILE_W = 380
MOBILE_H = 740


def mobile_overlay_state(page):
    return page.evaluate("""() => {
        const ov = document.getElementById('spxOverlay');
        const box = ov.firstElementChild;
        const br = box.getBoundingClientRect();
        const photos = Array.from(document.querySelectorAll('#spxTask .spx-photo'))
            .map(function (el) {
                const r = el.getBoundingClientRect();
                return {left: r.left, top: r.top, right: r.right,
                        bottom: r.bottom, width: r.width, height: r.height};
            });
        const buttons = Array.from(ov.querySelectorAll('button'))
            .filter(function (el) {
                const r = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                return r.width > 0 && r.height > 0 &&
                    cs.visibility !== 'hidden' && cs.display !== 'none';
            }).map(function (el) {
                const r = el.getBoundingClientRect();
                return {id: el.id, w: r.width, h: r.height,
                        left: r.left, right: r.right};
            });
        return {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            docScrollWidth: document.documentElement.scrollWidth,
            box: {top: br.top, bottom: br.bottom, left: br.left, right: br.right,
                  scrollWidth: box.scrollWidth, clientWidth: box.clientWidth,
                  scrollHeight: box.scrollHeight, clientHeight: box.clientHeight,
                  scrollTop: box.scrollTop},
            photos: photos,
            buttons: buttons,
            placeholders: document.querySelectorAll('#spxTask .spx-photo-missing').length
        };
    }""")


def png_size(path):
    with open(path, "rb") as fh:
        data = fh.read(24)
    assert data[:8] == PNG_SIGNATURE, data[:8]
    return struct.unpack(">II", data[16:24])


def test_mobile_overlay(p):
    browser = p.chromium.launch(args=[
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
    ])
    context = browser.new_context(
        viewport={"width": MOBILE_W, "height": MOBILE_H},
        is_mobile=True, has_touch=True, permissions=["microphone"])
    context.add_init_script(SILENT_SPEECH_SYNTH)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(URL + "app?spx_test=1", wait_until="networkidle")
    # The suite has already spent the server's 10 logins per 10 minutes, so
    # this late test adopts the session the first one opened.
    if OWNER_SESSION:
        page.evaluate("localStorage.setItem('b2first_user', %s)"
                      % json.dumps(json.dumps(OWNER_SESSION)))
        page.reload(wait_until="networkidle")
    else:
        helpers.login_owner(page, URL)
    page.evaluate("localStorage.setItem('spx_test','1')")
    page.goto(URL + "app?spx_test=1", wait_until="networkidle")
    page.wait_for_timeout(350)
    helpers.dismiss_onboarding(page)

    # Part 2 on a phone: the phase that carries the two photographs.
    page.evaluate("async () => { await SPX_TEST.ensure(); await SP_EXAM.open(); }")
    page.evaluate("""async () => {
        SP_EXAM.select(2);
        await SP_EXAM.start();
        await SP_EXAM.ready();
    }""")
    page.wait_for_function(
        """() => {
            const imgs = Array.from(document.querySelectorAll('#spxTask .spx-photo img'));
            return imgs.length === 2 && imgs.every(i => i.complete && i.naturalWidth > 200);
        }""", timeout=20000)
    page.wait_for_timeout(300)

    before = mobile_overlay_state(page)
    assert before["innerWidth"] == MOBILE_W, before
    assert before["innerHeight"] == MOBILE_H, before
    assert before["docScrollWidth"] <= MOBILE_W, \
        "the page scrolls sideways on a 380 px screen: %s" % before["docScrollWidth"]
    assert before["box"]["scrollWidth"] <= before["box"]["clientWidth"] + 0.5, before["box"]

    # Every visible button is a real target and stays inside the screen.
    assert before["buttons"], before
    for b in before["buttons"]:
        assert b["left"] >= -0.5 and b["right"] <= MOBILE_W + 0.5, b
        assert b["w"] >= 43.5 and b["h"] >= 43.5, b

    # Part 2: two real photographs, one under the other, not side by side.
    photos = before["photos"]
    assert before["placeholders"] == 0, "Part 2 fell back to a text placeholder"
    assert len(photos) == 2, photos
    assert abs(photos[0]["left"] - photos[1]["left"]) < 1, \
        "the two photographs are not stacked: %s" % photos
    assert photos[1]["top"] >= photos[0]["bottom"] - 1, photos
    for photo in photos:
        assert photo["width"] >= 200, photo
        assert photo["right"] <= MOBILE_W + 0.5, photo

    # The panel is taller than the screen and scrolls.
    assert before["box"]["scrollHeight"] > before["box"]["clientHeight"] + 20, before["box"]

    # Capture the stacked photographs on the phone, at the real viewport size.
    page.evaluate("document.getElementById('spxTask').scrollIntoView({block:'start'})")
    page.wait_for_timeout(150)
    os.makedirs(OUT_DIR, exist_ok=True)
    shot = os.path.join(OUT_DIR, "dy_mobile.png")
    page.locator("#spxOverlay").screenshot(path=shot)
    assert png_size(shot) == (MOBILE_W, MOBILE_H), png_size(shot)

    # The end-of-part button starts off screen and becomes reachable by
    # scrolling; pressing it really ends the part.
    page.evaluate("document.getElementById('spxOverlay').firstElementChild.scrollTop = 0")
    page.wait_for_timeout(100)
    reset = mobile_overlay_state(page)
    assert reset["box"]["scrollTop"] == 0, reset["box"]
    end_btn = page.locator("button[data-i18n='spx_end_early']")
    end_btn.scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    after = mobile_overlay_state(page)
    assert after["box"]["scrollTop"] > 0, after["box"]
    reach = page.evaluate("""() => {
        const btn = document.querySelector("button[data-i18n='spx_end_early']");
        const box = document.getElementById('spxOverlay').firstElementChild;
        const r = btn.getBoundingClientRect(), b = box.getBoundingClientRect();
        return {top: r.top, bottom: r.bottom, left: r.left, right: r.right,
                boxTop: b.top, boxBottom: b.bottom, inside:
                    r.top >= b.top - 1 && r.bottom <= b.bottom + 1 &&
                    r.left >= b.left - 1 && r.right <= b.right + 1};
    }""")
    assert reach["inside"] is True, reach
    end_btn.click()
    assert page.evaluate("SP_EXAM.screen") in ("feedback", "report"), \
        page.evaluate("SP_EXAM.screen")

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("12. mobile 380x740: stacked photos, scrolling panel, reachable buttons")
    browser.close()


# ---------------------------------------------------------------------------
# 14. The phase title and the green turn badge name the same speaker.
# ---------------------------------------------------------------------------
# The speaker each title can name, read off the English UI. The badge is
# classified the same way, and a frame is wrong when the badge names a speaker
# the title does not. Both sides are spelled out here, never imported from the
# page, so the check cannot agree with the app by construction.
TURN_TITLES = {
    "Your turn": ["candidate"],
    "Your long turn": ["candidate"],
    "Your follow-up question": ["candidate"],
    "Your partner's turn": ["partner"],
    "Listen to the examiner": ["examiner"],
    "Examiner speaking": ["examiner"],
    "Closing": ["examiner"],
    "Talk together": ["both"],
    "Reach a decision": ["both"],
}

TURN_RECORDER = r"""
window.__turnFrames = 0;
window.__turnPairs = [];
window.__turnBad = [];
(function () {
  const TITLES = %s;
  function badgeOwner(text) {
    if (text.indexOf('Your turn + ') === 0) return 'both';
    if (text === 'Your turn') return 'candidate';
    if (text === 'Examiner speaking') return 'examiner';
    if (text === 'Partner speaking') return 'partner';
    if (text.indexOf('Thinking') === 0) return 'examiner';
    if (text.indexOf('Listening') === 0) return 'candidate';
    return '';
  }
  function frame() {
    if (window.SP_EXAM && SP_EXAM.screen === 'exam') {
      const nameEl = document.getElementById('spxPhaseName');
      const badgeEl = document.getElementById('spxWho');
      const title = nameEl ? nameEl.textContent.trim() : '';
      const badge = badgeEl ? badgeEl.textContent.trim() : '';
      if (title && badge) {
        window.__turnFrames++;
        const pair = title + ' || ' + badge;
        if (window.__turnPairs.indexOf(pair) < 0) window.__turnPairs.push(pair);
        const owners = TITLES[title];
        const who = badgeOwner(badge);
        if (!owners || owners.indexOf(who) < 0) {
          if (window.__turnBad.indexOf(pair) < 0) window.__turnBad.push(pair);
        }
      }
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
"""


def test_turn_state_coherent(p):
    browser, page, errors = open_app(p, "?spx_test=1&spk=sim", SPEECH_STUB,
                                     reuse_login=True)
    page.evaluate("setLang('en')")
    page.evaluate("async () => { await SPX_TEST.ensure(); await SP_EXAM.open(); }")

    # The exact frame the screenshot showed: a candidate turn whose phase
    # carries the partner's key. The title must not claim it is the partner's
    # turn while the badge says the floor is yours.
    mismatch = page.evaluate("""() => {
        SP_EXAM.part = 3;
        SP_EXAM.phases = [{key: 'spx_response', who: 'candidate', sec: 60,
                           qi: 0, prompt: 'Tell me about your city.'}];
        SP_EXAM.phase = 0;
        spxSetScreen('exam');
        spxRenderTurn();
        return {
            title: document.getElementById('spxPhaseName').textContent.trim(),
            badge: document.getElementById('spxWho').textContent.trim(),
            key: spxTurnTitleKey('candidate')
        };
    }""")
    assert mismatch["key"] == "spx_your_turn", mismatch
    assert mismatch["title"] == "Your turn", mismatch
    assert mismatch["badge"] == "Your turn", mismatch

    # A whole Part 3 through the real engine, fast clock, sampled on every
    # animation frame.
    page.evaluate(TURN_RECORDER % json.dumps(TURN_TITLES))
    page.evaluate("""async () => {
        SPX_TEST.timeScale = 0.02;
        SP_EXAM.select(3);
        await SP_EXAM.start();
        await SP_EXAM.ready();
    }""")
    assert wait_until(page, "SP_EXAM.screen==='exam'", 20), \
        page.evaluate("SPX_TEST.state()")
    assert wait_until(
        page, "SP_EXAM.screen==='feedback' || SP_EXAM.screen==='report'", 90,
        step=250), page.evaluate("SPX_TEST.state()")

    bad = page.evaluate("window.__turnBad")
    pairs = page.evaluate("window.__turnPairs")
    frames = page.evaluate("window.__turnFrames")
    assert bad == [], "the title and the badge contradicted each other: %s" % bad
    assert frames >= 30, frames
    assert any(p.startswith("Listen to the examiner || ") for p in pairs), pairs
    assert any(p.startswith("Talk together || ") or
               p.startswith("Reach a decision || ") for p in pairs), pairs
    # The joint turn names both candidates in the badge, never only one.
    assert any("|| Your turn + " in p for p in pairs), pairs
    # Every title we saw is one the checker knows: an unknown label would be
    # skipped instead of checked.
    unknown = [p.split(" || ")[0] for p in pairs
               if p.split(" || ")[0] not in TURN_TITLES]
    assert unknown == [], unknown

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("14. turn state: %d frames of Part 3, no title/badge contradiction"
          % frames)
    browser.close()


def test_part1_long_silence(p):
    browser, page, errors = open_app(p, "?spx_test=1&spk=sim", NO_SPEECH_STUB,
                                     reuse_login=True)
    page.evaluate("setLang('en')")
    # A muted part runs the real clock but never produces a candidate turn: from
    # the exam's point of view the candidate simply says nothing.
    page.evaluate("""async () => {
        SPX_TEST.timeScale = 0.05;
        SP_EXAM.select(1);
        await SP_EXAM.start();
        SP_EXAM.muteMic(true);
        await SP_EXAM.ready();
    }""")
    assert wait_until(page, "SP_EXAM.screen==='exam' && SP_EXAM.phase>=1", 20), \
        page.evaluate("SPX_TEST.state()")

    prefix = page.evaluate("SPX_LINES.rephrase")
    assert prefix, prefix
    first_q = page.evaluate("SP_EXAM.phases[1].prompt")
    second_q = page.evaluate("SP_EXAM.phases[3].prompt")
    assert first_q and second_q and first_q != second_q, (first_q, second_q)
    assert page.evaluate("(SP_EXAM.task.questions||[]).includes(%r)" % first_q), \
        "the repeated line is not the written bank question: %r" % first_q

    # The scaled clock would end this turn long before the repeat; the question
    # stays open and the examiner asks the same one again, verbatim.
    assert wait_until(
        page,
        "SPK.lines.some(l=>l.who==='examiner'&&l.text===SPX_LINES.rephrase+%r)"
        % first_q, 20), page.evaluate("SPK.lines")
    assert page.evaluate("SP_EXAM.rephraseQi") == 0, \
        page.evaluate("SP_EXAM.rephraseQi")

    # Only after the repeat does the next question arrive, so the candidate has
    # not lost the turn to the clock.
    assert wait_until(page, "SP_EXAM.phase>=2", 10), page.evaluate("SPX_TEST.state()")
    examiner = page.evaluate("SPK.lines.filter(l=>l.who==='examiner').map(l=>l.text)")
    q2_line = page.evaluate("SP_EXAM.phases[2].line")
    assert q2_line in examiner, examiner
    assert examiner.count(prefix + first_q) == 1, examiner
    assert examiner.index(prefix + first_q) < examiner.index(q2_line), examiner

    # The repeat budget is per question, not per part: question 2 gets its own
    # one, and question 1 is still not repeated a second time.
    assert wait_until(page, "SP_EXAM.rephraseQi===1", 20), \
        page.evaluate("SPX_TEST.state()")
    examiner = page.evaluate("SPK.lines.filter(l=>l.who==='examiner').map(l=>l.text)")
    assert examiner.count(prefix + first_q) == 1, examiner
    assert examiner.count(prefix + second_q) == 1, examiner

    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("17. Part 1 silence: the same written question once, before moving on")
    browser.close()


def test_brief_partner_mode(p):
    browser, page, errors = open_app(p, "?spx_test=1", SPEECH_STUB,
                                     reuse_login=True)
    page.evaluate("setLang('en')")
    page.evaluate("async () => { await SP_EXAM.open(); }")

    # No AI available: the brief says the partner's lines are written and that
    # nothing the candidate says goes to a provider. Read from the rendered
    # line, not from the key, so a wrong key would fail here.
    bank = page.evaluate("""() => {
        SPK.partnerAI = false;
        SPX_TEST.partnerProvider = null;
        SP_EXAM.part = 1;
        SP_EXAM.full = false;
        SP_EXAM.task = {questions: ['Tell me about your city.']};
        SP_EXAM.phases = spxPhasesFor(1, SP_EXAM.task, 1);
        spxSetScreen('brief');
        spxRenderBrief();
        const el = document.getElementById('spxBriefAi');
        return {
            text: el.textContent,
            expected: I18N.en.spx_brief_partner_bank,
            inBrief: !!el.closest('[data-spx-screen="brief"]'),
            visible: getComputedStyle(el).display !== 'none'
        };
    }""")
    assert bank["inBrief"] is True and bank["visible"] is True, bank
    assert bank["text"] == bank["expected"], bank
    assert "written lines from the task bank" in bank["text"], bank
    assert "Nothing you say is sent to an AI provider" in bank["text"], bank

    # An available provider flips the same line to the AI wording and names
    # what is sent.
    ai = page.evaluate("""() => {
        SPK.partnerAI = true;
        spxRenderBrief();
        const el = document.getElementById('spxBriefAi');
        return {text: el.textContent, expected: I18N.en.spx_brief_partner_ai,
                bank: I18N.en.spx_brief_partner_bank};
    }""")
    assert ai["expected"] and ai["expected"] != ai["bank"], ai
    assert ai["text"] == ai["expected"], ai
    assert ai["text"] != bank["text"], ai
    assert "generated by AI" in ai["text"], ai
    assert "the task question and the words you say" in ai["text"], ai

    # The Spanish brief says the same in Spanish, through the language switch.
    page.evaluate("setLang('es')")
    page.wait_for_timeout(120)
    es = page.evaluate("""() => {
        const el = document.getElementById('spxBriefAi');
        return {text: el.textContent, expected: I18N.es.spx_brief_partner_ai,
                en: I18N.en.spx_brief_partner_ai};
    }""")
    assert es["text"] == es["expected"], es
    assert es["text"] != es["en"], es
    assert "las genera la IA" in es["text"], es

    page.evaluate("setLang('en')")
    page.wait_for_timeout(120)

    # The probe is the source of truth: a late "available: true" repaints the
    # brief that is already open, instead of leaving the bank wording behind.
    page.evaluate("""() => {
        window.__realFetch = window.fetch;
        window.__probe = 0;
        window.fetch = function (url, opts) {
            if (String(url).indexOf('/api/speaking/partner') >= 0 &&
                !(opts && opts.method === 'POST')) {
                window.__probe++;
                return Promise.resolve({ok: true, json: function () {
                    return Promise.resolve({available: true});
                }});
            }
            return window.__realFetch.apply(this, arguments);
        };
        SPK.partnerAI = false;
        spxSetScreen('brief');
        spxRenderBrief();
        spxProbePartnerAi();
    }""")
    assert wait_until(page, "SPK.partnerAI === true", 10), \
        page.evaluate("SPK.partnerAI")
    assert page.evaluate("document.getElementById('spxBriefAi').textContent") \
        == page.evaluate("I18N.en.spx_brief_partner_ai"), \
        page.evaluate("document.getElementById('spxBriefAi').textContent")

    # Opening the real brief probes availability by itself, so the honesty
    # does not depend on a previous run having reached the exam screen.
    started = page.evaluate("""async () => {
        window.__probe = 0;
        SPK.partnerAI = false;
        SP_EXAM.select(1);
        await SP_EXAM.start();
        return {screen: SP_EXAM.screen, probe: window.__probe};
    }""")
    assert started["screen"] == "brief", started
    assert started["probe"] >= 1, started
    assert wait_until(
        page,
        "document.getElementById('spxBriefAi').textContent ==="
        " I18N.en.spx_brief_partner_ai", 10), \
        page.evaluate("document.getElementById('spxBriefAi').textContent")

    page.evaluate("window.fetch = window.__realFetch")
    page.evaluate("SP_EXAM.close()")
    assert errors == [], errors
    print("18. brief: written-bank and AI wording, probed availability")
    browser.close()


def main():
    test_server_prompts()
    with sync_playwright() as p:
        test_recognition_and_partner(p)
        test_part3_two_reactions(p)
        test_partner_no_repeat(p)
        test_followup_capped(p)
        test_no_support(p)
        test_mic_denied(p)
        test_speech_counts(p)
        test_report_transcript(p)
        test_saved_measurements(p)
        test_keyboard_overlay(p)
        test_overlay_accessibility(p)
        test_mobile_overlay(p)
        test_turn_state_coherent(p)
        test_part1_long_silence(p)
        test_brief_partner_mode(p)
    print("OK: the partner reacts twice, never repeats a line, and no support is safe")


if __name__ == "__main__":
    main()
