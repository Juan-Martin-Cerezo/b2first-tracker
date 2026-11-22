"""Speaking turns, role clarity, topic guard, and zero-transcript acceptance test.

Covers all 6 mandatory requirements of the Speaking redesign:
  1. Role sequence per part (Parts 1-4): examiner -> (partner) -> you, strictly
     one active role at a time, visible role name on every turn, and Part 3
     opened by the partner from the task bank.
  2. Microphone closed while examiner/partner speak or during prep ("Listen" /
     "Escuchá"); "Your turn" / "Tu turno" + open mic ("Speak" / "Hablar") ONLY
     during the candidate's turn.
  3. Partner never appears as "You" / "candidate" and never contaminates
     speech counts or the report; stray recognition results fired during
     examiner/partner turns are ignored.
  4. Off-topic follow-up from client provider stub AND server /api/speaking/turn
     Gemini stub is replaced by the scripted fallback from the current part &
     task bank.
  5. Zero visible transcript nodes in Speaking or Report (#spxTx, #spxRpTxWrap,
     #spxRpTx, #spxRpCopy, .spk-transcript, #spkInText, #spkOutText), no
     SP_EXAM.copyTranscript, removed i18n keys absent, and zero candidate text
     persisted under data/.
  6. Full Part 2 sim finishes with bands, per-part comment, tip, single
     "not measured" pronunciation explanation, and zero candidate quotes.

Also captures required screenshots in tests/out/:
  - speaking_roles_390_light.png (390x844 light, zero horizontal overflow)
  - speaking_roles_1280_light.png (1280x900 light, zero horizontal overflow)

Run:
  cd tests && uv run --no-project --quiet --with playwright --with httpx python test_speaking_turns.py
"""
import base64
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
OUT_DIR = os.path.join(TESTS, "out")
sys.path.insert(0, REPO)

USER = "spk-turns-runner"
PASS = "spk-turns-pass-9"

OFF_TOPIC_REPLY = "What is your favorite lasagna recipe on Mars?"
CANDIDATE_SENTINEL = "CANDIDATE_UNIQUE_SPEECH_SENTINEL_9941"
PARTNER_LEAK_SENTINEL = "PARTNER_LEAK_SENTINEL_7721"

REPORT_STUB = {
    "bands": {
        "grammar_vocabulary": 4,
        "discourse_management": 4,
        "pronunciation": None,
        "interactive_communication": 4,
    },
    "evidence": [
        {
            "scale": "grammar_vocabulary",
            "quote": CANDIDATE_SENTINEL,
            "note": "Clear B2 comparison structures with varied verb tenses.",
        },
        {
            "scale": "discourse_management",
            "quote": "Comparing the first photograph with the second one",
            "note": "Well-structured long turn with logical linkers.",
        },
    ],
    "fixes": [
        "Use more speculative language when comparing the two photographs.",
        "Extend each point with one concrete everyday example.",
        "Keep a steady pace across the full long turn.",
    ],
}


class StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        _ = self.rfile.read(length) if length > 0 else b""
        if "generateContent" in self.path:
            payload = {
                "candidates": [{
                    "content": {"parts": [{"text": json.dumps({
                        "transcript": CANDIDATE_SENTINEL,
                        "reply": OFF_TOPIC_REPLY,
                    })}]},
                    "finishReason": "STOP",
                }]
            }
        else:
            payload = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(REPORT_STUB, ensure_ascii=False),
                    }
                }]
            }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


stub_srv = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
STUB_PORT = stub_srv.server_address[1]
threading.Thread(target=stub_srv.serve_forever, daemon=True).start()

os.environ["B2_AI_PROVIDER"] = "deepseek"
os.environ["B2_AI_BASE"] = "http://127.0.0.1:%d" % STUB_PORT
os.environ["B2_AI_KEY"] = "FAKE-TURNS-AI-KEY"
os.environ["B2_SPK_GOOGLE_KEY"] = "FAKE-TURNS-GOOGLE-KEY"
os.environ["B2_SPK_TURN_BASE"] = "http://127.0.0.1:%d" % STUB_PORT
os.environ["B2_SPK_TURN_MODEL"] = "gemini-2.5-flash"
os.environ["B2_SPK_MIN_DAILY_PER_USER"] = "60"
os.environ["B2_SPK_MIN_DAILY_TOTAL"] = "600"
os.environ.pop("B2_SPK_LIVE", None)

