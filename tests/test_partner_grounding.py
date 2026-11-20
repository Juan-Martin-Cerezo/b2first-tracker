"""Acceptance test for partner grounding: Alex listens and reacts to concrete details.

Runs against an isolated server and a local HTTP text-model stub (no network,
no secrets) plus Playwright with `SPX_TEST` and a stubbed provider:

  1. `candidate_said="I'd rather go by coach because it's much cheaper"` ->
     grounding guard catches an empty filler draft, retries with the quoted
     detail, and returns a grounded line mentioning coach/cheap/bus/money.
  2. `candidate_said="I prefer flying because it's much faster"` -> returns a
     different line mentioning flying/fast/plane.
  3. `partner_said` already containing the draft -> similarity guard retries
     and returns a non-repeating line (also verifies `partner_said` and
     `candidate_context` sanitisation and 3-line cap in partner + examiner).
  4. Empty `candidate_said` -> HTTP 200 with `{"line": ""}` and 0 stub calls.
  5. Overlong / multi-sentence model output is capped at <=35 words and 1-2
     sentences (never 5xx even if retry also fails to ground).
  6. UI (`SPX_TEST` + provider stub): candidate turn + partner reply both
     appear in `#spxTx` in order (including without Web Speech), partner line
     is spoken aloud, `partner_said` & `candidate_context` travel in all parts,
     and empty AI response retries once before using bank fallback.

Run:
    cd tests && uv run --no-project --quiet --with playwright --with httpx python test_partner_grounding.py
"""
import json
import os
import re
import shutil
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)


class StubState:
    calls = []
    mode = "default"
    lock = threading.Lock()


class TextModelStub(BaseHTTPRequestHandler):
    """Local OpenAI/DeepSeek wire stub recording every request."""

    def log_message(self, *_args):
        pass

    def _send(self, obj, status=200):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        msgs = body.get("messages") or []
        sys_msg = msgs[0].get("content", "") if len(msgs) > 0 else ""
        usr_msg = msgs[1].get("content", "") if len(msgs) > 1 else ""
        is_retry = "STRICT CORRECTION:" in usr_msg

        with StubState.lock:
            StubState.calls.append((sys_msg, usr_msg))
            mode = StubState.mode

        if mode == "filler_then_coach":
            if not is_retry:
                line = "That's interesting, I agree."
            else:
                line = (
                    "Going by coach is much cheaper, though sitting for hours can "
                    "feel cramped. Would you still pick the coach for a long trip?"
                )
        elif mode == "always_generic":
            line = "That sounds fine to me."
        elif mode == "flying":
            line = (
                "Flying is definitely faster, though airport security eats up "
                "loads of time. Do you mind waking up early for a flight?"
            )
        elif mode == "repeat_then_fresh":
            if not is_retry:
                line = (
                    "Going by coach is much cheaper, though sitting for hours can "
                    "feel cramped. Would you still pick the coach for a long trip?"
                )
            else:
                line = (
                    "A cheaper coach ticket leaves extra money for food, even if "
                    "the motorway traffic slows us down."
                )
        elif mode == "verbose":
            line = (
                "Taking the coach is clearly cheaper than most other options when "
                "you travel with friends from school. You can chat the whole way "
                "and share snacks on board without worrying about luggage fees. "
                "However, the motorway gets terribly busy on Friday afternoons and "
                "delays are common. What time would you want to leave?"
            )
        elif mode == "examiner_repeat_then_grounded":
            if not is_retry:
                line = "How do you prefer to travel on holiday?"
            else:
                line = "What makes flying less stressful for you than taking a train?"
        else:
            line = "Coach travel saves money, though the train can be quicker."

        self._send({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"line": line}),
                }
            }]
        })


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), TextModelStub)
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()
STUB_URL = "http://127.0.0.1:%d" % stub_srv.server_address[1]

os.environ["B2_AI_PROVIDER"] = "deepseek"
os.environ["B2_AI_BASE"] = STUB_URL + "/v1"
os.environ["B2_AI_MODEL"] = ""
os.environ["B2_AI_KEY"] = "FAKE-GROUNDING-KEY"
os.environ["B2_AI_DAILY_PER_USER"] = "200"
os.environ["B2_AI_DAILY_TOTAL"] = "1000"
os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "60"
os.environ["B2_SPK_MIN_DAILY_TOTAL"] = "600"
os.environ["B2_DEMO"] = "0"

import helpers  # noqa: E402

