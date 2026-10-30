"""S4 director acceptance: the pure turn state machine, no browser, no audio.

The director lives in index.html between the DIRECTOR markers and has no DOM or
network references. This test extracts that block, loads it in node and drives
it with scripted examiner/partner/candidate states, so every rule in the plan
§4 is asserted deterministically.

    cd tests && python test_speaking_director.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(REPO, "index.html")

RUNNER = """
const {spkDirectorTick} = require(process.argv[2]);
const steps = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
let state = null;
const out = [];
for (const input of steps) {
  const r = spkDirectorTick(state, input);
  state = r.state;
  out.push(r);
}
process.stdout.write(JSON.stringify(out));
"""


def director_source():
    html = open(HTML, encoding="utf-8").read()
    start = "DIRECTOR:START */"
    end = "/* DIRECTOR:END */"
    assert start in html and end in html, "the director markers are missing"
    return html[html.index(start) + len(start):html.index(end)]


def build_harness():
    tmp = tempfile.mkdtemp(prefix="b2spkdir-")
    src = os.path.join(tmp, "director.js")
    with open(src, "w", encoding="utf-8") as fh:
        fh.write(director_source())
        fh.write("\nmodule.exports={spkDirectorTick:spkDirectorTick};\n")
    runner = os.path.join(tmp, "runner.js")
    with open(runner, "w", encoding="utf-8") as fh:
        fh.write(RUNNER)
    return tmp, src, runner


NODE = shutil.which("node")


def run(steps):
    """Tick the director through `steps` (state starts null) and return results."""
    payload = os.path.join(HARNESS[0], "steps.json")
    with open(payload, "w", encoding="utf-8") as fh:
        json.dump(steps, fh)
    proc = subprocess.run([NODE, HARNESS[2], HARNESS[1], payload],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"node failed: {proc.stderr[:800]}"
    return json.loads(proc.stdout)


def step(part, t, ex=False, pa=False, ca=False, silence=0, text="", name=None):
    s = {"part": part, "t": t,
         "examiner": {"speaking": ex, "since": t},
         "partner": {"speaking": pa, "since": t},
         "candidate": {"speaking": ca, "silenceMs": silence},
         "transcriptTail": text}
    if name is not None:
        s["examinerName"] = name
    return s


def main():
    global HARNESS
    if not NODE:
        raise SystemExit("node is required: install Node.js or run node --check")
    HARNESS = build_harness()
    out = {}

    # 1-4. Part 1: examiner only; the partner session is never opened.
    r = run([step(1, 0, ex=True)])[-1]["out"]
    assert r["examiner"]["live"] is True, r
    assert r["examiner"]["muted"] is False, r
    assert r["partner"]["live"] is False, r
    assert r["partner"]["muted"] is True, r
    out["1_part1_examiner_only"] = (r["examiner"], r["partner"])

    # 5-8. Part 2: partner stays muted while the examiner asks and until the
    # candidate has actually spoken for 500 ms.
    steps = [
        step(2, 0, ex=True),
        step(2, 1000, ex=False),          # examiner done
        step(2, 1200, ca=True),           # candidate 200 ms
        step(2, 1400, ca=True),           # candidate 400 ms
    ]
    res = run(steps)
    assert res[1]["out"]["partner"]["muted"] is True, res[1]["out"]
    assert res[3]["out"]["phase"] == "ask", res[3]["out"]
    assert res[3]["out"]["partner"]["muted"] is True, res[3]["out"]
    assert res[3]["out"]["examiner"]["muted"] is False, res[3]["out"]
    out["2_part2_before_500ms"] = res[3]["out"]["phase"]

    res = run(steps + [step(2, 1600, ca=True)])[-1]["out"]
    assert res["phase"] == "candidate", res
    assert res["examiner"]["muted"] is True, res
    assert res["partner"]["muted"] is True, res
    out["3_part2_after_500ms"] = res["phase"]

    # 9-10. Part 2 timeout: 3 s without candidate speech repeats the instruction
    # once, and only once.
    res = run([step(2, 0, ex=True), step(2, 1000, ex=False),
               step(2, 3999, ex=False), step(2, 4000, ex=False),
               step(2, 5000, ex=False)])
    repeats = [e for r in res for e in r["out"]["events"] if e["type"] == "repeat"]
    assert len(repeats) == 1, repeats
    assert repeats[0]["who"] == "examiner", repeats[0]
    assert res[2]["out"]["events"] == [], "the repeat fired before 3 s"
    out["4_part2_repeat_once"] = repeats[0]

    # 11-12. Part 2: candidate 60 s then partner 30 s then examiner closes.
    base = steps + [step(2, 1600, ca=True)]
    res = run(base + [step(2, 61600, ex=False), step(2, 91600, ex=False)])
    assert res[-2]["out"]["phase"] == "partner", res[-2]["out"]
    assert res[-2]["out"]["partner"]["muted"] is False, res[-2]["out"]
    assert res[-2]["out"]["examiner"]["muted"] is True, res[-2]["out"]
    assert res[-1]["out"]["phase"] == "closing", res[-1]["out"]
    assert res[-1]["out"]["examiner"]["muted"] is False, res[-1]["out"]
    out["5_part2_60_30"] = (res[-2]["out"]["phase"], res[-1]["out"]["phase"])

    # 13-15. Part 3: the examiner introduces and goes quiet; the partner drives.
    res = run([step(3, 0, ex=True), step(3, 1500, ex=False)])
    assert res[0]["out"]["examiner"]["muted"] is False, res[0]["out"]
    assert res[0]["out"]["partner"]["muted"] is True, res[0]["out"]
    assert res[0]["out"]["partner"]["live"] is True, res[0]["out"]
    assert res[1]["out"]["phase"] == "partner", res[1]["out"]
    assert res[1]["out"]["examiner"]["muted"] is True, res[1]["out"]
    assert res[1]["out"]["partner"]["muted"] is False, res[1]["out"]
    out["6_part3_partner_drives"] = res[1]["out"]["phase"]

    # 16. Part 3: 2 s of dead air from both brings the examiner back, and both
    # stay live so overlap is possible.
    res = run([step(3, 0, ex=True), step(3, 1500, ex=False),
               step(3, 3499, ex=False), step(3, 3500, ex=False)])
    assert res[2]["out"]["phase"] == "partner", res[2]["out"]
    assert res[3]["out"]["phase"] == "examiner", res[3]["out"]
    assert res[3]["out"]["examiner"]["muted"] is False, res[3]["out"]
    assert res[3]["out"]["partner"]["muted"] is False, res[3]["out"]
    assert any(e["type"] == "examiner_return" for e in res[3]["out"]["events"]), \
        res[3]["out"]["events"]
    out["7_part3_dead_air"] = res[3]["out"]["phase"]

    # 17. Part 3: the candidate addresses the examiner by name.
    res = run([step(3, 0, ex=True), step(3, 1500, ex=False),
               step(3, 1600, ex=False, text="Sara, what do you think?", name="sara")])
    assert res[-1]["out"]["phase"] == "examiner", res[-1]["out"]
    assert any(e["type"] == "called" for e in res[-1]["out"]["events"]), \
        res[-1]["out"]["events"]
    out["8_part3_called_by_name"] = res[-1]["out"]["phase"]

    # 18. Part 3: overlap is allowed and measured, never negative.
    res = run([step(3, 0, ex=True), step(3, 1500, ex=False),
               step(3, 3500, ex=False), step(3, 3600, ex=True, pa=True),
               step(3, 3800, ex=True, pa=True)])
    assert res[-1]["out"]["overlap_ms"] == 300, res[-1]["out"]
    assert any(e["type"] == "overlap" for e in res[-2]["out"]["events"]), \
        "no overlap event at the start of the overlap"
    out["9_part3_overlap_ms"] = res[-1]["out"]["overlap_ms"]

    # 19-21. Part 4: direction by wording.
    def direction(text):
        return run([step(4, 0, ex=True), step(4, 1000, ex=False, text=text)])[-1]["out"]

    d_partner = direction("What does your partner think about that?")
    assert d_partner["partner"]["muted"] is False, d_partner
    assert d_partner["examiner"]["muted"] is True, d_partner
    d_you = direction("What do you think about that?")
    assert d_you["partner"]["muted"] is True, d_you
    assert d_you["examiner"]["muted"] is True, d_you
    d_default = direction("Now let's move on to the next question.")
    assert d_default["partner"]["muted"] is False, d_default
    out["10_part4_direction"] = (d_partner["addressed"], d_you["addressed"],
                                 d_default["addressed"])

    # 22. A backwards `t` does not advance timers, overlap or phases.
    res = run([step(3, 0, ex=True), step(3, 1500, ex=False),
               step(3, 3500, ex=False), step(3, 3600, ex=True, pa=True),
               step(3, 3700, ex=True, pa=True),
               step(3, 1000, ex=True, pa=True)])
    assert res[-1]["out"]["overlap_ms"] == res[-2]["out"]["overlap_ms"], res[-1]["out"]
    assert res[-1]["out"]["phase"] == res[-2]["out"]["phase"], res[-1]["out"]
    assert res[-1]["out"]["overlap_ms"] >= 0, res[-1]["out"]
    out["11_t_regression_safe"] = res[-1]["out"]["phase"]

    # 23. Idempotence: the same steps in two processes give the same result, and
    # a repeated tick at the same `t` never duplicates an event.
    steps = [step(2, 0, ex=True), step(2, 1000, ex=False),
             step(2, 4000, ex=False), step(2, 4000, ex=False)]
    a = run(steps)
    b = run(steps)
    assert json.dumps(a) == json.dumps(b), "the director is not deterministic"
    last_repeats = [e for e in a[-1]["out"]["events"] if e["type"] == "repeat"]
    assert last_repeats == [], f"the repeated tick duplicated the repeat: {last_repeats}"
    out["12_idempotent"] = True

    # 24. Purity: the extracted block touches neither the DOM, the clock nor the
    # network. If it ever does, this test is the one that notices.
    src = director_source()
    for forbidden in ("document.", "performance.", "Date.", "fetch(", "WebSocket"):
        assert forbidden not in src, f"the director is no longer pure: {forbidden}"
    out["13_pure"] = True

    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("OK: S4 director passed (pure, no browser)")


if __name__ == "__main__":
    main()