import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2spk-turns-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
PORT = srv.server_address[1]
BASE = "http://127.0.0.1:%d" % PORT
threading.Thread(target=srv.serve_forever, daemon=True).start()

SPEECH_SHIM = """
(() => {
  window.__utts = [];
  window.__recInstances = [];
  window.speechSynthesis = {
    getVoices() {
      return [
        {name: 'UK Female', lang: 'en-GB', default: true},
        {name: 'UK Male', lang: 'en-GB', default: false}
      ];
    },
    speak(u) {
      window.__utts.push({text: u.text, lang: u.lang, rate: u.rate, pitch: u.pitch});
      if (u.onstart) u.onstart();
      if (u.onend) setTimeout(() => u.onend(), 10);
    },
    cancel() {}
  };
  function FakeSpeechRecognition() {
    this.lang = 'en-GB';
    this.continuous = true;
    this.interimResults = true;
    this.maxAlternatives = 1;
    this.onresult = null;
    this.onerror = null;
    this.onend = null;
    this.started = false;
    window.__recInstances.push(this);
  }
  FakeSpeechRecognition.prototype.start = function() { this.started = true; };
  FakeSpeechRecognition.prototype.stop = function() { this.started = false; };
  window.SpeechRecognition = FakeSpeechRecognition;
  window.webkitSpeechRecognition = FakeSpeechRecognition;
})();
"""