DATA_DIR = helpers.isolated_data_dir("b2partnerground-")
BASE_URL = helpers.isolated_server(
    {
        "B2_DEMO": "0",
        "B2_AI_PROVIDER": "deepseek",
        "B2_AI_BASE": STUB_URL + "/v1",
        "B2_AI_KEY": "FAKE-GROUNDING-KEY",
    },
    data_dir=DATA_DIR,
)

import server as S  # noqa: E402


def post_partner(token, payload):
    req = urllib.request.Request(
        BASE_URL + "/api/speaking/partner",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"raw": raw}


def count_sentences(text):
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return len(parts)


def wait_until(page, expr, timeout_s=10, step=80):
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if page.evaluate(expr):
            return True
        page.wait_for_timeout(step)
    return False


def test_backend():
    token = S.new_token("grounding-user")
    out = {}

    # 1. Coach / cheaper: empty filler on draft 1 triggers strict retry with quoted detail.
    StubState.calls.clear()
    StubState.mode = "filler_then_coach"
    st1, body1 = post_partner(token, {
        "question": "How would you prefer to travel for the class trip?",
        "topic": "Transport",
        "candidate_said": "I'd rather go by coach because it's much cheaper",
        "candidate_context": ["old-1", "old-2", "old-3\x00\nline", "old-4"],
        "partner_said": [],
        "mode": "partner",
    })
    assert st1 == 200, (st1, body1)
    line1 = body1.get("line", "")
    assert line1, body1
    low1 = line1.lower()
    assert any(tok in low1 for tok in ("coach", "cheap", "bus", "money")), line1
    assert not re.match(r"^(that's interesting|i see|i agree)\b", low1), line1
    assert len(StubState.calls) == 2, f"expected grounding retry: {len(StubState.calls)}"
    sys1, retry_usr = StubState.calls[-1]
    assert "Alex" in sys1 and "35 words" in sys1, sys1
    assert "STRICT CORRECTION:" in retry_usr, retry_usr
    assert '"cheaper' in retry_usr or '"coach' in retry_usr, retry_usr
    # candidate_context is passed in partner mode too, sanitised and capped at 3 lines
    assert "old-1" not in retry_usr and "old-4" in retry_usr, retry_usr
    assert "\x00" not in retry_usr, retry_usr
    assert len(line1.split()) <= 35, line1
    assert 1 <= count_sentences(line1) <= 2, line1
    out["1_coach_grounding"] = line1

    # 2. Flying / faster: distinct line mentioning flying/fast/plane.
    StubState.calls.clear()
    StubState.mode = "flying"
    st2, body2 = post_partner(token, {
        "question": "How would you prefer to travel for the class trip?",
        "topic": "Transport",
        "candidate_said": "I prefer flying because it's much faster",
        "mode": "partner",
    })
    assert st2 == 200, (st2, body2)
    line2 = body2.get("line", "")
    assert line2 and line2 != line1, (line1, line2)
    low2 = line2.lower()
    assert any(tok in low2 for tok in ("flying", "fast", "plane")), line2
    assert len(StubState.calls) == 1, f"already grounded should not retry: {len(StubState.calls)}"
    assert len(line2.split()) <= 35 and 1 <= count_sentences(line2) <= 2, line2
    out["2_flying_distinct"] = line2

    # 3. partner_said already containing line1 -> similarity guard retries & returns different line.
    StubState.calls.clear()
    StubState.mode = "repeat_then_fresh"
    st3, body3 = post_partner(token, {
        "question": "How would you prefer to travel for the class trip?",
        "topic": "Transport",
        "candidate_said": "I'd rather go by coach because it's much cheaper",
        "partner_said": ["p-old-1", "p-old-2", "p-old-3\x00\tbad", line1],
        "mode": "partner",
    })
    assert st3 == 200, (st3, body3)
    line3 = body3.get("line", "")
    assert line3 and line3 != line1, (line1, line3)
    assert S._spk_token_similarity(line3, line1) < 0.8, (line1, line3)
    assert len(StubState.calls) == 2, f"expected repeat retry: {len(StubState.calls)}"
    _sys3, usr3 = StubState.calls[0]
    assert "p-old-1" not in usr3 and line1 in usr3, usr3
    assert "\x00" not in usr3 and "\t" not in usr3, usr3
    out["3_no_repeat_partner_said"] = line3

    # 3b. Examiner mode: concrete detail + forbids repeating previous examiner question.
    StubState.calls.clear()
    StubState.mode = "examiner_repeat_then_grounded"
    st3b, body3b = post_partner(token, {
        "question": "How do you prefer to travel on holiday?",
        "topic": "Transport",
        "candidate_said": "I prefer flying because it's much faster",
        "candidate_context": ["I went to Spain last summer."],
        "mode": "examiner",
    })
    assert st3b == 200, (st3b, body3b)
    ex_line = body3b.get("line", "")
    assert ex_line.endswith("?") and len(ex_line.split()) <= 20, ex_line
    assert "flying" in ex_line.lower(), ex_line
    assert len(StubState.calls) == 2, f"examiner repeat should retry: {len(StubState.calls)}"
    out["3b_examiner_grounded"] = ex_line

    # 4. Empty candidate_said -> 200 with {"line": ""} and ZERO model calls.
    StubState.calls.clear()
    StubState.mode = "flying"
    for empty_val in ("", "   \n\t  ", None):
        for mode in ("partner", "examiner"):
            st4, body4 = post_partner(token, {
                "question": "How would you prefer to travel?",
                "topic": "Transport",
                "candidate_said": empty_val,
                "mode": mode,
            })
            assert st4 == 200, (mode, empty_val, st4, body4)
            assert body4 == {"line": ""}, (mode, empty_val, body4)
    assert len(StubState.calls) == 0, f"empty candidate_said called model: {len(StubState.calls)}"
    out["4_empty_no_model_call"] = True

    # 5. Verbose output capped at <=35 words and 1-2 sentences; ungrounded retry never 5xx.
    StubState.calls.clear()
    StubState.mode = "verbose"
    st5, body5 = post_partner(token, {
        "question": "How would you prefer to travel?",
        "topic": "Transport",
        "candidate_said": "I'd rather go by coach because it's much cheaper",
        "mode": "partner",
    })
    assert st5 == 200, (st5, body5)
    line5 = body5.get("line", "")
    assert len(line5.split()) <= 35, (len(line5.split()), line5)
    assert 1 <= count_sentences(line5) <= 2, (count_sentences(line5), line5)

    StubState.calls.clear()
    StubState.mode = "always_generic"
    st5b, body5b = post_partner(token, {
        "question": "How would you prefer to travel?",
        "topic": "Transport",
        "candidate_said": "I'd rather go by coach because it's much cheaper",
        "mode": "partner",
    })
    assert st5b == 200 and body5b.get("line"), (st5b, body5b)
    assert len(StubState.calls) == 2, len(StubState.calls)
    out["5_caps_and_no_5xx"] = {
        "words": len(line5.split()),
        "sentences": count_sentences(line5),
        "fallback_status": st5b,
    }
    return out


