"""Phase 97: the rotation covers all four skills evenly and never resets.

Four consecutive sessions show R&UE -> Listening -> Writing -> Speaking exactly
once, for itemsPerSession 1, 2 and 3, and the order repeats after that. Crossing
a week boundary (the day list cycling) continues the same global session count.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

SKILLS_JS = """([days, per, start, count]) => rotationQueueSessions(
    days, per, start, count
).map(s => s.units[0].skill)"""


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    cycle = ["rue", "l", "w", "sp"]
    for per in (1, 2, 3):
        first = pg.evaluate(SKILLS_JS, [["mon", "fri"], per, 0, 4])
        assert first == cycle, f"per={per} did not cover the four skills once: {first}"
        second = pg.evaluate(SKILLS_JS, [["mon", "fri"], per, 4, 4])
        assert second == cycle, f"per={per} did not repeat the cycle: {second}"
        OUT[f"per{per}_cycle"] = first + second

    # Crossing a week boundary: two days per week, eight sessions.
    crossing = pg.evaluate(SKILLS_JS, [["mon", "wed"], 1, 0, 8])
    assert crossing == cycle * 2, (
        f"the cycle reset at the week change: {crossing}"
    )
    OUT["week_crossing"] = crossing

    # The same holds for multi-unit sessions over a week boundary.
    crossing2 = pg.evaluate(SKILLS_JS, [["mon", "wed"], 2, 0, 8])
    assert crossing2 == cycle * 2, (
        f"the per=2 cycle reset at the week change: {crossing2}"
    )
    OUT["week_crossing_per2"] = crossing2

    # A mid-cycle start continues from where it is, never from the beginning.
    continued = pg.evaluate(SKILLS_JS, [["mon", "fri"], 1, 3, 8])
    assert continued == ["sp", "rue", "l", "w", "sp", "rue", "l", "w"], (
        f"a mid-cycle start reset the order: {continued}"
    )
    OUT["mid_cycle_start"] = continued

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
