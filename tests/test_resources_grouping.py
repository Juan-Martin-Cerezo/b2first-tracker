"""Phase 82: every skill groups its documents by official sample.

Each sample gets one card (questions, audio, tapescript, answer key, lesson
plan). Online links come before local files inside a card, and a sample with
no documents never paints an empty card.
"""
import json
import os

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

MAT_KEYS = [
    # Reading & Use of English samples and keys
    "rueS1", "rueS2", "rueFS1", "rueFS2",
    "keyS1", "keyS2", "keyFS1", "keyFS2",
    # Reading lesson plans (B2 First and For Schools)
    *["lpR%d" % n for n in range(1, 8)],
    *["fR%d" % n for n in range(1, 8)],
    # Writing samples and lesson plans
    "wS1", "wS2", "wFS1", "wFS2",
    "lpW1", "lpW2", "fW1", "fW2",
    # Listening samples, audio, tapescripts, keys and lesson plans
    "lS1", "lS2", "lFS1", "lFS2", "auS1", "auFS2",
    *["auS2p%d" % n for n in range(1, 5)],
    *["auFS1p%d" % n for n in range(1, 5)],
    "tsS1", "tsFS1", "lkS1", "lkS2", "lkFS1", "lkFS2",
    *["lpL%d" % n for n in range(1, 5)],
    *["fL%d" % n for n in range(1, 5)],
    *["fL%da" % n for n in range(1, 5)],
    "lGuide",
    # Speaking samples and lesson plans
    "spS1", "spS2", "spFS1", "spFS2",
    *["lpSp%d" % n for n in range(1, 5)],
    *["fSp%d" % n for n in range(1, 5)],
    # Self-study / guides / examiner comments
    "rAct1", "rAct1b", "rAct2", "rGuide",
    "wCheck", "wAct1", "wAct2", "wGuide",
    "spAct", "spGuide",
    *["exC%d" % n for n in range(0, 6)],
]

# renderResources keys reading as "ue" and listening as "lp".
SKILLS = [("rue", "ue"), ("w", "w"), ("l", "lp"), ("sp", "sp")]


def is_sample(dom, title):
    """A sample card: per-skill cards for RUE/W/SP, test cards for Listening."""
    if dom == "lp":
        return title.startswith("Listening test") or title.startswith("Full test")
    return "Sample Paper" in title

out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 1000})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    pg.evaluate(
        """(keys) => {
        MAT = {};
        keys.forEach(k => { MAT[k] = '/files/test-' + k + '.pdf'; });
        renderResources();
    }""",
        MAT_KEYS,
    )
    pg.evaluate("showView('resources')")
    pg.wait_for_timeout(300)

    # 1. One sample card per skill, and the header names skill + sample.
    out["samples"] = {}
    for skill, dom in SKILLS:
        cards = pg.eval_on_selector_all(
            f"#resourcesList .res-paper[data-res-type='{dom}'] .listen-test",
            """els => els.map(e => ({
                title: e.querySelector('.lt-head').textContent.trim(),
                hrefs: [...e.querySelectorAll('a.chip')].map(a => a.getAttribute('href')),
                labels: [...e.querySelectorAll('a.chip')].map(a => a.textContent.trim())
            }))""",
        )
        assert cards, f"no cards rendered for skill {skill}"
        samples = [c for c in cards if is_sample(dom, c["title"])]
        assert samples, f"no sample card for skill {skill}: {[c['title'] for c in cards]}"
        for card in samples:
            paper = card["title"].split(" · ")[0]
            if dom == "lp":
                assert paper.startswith("Listening") or paper.startswith("Full test"), (
                    f"sample card header lacks the skill: {card['title']}"
                )
            else:
                assert paper in (
                    "Reading & Use of English", "Writing", "Speaking"
                ), f"sample card header lacks the skill: {card['title']}"

        # 2. Online links before local files inside every card.
        for card in cards:
            kinds = ["online" if h.startswith("http") else "local" for h in card["hrefs"]]
            if "online" in kinds and "local" in kinds:
                last_online = max(i for i, k in enumerate(kinds) if k == "online")
                first_local = min(i for i, k in enumerate(kinds) if k == "local")
                assert last_online < first_local, (
                    f"local file before an online link in {card['title']}: {card['hrefs']}"
                )
            assert all(card["labels"]), f"empty chip label in {card['title']}"
        out["samples"][skill] = [c["title"] for c in samples]

    pg.locator("#practiceResources").screenshot(path=os.path.join(OUT, "resources_samples.png"))

    # 3. A sample with no documents never paints a card.
    pg.evaluate("MAT = {}; renderResources();")
    pg.wait_for_timeout(200)
    empty_samples = []
    for skill, dom in SKILLS:
        empty = pg.eval_on_selector_all(
            f"#resourcesList .res-paper[data-res-type='{dom}'] .listen-test",
            """els => els.map(e => ({
                title: e.querySelector('.lt-head').textContent.trim(),
                chips: e.querySelectorAll('a.chip').length
            }))""",
        )
        assert all(c["chips"] for c in empty), f"a card rendered with no documents: {empty}"
        empty_samples += [c["title"] for c in empty if is_sample(dom, c["title"])]
    assert not empty_samples, f"an empty sample card was invented: {empty_samples}"
    out["empty_samples"] = empty_samples

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
