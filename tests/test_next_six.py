"""Phase 99: "What comes next" offers exactly the units the log still owes.

The six rows of the card come from D.log: a unit already done in the current
pass is skipped, a repeated exercise never moves the queue twice, a closed pass
starts again from its first unit, and no unit is offered twice before its pass
is exhausted. Rows are checked against the log, not against a stored cursor.
"""
import json
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}

DAY_NUM = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}

# The product's passes, as the card names them.
CYCLES = {
    "rue": [1, 2, 3, 4, 5, 6, 7],
    "l": [1, 2, 3, 4],
    "w": ["Essay", "Article", "Report", "Review", "Email"],
    "sp": [1, 2, 3, 4],
}
LABELS = [
    ("rue", re.compile(r"^Reading part (\d+)$")),
    ("l", re.compile(r"^Listening part (\d+)$")),
    ("w", re.compile(r"^Writing (\S+)$")),
    ("sp", re.compile(r"^Speaking part (\d+)$")),
]
LOG_TYPE = {"rue": "ue", "l": "lp", "w": "w", "sp": "sp"}

READ_JS = """() => [...document.querySelectorAll('#planUpcomingPreview .up-row')]
    .map(r => ({
        day: r.dataset.day,
        label: ((r.querySelector('.badge') || {}).textContent || '').trim(),
    }))"""

SEED_JS = """([schedule, per, log]) => {
    D.log = log.slice();
    D.sessionOffset = 0;
    D.weekOverrides = {};
    D.settings.schedule = schedule;
    D.settings.rotationMode = 'by-part';
    D.settings.itemsPerSession = per;
    save();
    refreshAll();
}"""


def rows(*units, day="2026-10-01"):
    """Log rows for (skill, value) pairs, one date per row, oldest first."""
    out = []
    for i, (skill, value) in enumerate(units):
        row = {"type": LOG_TYPE[skill], "date": "%s-%02d" % (day, i + 1), "min": 10}
        if skill == "w":
            row["kind"] = value
        else:
            row["part"] = value
        out.append(row)
    return out


def parse(label):
    for skill, rx in LABELS:
        m = rx.match(label)
        if m:
            raw = m.group(1)
            if skill == "w":
                return skill, next(v for v in CYCLES["w"] if v.lower() == raw.lower())
            return skill, int(raw)
    raise AssertionError("the card named an unknown unit: %r" % label)


def owed(skill, values, count):
    """The next units of one skill from its logged units: pending in this pass
    (pass order, skipping what is done), then the following passes whole."""
    cycle = CYCLES[skill]
    total = len(cycle)
    done = set()
    for value in values:
        if len(done) >= total:
            done = set()
        done.add(value)
    out = [value for value in cycle if value not in done]
    while len(out) < count:
        out += list(cycle)
    return out[:count]


def seed_units(log):
    out = {}
    for row in log:
        if row["type"] == "ue":
            out.setdefault("rue", []).append(row["part"])
        elif row["type"] == "lp":
            out.setdefault("l", []).append(row["part"])
        elif row["type"] == "w":
            out.setdefault("w", []).append(row["kind"])
        elif row["type"] == "sp":
            out.setdefault("sp", []).append(row["part"])
    return out


def seed(pg, log, per=1, days=("mon", "fri")):
    schedule = [{"day": DAY_NUM[d], "time": "15:30"} for d in days]
    pg.evaluate(SEED_JS, [schedule, per, log])
    pg.wait_for_timeout(250)
    return pg.evaluate(READ_JS)


def check(card, log, per, label, days=("mon", "fri")):
    """Six rows, and per skill exactly what the log leaves pending in order."""
    assert len(card) == 6, "%s: the card did not list six units: %r" % (label, card)
    want_days = [days[(i // per) % len(days)] for i in range(6)]
    assert [r["day"] for r in card] == want_days, (
        "%s: the days of the sessions are wrong: %r (want %r)" % (label, card, want_days)
    )
    done = seed_units(log)
    shown = {}
    for row in card:
        skill, value = parse(row["label"])
        shown.setdefault(skill, []).append(value)
    for skill, values in shown.items():
        want = owed(skill, done.get(skill, []), len(values))
        assert values == want, (
            "%s: %s offers %r but the log still owes %r" % (label, skill, values, want)
        )
    return [r["label"] for r in card]


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(250)

    # 1. Empty log: the first unit of every pass, in queue order.
    labels = check(seed(pg, []), [], 1, "empty")
    assert labels == [
        "Reading part 1", "Listening part 1", "Writing essay",
        "Speaking part 1", "Reading part 2", "Listening part 2",
    ], labels
    OUT["1_empty"] = labels

    # 2. Partial pass: parts 1 and 2 are done, so the next Reading session owes
    #    part 3. The old row count repeated part 2 here.
    partial = rows(("rue", 1), ("rue", 2))
    labels = check(seed(pg, partial), partial, 1, "partial")
    assert labels == [
        "Writing essay", "Speaking part 1", "Reading part 3",
        "Listening part 1", "Writing article", "Speaking part 2",
    ], labels
    OUT["2_partial"] = labels

    # 3. The same unit logged twice moves the queue once: the six rows are the
    #    same as with the two distinct parts.
    repeated = rows(("rue", 1), ("rue", 1), ("rue", 2))
    repeated_labels = check(seed(pg, repeated), repeated, 1, "repeated")
    assert repeated_labels == labels, (
        "a repeated exercise moved the queue: %r vs %r" % (repeated_labels, labels)
    )
    OUT["3_repeated"] = repeated_labels

    # 4. Parts done out of order are still skipped, not repeated.
    unordered = rows(("rue", 3), ("rue", 4))
    labels = check(seed(pg, unordered), unordered, 1, "unordered")
    assert labels[2] == "Reading part 1", labels
    for label in labels:
        skill, value = parse(label)
        if skill == "rue":
            assert value not in (3, 4), "a done Reading part is offered again: %r" % labels
    OUT["4_unordered"] = labels

    # 5. A closed pass restarts at its first unit instead of continuing past it.
    closed = rows(*[("rue", part) for part in range(1, 8)])
    labels = check(seed(pg, closed), closed, 1, "closed")
    assert labels == [
        "Speaking part 1", "Reading part 1", "Listening part 1",
        "Writing essay", "Speaking part 2", "Reading part 2",
    ], labels
    OUT["5_closed"] = labels

    # 6. Two exercises per session: both units of the session come from what the
    #    pass still owes, and the pass is not restarted early.
    five = rows(*[("rue", part) for part in range(1, 6)])
    labels = check(seed(pg, five, per=2), five, 2, "per2")
    assert labels == [
        "Writing essay", "Writing article", "Speaking part 1",
        "Speaking part 2", "Reading part 6", "Reading part 7",
    ], labels
    OUT["6_per_session"] = labels

    # 7. The card follows a log written after it was first painted.
    seed(pg, [])
    pg.evaluate(
        """() => {
            D.log = [{type: 'ue', part: 1, date: '2026-10-01'},
                     {type: 'ue', part: 2, date: '2026-10-02'}];
            save();
            renderRotationCard();
        }"""
    )
    pg.wait_for_timeout(200)
    live = [r["label"] for r in pg.evaluate(READ_JS)]
    assert live[2] == "Reading part 3", "the card did not follow the new log: %r" % live
    OUT["7_after_logging"] = live

    assert page_errors == [], "page errors: %r" % page_errors
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