def test_ui():
    from playwright.sync_api import sync_playwright

    page_errors = []
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
        ])
        ctx = browser.new_context()
        # Simulate NO Web Speech support and capture speechSynthesis utterances.
        ctx.add_init_script("""(function () {
            delete window.SpeechRecognition;
            delete window.webkitSpeechRecognition;
            window.__spoken = [];
            try {
                Object.defineProperty(window, 'speechSynthesis', {
                    configurable: true,
                    value: {
                        getVoices: function () { return []; },
                        cancel: function () {},
                        speak: function (u) {
                            window.__spoken.push(String(u && u.text || ''));
                            if (u && typeof u.onend === 'function') {
                                setTimeout(function () { u.onend(); }, 5);
                            }
                        }
                    }
                });
            } catch (e) {}
        })();""")
        page = ctx.new_page()
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(BASE_URL + "/app", wait_until="networkidle")
        helpers.login_owner(page, BASE_URL + "/")
        page.evaluate("localStorage.setItem('spx_test', '1')")
        page.goto(BASE_URL + "/app?spx_test=1", wait_until="networkidle")
        page.wait_for_timeout(300)
        helpers.dismiss_onboarding(page)
        assert page.evaluate("!!window.SPX_TEST"), "SPX_TEST not exposed"

        # 6a. Candidate speaks (no Web Speech: transcript in SPK.lines) -> partner
        #     receives latest candidate_said, candidate_context in Part 3, retries
        #     once when AI returns empty, speaks aloud, and #spxTx shows You + Alex.
        cand1 = "I'd rather go by coach because it's much cheaper."
        alex1 = "Going by coach saves loads of money, though the journey takes longer."
        cand2 = "I prefer flying because it's much faster."
        alex2 = "Flying is faster, but getting through airport security is exhausting."

        page.evaluate("""async ([cand1, alex1, cand2, alex2]) => {
            await SP_EXAM.open();
            spxSetScreen('exam');
            SP_EXAM.part = 3;
            SP_EXAM.task = {
                topic: 'Transport',
                partnerLines: ['Bank fallback one.', 'Bank fallback two.']
            };
            SP_EXAM.phases = [{key: 'spx_discuss', who: 'both', sec: 120, qi: 0,
                               prompt: 'How should we travel?'}];
            SP_EXAM.phase = 0;
            SP_EXAM.partnerSaid = [];
            SP_EXAM.txShown = 0;
            SPK.lines = [];
            SPK.heard.final = 'stale old line';
            SPK.heard.committed = 'stale old line';
            document.getElementById('spxTx').replaceChildren();

            window.__calls = [];
            let firstEmpty = true;
            SPX_TEST.partnerProvider = function (question, payload) {
                window.__calls.push(payload);
                if (firstEmpty) {
                    firstEmpty = false;
                    return '';
                }
                if ((payload.candidate_said || '').indexOf('flying') >= 0) {
                    return alex2;
                }
                return alex1;
            };

            // Candidate turn 1 (without Web Speech: lands via spkAddLine)
            spkAddLine('in', cand1, 'candidate');
            spxPartnerTurn({prompt: 'How should we travel?', text: 'Bank fallback one.'});
        }""", [cand1, alex1, cand2, alex2])

        assert wait_until(
            page,
            "SPK.lines.some(l => l.who === 'partner' && l.text.indexOf('coach') >= 0)",
            10,
        ), page.evaluate("({lines: SPK.lines, calls: window.__calls})")

        calls1 = page.evaluate("window.__calls")
        assert len(calls1) == 2, f"expected 1 retry on empty AI reply: {calls1}"
        assert calls1[0]["candidate_said"] == cand1, calls1[0]
        assert cand1 in calls1[0]["candidate_context"], calls1[0]
        assert calls1[0]["partner_said"] == [], calls1[0]

        tx1 = page.evaluate("document.getElementById('spxTx').textContent")
        assert ("You: " + cand1) in tx1 or ("Vos: " + cand1) in tx1, tx1
        assert ("Alex: " + alex1) in tx1, tx1
        assert tx1.index(cand1) < tx1.index(alex1), tx1

        spoken1 = page.evaluate("window.__spoken")
        assert alex1 in spoken1, spoken1

        # 6b. Candidate turn 2 via live SPK.heard.final -> partner receives fresh
        #     candidate_said and partner_said=[alex1], and #spxTx shows turn 2 below.
        page.evaluate("""([cand2]) => {
            SPK.heard.active = true;
            SPK.heard.final = cand2;
            SPK.heard.committed = '';
            spxPartnerTurn({prompt: 'What about flying?', text: 'Bank fallback two.'});
        }""", [cand2])

        assert wait_until(
            page,
            "SPK.lines.some(l => l.who === 'partner' && l.text.indexOf('Flying') >= 0)",
            10,
        ), page.evaluate("({lines: SPK.lines, calls: window.__calls})")

        calls2 = page.evaluate("window.__calls")
        assert len(calls2) == 3, calls2
        last_payload = calls2[-1]
        assert last_payload["candidate_said"] == cand2, last_payload
        assert alex1 in last_payload["partner_said"], last_payload
        assert cand1 in last_payload["candidate_context"], last_payload

        tx2 = page.evaluate("document.getElementById('spxTx').textContent")
        assert cand2 in tx2 and alex2 in tx2, tx2
        assert tx2.index(alex1) < tx2.index(cand2) < tx2.index(alex2), tx2

        spoken2 = page.evaluate("window.__spoken")
        assert alex2 in spoken2, spoken2

        # 6c. When AI returns empty TWICE, falls back to bank line.
        page.evaluate("""() => {
            window.__emptyCalls = 0;
            SPX_TEST.partnerProvider = function () {
                window.__emptyCalls++;
                return '';
            };
            spxPartnerTurn({prompt: 'Final question?', text: 'Bank fallback two.'});
        }""")
        assert wait_until(
            page,
            "SPK.lines.some(l => l.who === 'partner' && l.text === 'Bank fallback two.')",
            10,
        ), page.evaluate("({lines: SPK.lines, n: window.__emptyCalls})")
        assert page.evaluate("window.__emptyCalls") == 2, page.evaluate("window.__emptyCalls")

        page.evaluate("SP_EXAM.close()")
        assert page_errors == [], f"page errors: {page_errors}"
        out["6_ui_panel_and_voice"] = {
            "tx_rows": page.evaluate("document.querySelectorAll('#spxTx .spx-tx-line').length"),
            "spoken_count": len(spoken2),
            "retry_before_fallback_calls": page.evaluate("window.__emptyCalls"),
        }
        browser.close()
    return out


def main():
    try:
        out = test_backend()
        out.update(test_ui())
        print(json.dumps(out, ensure_ascii=False, indent=1))
        print("OK: partner grounding tests passed")
    finally:
        stub_srv.shutdown()
        stub_srv.server_close()
        shutil.rmtree(DATA_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
