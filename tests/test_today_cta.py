"""Regression: Today's session CTAs stack when the card is narrow.

Seeds a profile whose schedule includes today, syncs the progress document and
measures the two buttons inside `.ts-actions` at three viewports:

  * 360x740 and 768x1024 (narrow card): both buttons share the same width, fill
    at least 95% of the actions container and sit on different rows (stacked).
  * 1280x800 (wide card): both buttons stay on the same row.

Every viewport must also avoid horizontal scrolling. The measured JSON for each
viewport is printed; any failed assertion exits non-zero.

Run:  cd tests && uv run --with playwright python test_today_cta.py
"""
import json
import urllib.request
from datetime import date

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
NAME = "today-cta-suite"
PASS = "today-cta-suite-pass-9"

# JS getDay(): 0=Sunday … 6=Saturday; date.isoweekday(): Mon=1 … Sun=7.
DAY_NUM = date.today().isoweekday() % 7
DAY_KEY = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][DAY_NUM]

# label, width, height, mobile emulation, expected layout
VIEWPORTS = [
    ("phone", 360, 740, True, "stacked"),
    ("tablet", 768, 1024, True, "stacked"),
    ("desktop", 1280, 800, False, "row"),
]

MEASURE_JS = """() => {
    const card = document.getElementById('todaySession');
    const row = card ? card.querySelector('.ts-row:not(.ts-next-unit)') : null;
    const actions = row ? row.querySelector('.ts-actions') : null;
    const buttons = actions ? Array.from(actions.querySelectorAll('button')) : [];
    const ar = actions ? actions.getBoundingClientRect() : null;
    const rects = buttons.map(b => b.getBoundingClientRect());
    return {
        rows: card ? card.querySelectorAll('.ts-row:not(.ts-next-unit)').length : 0,
        rest: !!(card && card.querySelector('[data-rest]')),
        count: buttons.length,
        labels: buttons.map(b => b.textContent.trim()),
        cardWidth: card ? card.getBoundingClientRect().width : 0,
        actionsWidth: ar ? ar.width : 0,
        widths: rects.map(r => Math.round(r.width * 10) / 10),
        tops: rects.map(r => Math.round(r.top * 10) / 10),
        sameRow: rects.length === 2 && Math.abs(rects[0].top - rects[1].top) <= 1,
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
    };
}"""


def seed_progress(user):
    """One session on today's weekday so Today renders its two CTAs."""
    schedule = [{"day": DAY_NUM, "time": "17:00"}]
    doc = {
        "log": [], "errs": [], "examDates": [], "stage": 1,
        "settings": {
            "lang": "en",
            "schedule": schedule,
            "sessions": schedule,
            "rotationMode": "by-part",
            "itemsPerSession": 1,
        },
        "overrides": {}, "weekOverrides": {}, "mat": {},
        "diag": None,
        "profile": {
            "examDate": None, "targetGrade": "B",
            "skills": {"rue": 3, "w": 3, "l": 3, "sp": 3},
            "hoursWeek": 4, "days": [DAY_KEY],
            "struggles": [], "strugglesDeclared": [],
        },
        "onboarded": True, "sessionOffset": 0,
    }
    req = urllib.request.Request(
        URL + "api/progress?user=" + user["id"],
        data=json.dumps(doc).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + user["token"],
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        r.read()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        boot = browser.new_context(viewport={"width": 1280, "height": 800})
        pg = boot.new_page()
        pg.goto(URL + "app", wait_until="networkidle")
        user = login_user(pg, URL, NAME, PASS)
        seed_progress(user)
        boot.close()

        for label, width, height, mobile, expected in VIEWPORTS:
            ctx = browser.new_context(
                viewport={"width": width, "height": height},
                is_mobile=mobile, has_touch=mobile, device_scale_factor=1,
            )
            pg = ctx.new_page()
            pg.add_init_script(
                "localStorage.setItem('b2first_user', %s);"
                % json.dumps(json.dumps(user))
            )
            pg.goto(URL + "app", wait_until="networkidle")
            pg.evaluate("syncPull()")
            pg.evaluate("if (typeof hideOnboarding === 'function') hideOnboarding();")
            pg.evaluate("showView('hoy')")
            pg.wait_for_selector("#todaySession .ts-actions button", timeout=8000)
            pg.wait_for_timeout(300)

            data = pg.evaluate(MEASURE_JS)
            row = {
                "viewport": label,
                "size": "%dx%d" % (width, height),
                "expected": expected,
                "scroll": data["scrollWidth"] <= data["innerWidth"] + 1,
                **data,
            }
            print(json.dumps(row))
            ctx.close()

            assert data["rows"] == 1 and not data["rest"], (
                "%s: Today is not showing today's session: %s" % (label, data)
            )
            assert data["count"] == 2, (
                "%s: expected 2 session buttons, got %d: %s"
                % (label, data["count"], data)
            )
            assert data["scrollWidth"] <= data["innerWidth"] + 1, (
                "%s: horizontal scroll %d > %d"
                % (label, data["scrollWidth"], data["innerWidth"])
            )

            if expected == "stacked":
                assert abs(data["widths"][0] - data["widths"][1]) <= 1, (
                    "%s: buttons have different widths: %s" % (label, data["widths"])
                )
                assert data["widths"][0] >= 0.95 * data["actionsWidth"], (
                    "%s: button width %s < 95%% of container %s"
                    % (label, data["widths"][0], data["actionsWidth"])
                )
                assert abs(data["tops"][0] - data["tops"][1]) > 1, (
                    "%s: buttons are not stacked: tops %s"
                    % (label, data["tops"])
                )
            else:
                assert data["sameRow"] is True, (
                    "%s: buttons left the same row: tops %s" % (label, data["tops"])
                )

        browser.close()


if __name__ == "__main__":
    main()
