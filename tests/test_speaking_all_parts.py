"""All four parts of the Speaking exam, end to end, plus the photograph gate.

Three phases so nothing depends on catching a fast transition:

  A. gate     every Part 2 task has both photographs on disk (no browser needed)
  B. part 2   opens Part 2 directly and proves the two photos decoded on screen
  C. full run one complete mock: parts 1-4 planned, every part records turns,
              the exam reaches the report, and the page raised no error

Run:  uv run --with playwright python test_speaking_all_parts.py
"""
import json
import math
import os
import struct
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "out")
URL = os.environ.get("B2_URL", "http://127.0.0.1:8088/")


def make_wav(path):
    """A tone with speech/silence cycles for Chromium's fake capture device.

    It opens with over a second of near-silence on purpose: the AudioWorklet
    calibrates its noise floor from the first frames, so a file that starts
    mid-tone makes the threshold unreachable and the VAD never fires.
    """
    rate = 16000
    frames = bytearray(b"\x00\x00" * int(rate * 1.2))
    for _cycle in range(3):
        for i in range(int(rate * 1.2)):
            frames += struct.pack("<h", int(0.28 * 32767 * math.sin(2 * math.pi * 220 * i / rate)))
        frames += b"\x00\x00" * int(rate * 0.8)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return path


def photo_gate():
    bank = json.load(open(os.path.join(ROOT, "material", "speaking.json")))
    part2 = [p for p in bank["parts"] if p["part"] == 2][0]
    missing = []
    for task in part2["tasks"]:
        for rel in task["photos"]:
            path = os.path.join(ROOT, rel)
            if not os.path.exists(path) or os.path.getsize(path) < 8000:
                missing.append("%s (%s)" % (task["id"], rel))
    return missing


def main():
    missing = photo_gate()
    print("A. photo gate:", "all 24 present" if not missing else "%d MISSING" % len(missing))
    for m in missing:
        print("   missing", m)
    assert not missing, "Part 2 tasks without photographs: %s" % missing[:6]

    wav = make_wav(os.path.join(ROOT, "tests", "fixtures", "speech.wav"))
    # A private server over an empty data dir: no shared accounts, no per-IP rate
    # limits from repeated test runs, and nothing written to the real data/.
    URL = os.environ.get("B2_URL") or (helpers.isolated_server() + "/")
    tag = "sp4-%d" % int(time.time())
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
            "--use-file-for-fake-audio-capture=" + wav,
        ])
        page = browser.new_page(viewport={"width": 1100, "height": 1000}, color_scheme="dark")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL, wait_until="load")          # localStorage needs a real origin first
        helpers.login_user(page, URL, tag, tag + "-pass-123")
        page.goto(URL + "app?spx_test=1", wait_until="load")
        page.wait_for_timeout(600)
        helpers.dismiss_onboarding(page)

        # --- B. Part 2 on its own: the photographs must decode
        page.evaluate("async () => { SPX_TEST.timeScale = 0.05; await SPX_TEST.ensure() }")
        page.evaluate("async () => { await SP_EXAM.open(); SP_EXAM.select(2); await SP_EXAM.start(); await SP_EXAM.ready() }")
        page.wait_for_function(
            """() => {
                const imgs = Array.from(document.querySelectorAll('#spxTask .spx-photo img'));
                return imgs.length === 2 && imgs.every(i => i.complete && i.naturalWidth > 200);
            }""", timeout=20000)
        part2 = page.evaluate("""() => ({
            photos: Array.from(document.querySelectorAll('#spxTask .spx-photo img'))
                .map(i => ({w: i.naturalWidth, src: (i.currentSrc || i.src).split('/').pop()})),
            placeholders: document.querySelectorAll('#spxTask .spx-photo-missing').length,
            title: (document.getElementById('spxTask') || {}).innerText?.slice(0, 60),
        })""")
        page.screenshot(path=os.path.join(OUT, "sp4_part2.png"))
        print("B. part 2:", part2["photos"], "placeholders", part2["placeholders"],
              "| overlay", page.evaluate("() => getComputedStyle(document.getElementById('spxOverlay')).display"))
        assert part2["placeholders"] == 0, "Part 2 showed a text placeholder"
        visible = page.evaluate("""() => ({
            overlay: getComputedStyle(document.getElementById('spxOverlay')).display,
            panel: document.getElementById('spxPanel').offsetHeight,
        })""")
        assert visible["overlay"] == "flex" and visible["panel"] > 200, \
            "the exam panel is not on screen: %s" % visible
        assert len(part2["photos"]) == 2, "Part 2 did not render two photographs"
        for photo in part2["photos"]:
            assert photo["w"] > 200, "%s did not decode" % photo["src"]
        page.evaluate("() => SP_EXAM.close()")

        # --- C. a whole mock, from Part 1 to the report
        page.evaluate("async () => { SPX_TEST.timeScale = 0.03; await SPX_TEST.startFull(4242) }")
        deadline = time.time() + 240
        final = {}
        while time.time() < deadline:
            final = page.evaluate("() => SPX_TEST.state()")
            if final.get("screen") == "report":
                break
            page.wait_for_timeout(600)
        page.screenshot(path=os.path.join(OUT, "sp4_report.png"))
        browser.close()

    planned = [p.get("part") for p in (final.get("plan") or [])]
    stats = final.get("partStats") or {}
    print("C. planned parts:", planned)
    print("C. turn stats:", {k: v for k, v in stats.items()})
    print("C. screen:", final.get("screen"), "| page errors:", errors[:3])

    assert sorted(set(planned)) == [1, 2, 3, 4], "the mock did not plan all four parts: %s" % planned
    total_candidate_turns = 0
    for part in ("1", "2", "3", "4"):
        assert part in stats, "part %s recorded no turns" % part
        turns = stats[part].get("turns") or {}
        assert turns.get("examiner", 0) > 0, "part %s never had the examiner speaking: %s" % (part, turns)
        assert stats[part].get("seconds", 0) > 0, "part %s ran for zero seconds" % part
        total_candidate_turns += turns.get("candidate", 0)
    assert total_candidate_turns > 0, "the candidate never got a turn with speech on the fake mic"
    assert final.get("screen") in ("feedback", "report"), "the exam stalled at %s" % final.get("screen")
    assert not errors, "page errors: %s" % errors[:3]
    print("OK: four parts, two real photographs, no placeholder, candidate got turns, "
          "no page errors (ended on %s)" % final.get("screen"))


if __name__ == "__main__":
    main()
