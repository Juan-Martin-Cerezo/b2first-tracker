"""Part 2 photographs are fetched before the task card is shown.

Two checks:
  A. Opening the exam starts the download of the first Part 2 task, so the card
     is never the first thing that asks for those files.
  B. Moving to the next task of a session preloads its photographs while the
     current task is still on screen. The switch is then captured synchronously:
     right after the next task renders, both images must already be complete and
     decoded (naturalWidth > 0) and no placeholder may be in the DOM. Without
     the preload the first frame has two empty <img> elements and this fails.

Run:  uv run --with playwright python test_speaking_preload.py
"""
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

OUT_DIR = os.path.join(TESTS, "out")
URL = helpers.isolated_server() + "/"
SEED = 20261104


def wait_until(pg, expression, timeout_s, step=50):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if pg.evaluate(expression):
            return True
        pg.wait_for_timeout(step)
    return False


def open_app(p):
    browser = p.chromium.launch(args=[
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
    ])
    context = browser.new_context(viewport={"width": 1200, "height": 900},
                                  permissions=["microphone"])
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(URL, wait_until="load")
    helpers.login_owner(page, URL)
    page.evaluate("localStorage.setItem('spx_test','1')")
    page.goto(URL + "app?spx_test=1", wait_until="networkidle")
    page.wait_for_timeout(350)
    helpers.dismiss_onboarding(page)
    assert page.evaluate("!!window.SPX_TEST"), "SPX_TEST was not exposed"
    return browser, page, errors


def basename(src):
    return str(src or "").split("/")[-1]


def test_preload(p):
    browser, page, errors = open_app(p)
    try:
        # A. Opening the exam warms the first Part 2 task.
        page.evaluate("async () => { await SP_EXAM.open(); }")
        first_task = page.evaluate("""() => {
            const p2 = SP_EXAM.bank.parts.find(p => Number(p.part) === 2);
            return {id: p2.tasks[0].id, photos: p2.tasks[0].photos.slice()};
        }""")
        print("A. first Part 2 task:", first_task["id"], first_task["photos"])
        assert wait_until(
            page, """() => {
                const p2 = SP_EXAM.bank.parts.find(p => Number(p.part) === 2);
                return spxTaskPhotosReady(p2.tasks[0]);
            }""", 20), "opening the exam did not preload the first Part 2 task"

        # B. A session preloads the next task while the current one is on screen.
        page.evaluate("async (seed) => { await SP_EXAM.startFull(seed); }", SEED)
        expected = page.evaluate("""() => {
            const part = SP_EXAM.session.plan.parts.find(p => Number(p.part) === 2);
            return part.task.photos.map(src => src.split('/').pop());
        }""")
        print("B. planned Part 2 photos:", expected)
        assert len(expected) == 2, expected

        page.evaluate("""() => { spxSetScreen('exam'); spxEnterSessionPart(0); }""")
        assert wait_until(
            page, """() => {
                const s = SP_EXAM.session;
                const next = s.plan.parts[s.partIndex + 1];
                return !!next && spxTaskPhotosReady(next.task);
            }""", 20), "the next task was not preloaded while the current task was on screen"

        # Capture the first frame after the change of task in the same JS turn:
        # no network or event loop can rescue a missing preload.
        first_frame = page.evaluate("""() => {
            spxEnterSessionPart(1);
            const imgs = Array.from(document.querySelectorAll('#spxTask .spx-photo img'));
            const state = {
                part: SP_EXAM.part,
                images: imgs.map(img => ({
                    src: (img.currentSrc || img.src).split('/').pop(),
                    complete: img.complete,
                    w: img.naturalWidth,
                })),
                placeholders: document.querySelectorAll('#spxTask .spx-photo-missing').length,
            };
            spxStopTimer();
            return state;
        }""")
        page.screenshot(path=os.path.join(OUT_DIR, "spx_preload_part2.png"))
        print("B. first frame after the change:", first_frame)

        assert first_frame["part"] == 2, first_frame
        assert first_frame["placeholders"] == 0, \
            "the changed task showed a placeholder card: %s" % first_frame
        assert len(first_frame["images"]) == 2, first_frame["images"]
        assert [basename(i["src"]) for i in first_frame["images"]] == expected, \
            "the rendered task is not the preloaded one: %s" % first_frame
        for img in first_frame["images"]:
            assert img["complete"], "blank frame: %s was still loading" % img
            assert img["w"] > 200, "frame not decoded: %s" % img

        assert not errors, "page errors: %s" % errors[:3]
    finally:
        page.evaluate("() => { try { SP_EXAM.close(); } catch (e) {} }")
        browser.close()


def main():
    with sync_playwright() as p:
        test_preload(p)
    print("OK: Part 2 photos are preloaded on open and on the change of task")


if __name__ == "__main__":
    main()