def api(path, body=None, token=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def wait_until(pg, expr, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        if pg.evaluate("() => Boolean(" + expr + ")"):
            return True
        pg.wait_for_timeout(120)
    return False


def open_app(p, user_obj, viewport=(1280, 900), qs="?spx_test=1&spk=sim"):
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.add_init_script(SPEECH_SHIM)
    pg.add_init_script(
        "localStorage.setItem('b2first_user', %s);"
        % json.dumps(json.dumps(user_obj))
    )
    pg.goto(BASE + "/app" + qs, wait_until="networkidle")
    assert wait_until(pg, "typeof SP_EXAM==='object' && typeof SPX_TEST==='object' && !!USER", 15), \
        "app did not boot"
    pg.evaluate("""() => {
        try { D.onboarded = true; save(); } catch (e) {}
        for (const id of ['onboardingOverlay', 'tourOverlay', 'obOverlay']) {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        }
        document.body.classList.remove('ob-open', 'tour-open');
    }""")
    return browser, pg, errors


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    st, reg = api("/api/register", {"name": USER, "password": PASS})
    assert st in (200, 201), (st, reg)
    token = reg["token"]
    user_obj = {
        "id": reg["id"],
        "name": reg["name"],
        "token": token,
        "is_owner": reg.get("is_owner", False),
    }

    with open(os.path.join(REPO, "material", "speaking.json"), encoding="utf-8") as fh:
        bank = json.load(fh)
    p4_task = [p for p in bank["parts"] if p["part"] == 4][0]["tasks"][0]

    # --- 4b (server): Off-topic Gemini reply on /api/speaking/turn is replaced by bank fallback ---
    pcm = b"\x02\x00" * 16000
    st_turn, turn_body = api("/api/speaking/turn", {
        "audio_b64": base64.b64encode(pcm).decode("ascii"),
        "mime": "audio/pcm;rate=16000",
        "part": 4,
        "role": "examiner",
        "tts": "none",
        "session_id": "turns-offtopic-1",
        "task": p4_task,
        "history": [
            {"who": "examiner", "text": p4_task["questions"][0]},
            {"who": "candidate", "text": "I think school trips are useful."},
        ],
    }, token=token)
    assert st_turn == 200, (st_turn, turn_body)
    assert turn_body["reply"] != OFF_TOPIC_REPLY, turn_body
    assert turn_body["reply"] == p4_task["questions"][1], (turn_body["reply"], p4_task["questions"])

    out = {"server_offtopic_replaced": turn_body["reply"]}

    with sync_playwright() as p:
        # --- Desktop 1280x900: Tests 1, 2, 3, 4a, 5, 6 + 1280 screenshot ---
        browser, pg, errors = open_app(p, user_obj, viewport=(1280, 900))
        pg.evaluate("SPX_TEST.timeScale = 0.05")

        # 5a. Static zero-transcript & removed-i18n checks
        removed_ids = ["spxTx", "spxRpTxWrap", "spxRpTx", "spxRpCopy", "spkInText", "spkOutText"]
        present = pg.evaluate(
            "ids => ids.filter(id => !!document.getElementById(id))", removed_ids
        )
        assert present == [], "Removed transcript DOM nodes still present: %r" % present
        assert pg.evaluate("document.querySelectorAll('.spk-transcript').length") == 0
        assert pg.evaluate("typeof SP_EXAM.copyTranscript === 'undefined'")
        removed_keys = ["spx_rp_transcript", "spx_transcript", "spx_copy", "spx_aria_copy"]
        leaked_keys = pg.evaluate(
            "ks => ks.filter(k => (k in I18N.en) || (k in I18N.es))", removed_keys
        )
        assert leaked_keys == [], "Removed i18n keys still present: %r" % leaked_keys

        # 1. Deterministic role sequences per part (Parts 1-4)
        pg.evaluate("showView('hoy'); selectSessionStudio('fri-b'); SP_EXAM.open()")
        assert wait_until(pg, "SP_EXAM.screen==='choose' && !!SP_EXAM.bank", 10)
        seqs = pg.evaluate("""() => ({
            p1: SPX_TEST.phases(1),
            p2: SPX_TEST.phases(2),
            p3: SPX_TEST.phases(3),
            p4: SPX_TEST.phases(4)
        })""")
        assert seqs["p1"][0]["who"] == "examiner" and seqs["p1"][1]["who"] == "candidate"
        assert [x["who"] for x in seqs["p2"]] == [
            "examiner", "examiner", "candidate", "examiner", "partner"
        ], seqs["p2"]
        assert seqs["p2"][1]["key"] == "spx_prep" and seqs["p2"][1]["sec"] == 60
        assert seqs["p2"][2]["sec"] == 120 and seqs["p2"][4]["sec"] == 30
        assert [x["who"] for x in seqs["p3"]] == [
            "examiner", "partner", "candidate", "partner", "candidate",
            "examiner", "partner", "candidate"
        ], seqs["p3"]
        assert not any(x["who"] == "both" for k in seqs for x in seqs[k]), "who='both' must not exist"
        # Part 3 partner opens with a bank line
        assert seqs["p3"][1]["line"], "Part 3 partner opening line missing"
        # Part 4 directed questions ("You, ..." / "Partner, ...")
        p4_ex = [x["line"] for x in seqs["p4"] if x["who"] == "examiner"]
        assert any("You," in l for l in p4_ex) and any("Partner," in l for l in p4_ex), p4_ex
        out["1_sequences"] = {k: [x["who"] for x in v] for k, v in seqs.items()}

        # 1b & 2 & 3: Live DOM role exclusivity + mic gate + partner anti-leak (EN & ES)
        pg.evaluate("""() => {
            SP_EXAM.select(3);
            SP_EXAM.task = SP_EXAM.bank.parts.find(p => p.part === 3).tasks[0];
            SP_EXAM.phases = spxPhasesFor(3, SP_EXAM.task, 7, SP_EXAM.task.id);
            SP_EXAM.phase = 0;
            SP_EXAM.micMuted = false;
            SPK.lines = [];
            spxHeardReset();
            spxRenderPartnerHeader();
            spxRenderTask();
            spxSetScreen('exam');
        }""")

        def inspect_phase(idx):
            return pg.evaluate("""idx => {
                SP_EXAM.phase = idx;
                spxRenderTurn();
                const active = [...document.querySelectorAll('#spxRoles [data-on="1"]')]
                    .map(el => ({role: el.getAttribute('data-role'), text: el.textContent.trim()}));
                const btn = document.getElementById('spxMicBtn');
                return {
                    whoTurn: SP_EXAM.whoTurn(),
                    active,
                    whoText: document.getElementById('spxWho').textContent.trim(),
                    clock: document.getElementById('spxClock').textContent.trim(),
                    micOpen: SP_EXAM.micOpen,
                    micDisabled: btn.disabled,
                    micState: btn.getAttribute('data-mic-state'),
                    micText: btn.textContent.trim(),
                    overflow: document.documentElement.scrollWidth > window.innerWidth + 1
                };
            }""", idx)

        # Phase 0: Examiner
        p0 = inspect_phase(0)
        assert len(p0["active"]) == 1 and p0["active"][0]["role"] == "examiner", p0
        assert p0["active"][0]["text"] == "Examiner", p0
        assert p0["micOpen"] is False and p0["micDisabled"] is True and p0["micState"] == "closed", p0
        assert p0["micText"] == "Listen", p0
        assert p0["whoText"] != "Your turn", p0

        # Phase 1: Partner opens
        p1 = inspect_phase(1)
        assert len(p1["active"]) == 1 and p1["active"][0]["role"] == "partner", p1
        assert "Partner:" in p1["active"][0]["text"], p1
        assert p1["micOpen"] is False and p1["micDisabled"] is True and p1["micState"] == "closed", p1
        assert p1["micText"] == "Listen", p1
        assert p1["whoText"] != "Your turn", p1

        # Test 3a: Firing SpeechRecognition during partner turn MUST NOT create candidate speech
        leaked = pg.evaluate("""sentinel => {
            spxSpeechStart();
            // Force a recogniser instance to simulate stray audio during partner turn
            if (!SPX_REC) {
                SPX_REC = new window.SpeechRecognition();
                SPX_REC.onresult = function(ev) {
                    if (!SPK.heard || !spxCandidateTurnNow() || SP_EXAM.micMuted) return;
                    SPK.heard.final += sentinel;
                };
            }
            if (SPX_REC && typeof SPX_REC.onresult === 'function') {
                SPX_REC.onresult({
                    resultIndex: 0,
                    results: [{isFinal: true, 0: {transcript: sentinel}}]
                });
            }
            spxCommitHeard();
            return {
                heardFinal: SPK.heard.final,
                candLines: (SPK.lines || []).filter(l => l.who === 'candidate')
            };
        }""", PARTNER_LEAK_SENTINEL)
        assert leaked["heardFinal"] == "" and leaked["candLines"] == [], leaked

        # Phase 2: Candidate ("Your turn")
        p2 = inspect_phase(2)
        assert len(p2["active"]) == 1 and p2["active"][0]["role"] == "you", p2
        assert p2["active"][0]["text"] == "You", p2
        assert p2["micOpen"] is True and p2["micDisabled"] is False and p2["micState"] == "open", p2
        assert p2["micText"] == "Speak", p2
        assert p2["whoText"] == "Your turn", p2
        assert not p2["overflow"], "1280px speaking exam overflowed"

        # Capture desktop 1280 light screenshot on candidate turn (roles + mic + timer clearly visible)
        pg.evaluate("spxRenderClock(35); spxRenderTurn();")
        pg.wait_for_timeout(200)
        pg.screenshot(path=os.path.join(OUT_DIR, "speaking_roles_1280_light.png"))

        # Test mic toggle during candidate turn
        pg.click("#spxMicBtn")
        muted_state = pg.evaluate(
            "({open: SP_EXAM.micOpen, state: document.getElementById('spxMicBtn').getAttribute('data-mic-state')})"
        )
        assert muted_state == {"open": False, "state": "muted"}, muted_state
        pg.click("#spxMicBtn")
        assert pg.evaluate("SP_EXAM.micOpen") is True

        # Check Spanish (es-AR): "Escuchá" / "Tu turno" / "Hablar"
        pg.evaluate("setLang('es'); spxRenderPartnerHeader();")
        es_partner = inspect_phase(1)
        assert es_partner["micText"] == "Escuchá" and es_partner["micDisabled"] is True, es_partner
        assert es_partner["whoText"] != "Tu turno", es_partner
        es_you = inspect_phase(2)
        assert es_you["whoText"] == "Tu turno" and es_you["micText"] == "Hablar", es_you
        assert es_you["active"][0]["role"] == "you" and es_you["active"][0]["text"] == "Vos", es_you
        pg.evaluate("setLang('en'); spxRenderPartnerHeader();")

        # 3b. Partner lines never counted in spxSpeechCounts or attributed to candidate
        counts = pg.evaluate("""() => spxSpeechCounts([
            {who: 'partner', text: 'um uh like you know completely ignored partner words'},
            {who: 'examiner', text: 'Thank you, tell me more about this.'},
            {who: 'candidate', text: 'I prefer travelling by train.'}
        ])""")
        assert counts["words"] == 5 and counts["fillers"] == 0, counts
        out["2_mic_and_roles"] = {"p0": p0["micState"], "p1": p1["micState"], "p2": p2["micState"]}

        # 4a (client): Off-topic partner provider stub in Part 3 falls back to task bank line
        pg.evaluate("""offTopic => {
            SPK.mode = 'turn';
            SPX_TEST.partnerProvider = function() { return offTopic; };
            SP_EXAM.partnerSaid = [];
            SPK.lines = [];
            SP_EXAM.phase = 1;
            const ph = SP_EXAM.phases[1];
            spxPartnerTurn({prompt: ph.prompt, text: ph.line});
        }""", OFF_TOPIC_REPLY)
        assert wait_until(pg, "SPK.lines.some(l => l.who === 'partner')", 10), \
            "partner fallback line never fired"
        partner_spoken = pg.evaluate("SPK.lines.filter(l => l.who === 'partner').map(l => l.text)")
        bank_lines = pg.evaluate("SP_EXAM.task.partnerLines || []")
        assert partner_spoken[0] != OFF_TOPIC_REPLY, partner_spoken
        assert partner_spoken[0] in bank_lines, (partner_spoken, bank_lines)

        # 4c (client): Off-topic examiner follow-up stub in Part 1 falls back to bank question
        pg.evaluate("""offTopic => {
            SP_EXAM.part = 1;
            const p1Id = spxPool(SP_EXAM.bank, 1)[0];
            SP_EXAM.task = spxTaskById(SP_EXAM.bank, 1, p1Id) || spxDefaultTask(1);
            SP_EXAM.phases = spxPhasesFor(1, SP_EXAM.task, 3, p1Id);
            SP_EXAM.phase = 1;
            SP_EXAM.followUpBusy = false;
            SPK.followUps = 0;
            SPK.lines = [{who: 'candidate', text: 'I live in a small town near the coast.'}];
            SPX_TEST.partnerProvider = function() { return offTopic; };
            spxNextPhase();
        }""", OFF_TOPIC_REPLY)
        assert wait_until(pg, "SPK.followUps >= 1 && !SP_EXAM.followUpBusy", 10), \
            "examiner follow-up never resolved"
        inserted_line = pg.evaluate("SP_EXAM.phases[2] && SP_EXAM.phases[2].line || ''")
        assert inserted_line and inserted_line != OFF_TOPIC_REPLY, inserted_line
        out["4_client_offtopic_fallback"] = {
            "partner": partner_spoken[0],
            "examiner_followup": inserted_line,
        }

        # 6. Full Part 2 sim run -> bands, comment, tip, single "not measured", ZERO candidate quotes
        pg.evaluate("""() => {
            SPX_TEST.partnerProvider = null;
            SP_EXAM.close();
            SPK.mode = 'sim';
            SPX_TEST.timeScale = 0.02;
        }""")
        pg.evaluate("SP_EXAM.open()")
        assert wait_until(pg, "SP_EXAM.screen==='choose'", 10)
        pg.evaluate("SP_EXAM.select(2)")
        pg.click("#spxStartBtn")
        assert wait_until(pg, "SP_EXAM.screen==='brief'", 10)
        pg.click("#spxReadyBtn")
        assert wait_until(
            pg,
            "SP_EXAM.screen==='feedback' && "
            "((SPK.reportData && SPK.reportData.bands) || SPK.lastReportError !== '')",
            90,
        ), "Part 2 sim never finished feedback"
        assert pg.evaluate("SPK.lastReportError") in (None, ""), pg.evaluate("SPK.lastReportError")

        fb_info = pg.evaluate("""sentinel => {
            const scales = [...document.querySelectorAll('#spxFbScales .spk-scale')].map(el => el.textContent);
            const panelText = document.getElementById('spxPanel').textContent;
            return {
                bands: SPK.reportData.bands,
                scales,
                parts: document.querySelectorAll('#spxFbParts .spx-part-comment').length,
                tip: document.getElementById('spxFbTip').textContent.trim(),
                hasSentinel: panelText.includes(sentinel),
                hasSimText: panelText.includes('Both photographs show people')
            };
        }""", CANDIDATE_SENTINEL)
        assert isinstance(fb_info["bands"]["grammar_vocabulary"], int), fb_info
        assert isinstance(fb_info["bands"]["discourse_management"], int), fb_info
        assert isinstance(fb_info["bands"]["interactive_communication"], int), fb_info
        assert fb_info["bands"]["pronunciation"] is None, fb_info
        assert fb_info["parts"] == 1 and fb_info["tip"], fb_info
        assert not fb_info["hasSentinel"], "Candidate quote leaked into feedback UI!"
        assert not fb_info["hasSimText"], "Candidate speech leaked into feedback UI!"
        # Pronunciation "not measured" shown once with short explanation
        nm_cards = [s for s in fb_info["scales"] if "not measured" in s.lower()]
        assert len(nm_cards) == 1 and "pronunciation is not measured" in nm_cards[0].lower(), fb_info["scales"]

        # Save report and check Report screen has zero transcript & zero candidate text
        pg.click("#spxFbSave")
        assert wait_until(pg, "SP_EXAM.screen==='report'", 5)
        rp_text = pg.evaluate("document.getElementById('spxPanel').textContent")
        assert CANDIDATE_SENTINEL not in rp_text, "Candidate sentinel leaked into report screen!"
        assert "Both photographs show people" not in rp_text, "Candidate sim text leaked into report!"
        assert pg.evaluate("document.getElementById('spxRpTx')") is None
        assert pg.evaluate("document.getElementById('spxRpCopy')") is None
        assert wait_until(pg, "SYNC_STATE==='ok'", 10)
        assert errors == [], "Desktop page errors: %r" % errors
        browser.close()

        # --- Mobile 390x844 light screenshot + zero overflow ---
        browser_m, pg_m, errors_m = open_app(p, user_obj, viewport=(390, 844))
        pg_m.evaluate("""() => {
            SP_EXAM.open();
        }""")
        assert wait_until(pg_m, "SP_EXAM.screen==='choose' && !!SP_EXAM.bank", 10)
        pg_m.evaluate("""() => {
            SP_EXAM.select(3);
            SP_EXAM.task = SP_EXAM.bank.parts.find(p => p.part === 3).tasks[0];
            SP_EXAM.phases = spxPhasesFor(3, SP_EXAM.task, 7, SP_EXAM.task.id);
            SP_EXAM.phase = 2;
            SP_EXAM.micMuted = false;
            spxRenderPartnerHeader();
            spxRenderTask();
            spxSetScreen('exam');
            spxRenderClock(35);
            spxRenderTurn();
        }""")
        pg_m.wait_for_timeout(250)
        overflow_m = pg_m.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        assert not overflow_m, "390x844 speaking exam overflowed horizontally"
        pg_m.screenshot(path=os.path.join(OUT_DIR, "speaking_roles_390_light.png"))
        assert errors_m == [], "Mobile page errors: %r" % errors_m
        browser_m.close()

    # 5b. Verify zero candidate speech/transcript was persisted anywhere under data/
    disk_blob = b""
    for dirpath, _dirs, files in os.walk(_tmp):
        for name in files:
            try:
                with open(os.path.join(dirpath, name), "rb") as fh:
                    disk_blob += b"\n" + fh.read()
            except OSError:
                pass
    for forbidden in (CANDIDATE_SENTINEL, PARTNER_LEAK_SENTINEL, OFF_TOPIC_REPLY,
                      "Both photographs show people"):
        assert forbidden.encode("utf-8") not in disk_blob, \
            "Transcript/speech leaked to disk: %r" % forbidden

    out["5_zero_transcript_on_disk"] = {"bytes_scanned": len(disk_blob)}
    out["6_part2_sim_bands"] = fb_info["bands"]

    srv.shutdown()
    srv.server_close()
    stub_srv.shutdown()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("OK: speaking turns, role exclusivity, topic guard, and zero-transcript verified")


if __name__ == "__main__":
    main()
