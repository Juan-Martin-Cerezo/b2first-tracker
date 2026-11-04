"""Phase 56: each part lasts what the exam says, with no drift between parts.

The exam announces a budget for every part (the sum of its phases, the same
number the plan carries and the report repeats). This suite runs a whole mock
on a compressed clock (`timeScale` 0.05, so a four-minute part takes about
twelve seconds) and checks the measured part durations against that budget:

  1. The plan and the part ledger agree on the budget of every part.
  2. Every part lasts its budget within two seconds. The timer keeps its
     resolution in exam time and every phase hands over at its scheduled
     boundary, so the lateness of a tick never accumulates. The reported
     seconds are checked against the part's own wall clock, so a part that
     simply echoed its budget would not pass.
  3. The four parts together are within two seconds of the four budgets, and
     the running error stays inside the tolerance after every part: the error
     of one part is not inherited (or cancelled) by the next one.

The candidate is kept talking through their own turn (the sim voice stays
"active" while the floor is theirs), because a candidate who falls silent
deliberately ends the turn early and the part then has no fixed length to
measure. When the floor leaves the candidate, the room is made silent for the
same reason, so the examiner's line does not wait on a real-time floor rule
that a compressed clock would stretch.

Run:  uv run --with playwright python test_speaking_clock.py
"""
import json
import os
import sys
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

os.environ.pop("B2_AI_KEY", None)

import helpers  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

URL = helpers.isolated_server() + "/"
NAME = "speaking-clock-suite"
PASS = "speaking-clock-suite-pass-9"

TIME_SCALE = 0.05
TOLERANCE_S = 2
PARTS = (1, 2, 3, 4)

# The candidate fills their turn; nobody speaks while the floor is elsewhere.
TALK_THROUGH_TURN = r"""
window.__clockDriver = true;
(function keepTalking() {
  if (!window.__clockDriver) return;
  const ph = SP_EXAM.phases[SP_EXAM.phase];
  const candidate = ph && ph.who === 'candidate';
  SPK.simSpeechUntil = candidate ? performance.now() + 60000 : 0;
  if (!candidate) SPK.lastSpeechEnd = 0;
  requestAnimationFrame(keepTalking);
})();
"""


def wait_until(pg, expression, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pg.evaluate(expression):
            return True
        pg.wait_for_timeout(100)
    return False


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1100, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))

    pg.goto(URL, wait_until="load")
    helpers.login_user(pg, URL, NAME, PASS)
    pg.goto(URL + "app?spx_test=1&spk=sim", wait_until="load")
    pg.wait_for_timeout(400)
    helpers.dismiss_onboarding(pg)

    pg.evaluate(
        "async () => { SPX_TEST.timeScale = %s; await SPX_TEST.startFull(4242) }"
        % TIME_SCALE)
    assert wait_until(pg, "SP_EXAM.screen==='exam'", 20), \
        pg.evaluate("SPX_TEST.state()")
    pg.evaluate(TALK_THROUGH_TURN)
    assert wait_until(
        pg, "SP_EXAM.screen==='feedback' || SP_EXAM.screen==='report'", 180), \
        pg.evaluate("SPX_TEST.state()")

    final = pg.evaluate("() => SPX_TEST.state()")
    pg.evaluate("() => { window.__clockDriver = false; SP_EXAM.close(); }")

    plan = {int(entry["part"]): entry for entry in final.get("plan") or []}
    stats = final.get("partStats") or {}
    assert sorted(plan) == list(PARTS), plan
    assert sorted(int(k) for k in stats) == list(PARTS), stats

    measured = []
    total_planned = 0
    total_measured = 0
    running = 0
    for part in PARTS:
        st = stats[str(part)]
        says = plan[part]["seconds"]
        assert st["planned"] == says, \
            "part %d: the ledger says %r s but the exam says %r s" % (
                part, st["planned"], says)
        assert says > 0, "part %d has no budget: %r" % (part, says)
        delta = st["seconds"] - says
        assert abs(delta) <= TOLERANCE_S, \
            "part %d lasted %r s against a budget of %r s (%+d s)" % (
                part, st["seconds"], says, delta)
        # The ledger rounds the wall clock to 0.1 s, so the exam-time seconds
        # have to land on the wall the part really took. A part that echoed
        # its budget instead of measuring would drift away from this.
        wall_s = st["seconds"] * TIME_SCALE
        assert abs(st["wall"] - wall_s) <= 0.1, \
            "part %d reports %r s of exam time but wall says %r s (%.2f s " \
            "expected)" % (part, st["seconds"], st["wall"], wall_s)
        measured.append({"part": part, "planned": says,
                         "seconds": st["seconds"], "wall": st["wall"],
                         "delta": delta})
        total_planned += says
        total_measured += st["seconds"]
        # Checked after every part, not only at the end: a part that runs long
        # and a later one that runs short must not cancel each other out.
        running += delta
        assert abs(running) <= TOLERANCE_S, \
            "after part %d the clock had drifted %+d s from its budget: %r" % (
                part, running, measured)

    drift = total_measured - total_planned
    assert abs(drift) <= TOLERANCE_S, \
        "the four parts drifted %+d s from their budgets: %r" % (drift, measured)

    assert page_errors == [], page_errors
    out = {"time_scale": TIME_SCALE, "tolerance_s": TOLERANCE_S,
           "parts": measured, "drift_s": drift, "page_errors": page_errors}
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
