"""Phase 26 acceptance: practice sources catalogue and one-tap access.

Standalone Playwright suite. It logs in through helpers.py, opens the Practice
screen from the main nav, and checks the catalogue, the filters, the free-only
toggle and the "Practise this now" row on Today.

Link liveness is deliberately NOT part of this suite: run
`python3 tools/check_sources.py` by hand for that report.

Run with:  uv run --with playwright python test_sources.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

from helpers import login_owner

URL = "http://127.0.0.1:8088/"
SKILLS = ["rue", "w", "l", "sp"]
KINDS = ["free", "freemium", "paid"]


def card_state(pg):
    return pg.evaluate(
        """() => {
        const cards = [...document.querySelectorAll('#practiceGrid .practice-card')];
        return {
            n: cards.length,
            skills: [...new Set(cards.map(c => c.dataset.skill))],
            kinds: [...new Set(cards.map(c => c.dataset.kind))],
        };
    }"""
    )


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    page_errors = []
    console_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.on(
        "console",
        lambda m: console_errors.append(m.text)
        if m.type == "error" and "Failed to load resource" not in m.text
        else None,
    )

    pg.goto(URL, wait_until="networkidle")
    login_owner(pg, URL)

    # --- 1. The Practice item is in the nav and opens the screen ----------
    assert pg.evaluate(
        "!!document.querySelector(\"nav button[data-view='practice']\")"
    ), "Practice is not in the main navigation"
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(300)
    assert pg.evaluate(
        "document.getElementById('v-practice').classList.contains('active')"
    ), "Practice did not become the active view"

    # --- 2. The catalogue is big enough and has the right shape -----------
    sources = pg.evaluate(
        """() => (typeof PRACTICE_SOURCES !== 'undefined' ? PRACTICE_SOURCES : [])
        .map(s => ({n: s.n, url: s.url, skill: s.skill, kind: s.kind,
                    what: s.what, mins: s.mins, part: s.part}))"""
    )
    assert len(sources) >= 18, f"Only {len(sources)} practice sources (need 18+)"
    for s in sources:
        assert s["n"], f"source without a name: {s}"
        assert isinstance(s["url"], str) and s["url"].startswith("https://"), f"bad URL: {s}"
        assert s["skill"] in SKILLS, f"bad skill: {s}"
        assert s["kind"] in KINDS, f"bad kind: {s}"
        assert isinstance(s["what"], str) and len(s["what"]) > 20, f"'what' too short: {s}"
        assert isinstance(s["mins"], int) and s["mins"] > 0, f"bad mins: {s}"

    expected = {k: sum(1 for s in sources if s["skill"] == k) for k in SKILLS}
    assert all(v > 0 for v in expected.values()), f"a skill has no sources: {expected}"

    # --- 3. Filter chips really filter, and the parts add up --------------
    pg.click("#practiceFilter [data-skill='all']")
    pg.wait_for_timeout(120)
    all_state = card_state(pg)
    assert all_state["n"] == len(sources), f"All shows {all_state['n']}, catalogue {len(sources)}"

    filtered = {}
    for skill in SKILLS:
        pg.click(f"#practiceFilter [data-skill='{skill}']")
        pg.wait_for_timeout(120)
        state = card_state(pg)
        filtered[skill] = state["n"]
        assert state["n"] == expected[skill], f"{skill}: {state['n']} cards, expected {expected[skill]}"
        assert state["skills"] == [skill], f"{skill} filter leaked: {state['skills']}"
        assert state["n"] != all_state["n"], f"{skill} did not change the count"
    assert sum(filtered.values()) == len(sources), (
        f"filtered counts {filtered} do not add up to {len(sources)}"
    )

    # --- 4. Free-only hides every non-free source -------------------------
    pg.click("#practiceFilter [data-skill='all']")
    pg.wait_for_timeout(120)
    pg.check("#practiceFreeOnly")
    pg.wait_for_timeout(120)
    free_state = card_state(pg)
    free_total = sum(1 for s in sources if s["kind"] == "free")
    assert free_state["n"] == free_total, f"Free only shows {free_state['n']}, expected {free_total}"
    assert free_state["kinds"] in (["free"], []), f"non-free sources leaked: {free_state['kinds']}"
    pg.uncheck("#practiceFreeOnly")
    pg.wait_for_timeout(120)
    assert card_state(pg)["n"] == len(sources), "turning Free only off did not restore the list"

    # --- 5. Every card link opens safely in a new tab ---------------------
    links = pg.eval_on_selector_all(
        "#practiceGrid a",
        """els => els.map(a => ({href: a.getAttribute('href'),
                                target: a.getAttribute('target'),
                                rel: a.getAttribute('rel')}))""",
    )
    assert len(links) == len(sources), f"{len(links)} links for {len(sources)} cards"
    for a in links:
        assert a["href"] and a["href"].startswith("https://"), f"bad card link: {a}"
        assert a["target"] == "_blank", f"card link without target=_blank: {a}"
        assert a["rel"] == "noopener noreferrer", f"card link without rel=noopener noreferrer: {a}"

    # --- 6. Today shows 1-3 one-tap sources under the daily suggestion ----
    pg.click("nav button[data-view='hoy']")
    pg.wait_for_timeout(300)
    now = pg.evaluate(
        """() => {
        const box = document.getElementById('practiceNow');
        if (!box) return null;
        const links = [...box.querySelectorAll('a')];
        return {
            shown: getComputedStyle(box).display !== 'none',
            n: links.length,
            attrs: links.map(a => ({
                href: a.getAttribute('href'),
                target: a.getAttribute('target'),
                rel: a.getAttribute('rel')
            }))
        };
    }"""
    )
    assert now, "Today has no #practiceNow row"
    assert now["shown"], "the Practise this now row is hidden"
    assert 1 <= now["n"] <= 3, f"Practise this now rendered {now['n']} links (need 1-3)"
    for a in now["attrs"]:
        assert a["href"] and a["href"].startswith("https://"), f"bad now link: {a}"
        assert a["target"] == "_blank", f"now link without target=_blank: {a}"
        assert a["rel"] == "noopener noreferrer", f"now link without rel=noopener noreferrer: {a}"

    # --- 7. Zero console / page errors -----------------------------------
    assert page_errors == [], f"page errors: {page_errors}"
    assert console_errors == [], f"console errors: {console_errors}"

    out = {
        "sources": len(sources),
        "by_skill": expected,
        "filtered": filtered,
        "free_only": free_total,
        "now_links": now["n"],
        "page_errors": page_errors,
        "console_errors": console_errors,
    }
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
sys.exit(0)
