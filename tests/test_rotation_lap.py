"""Phase 90: the rotation card says which lap of the cycle the user is on.

The card divides the sessions logged for a skill by the length of its cycle:
0 sessions start the first lap, 1 session leaves three to close it, a full lap
moves on to the next. The lap line is bilingual.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"

SEED = """(count) => {
    D.log = [];
    for (let i = 0; i < count; i++) {
        D.log.push({date: '2026-10-0' + ((i % 9) + 1), type: 'ue', part: (i % 4) + 1,
                    correct: 6, total: 8, min: 10});
    }
    D.settings.rueCycle = [1, 2, 3, 4];
    applyCycleInputs();
    document.getElementById('pRueCycle').value = '1,2,3,4';
    save();
    renderRotationCard();
}"""

READ = """() => {
    const el = document.querySelector('#rotationCardBody .rot-skill[data-skill="rue"]');
    if (!el) return null;
    const lap = el.querySelector('.rot-lap');
    const pos = el.querySelector('.rot-pos');
    return {
        lap: lap ? lap.textContent.trim() : null,
        pos: pos ? pos.textContent.trim() : null,
        count: rotationPosition(ROTATION_DEFS.find(d => d.key === 'rue'),
                                rotationCycle(ROTATION_DEFS.find(d => d.key === 'rue'))).count,
    };
}"""

out = {}
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
    pg.wait_for_timeout(300)

    # 0 sessions: first lap, nothing done yet, the whole cycle is left.
    pg.evaluate(SEED, 0)
    pg.wait_for_timeout(150)
    zero = pg.evaluate(READ)
    assert zero and zero["count"] == 0, f"the seed did not leave an empty log: {zero}"
    assert zero["lap"] == "lap 1 · 4 to close it", (
        f"0 sessions is not on the first lap: {zero['lap']!r}"
    )
    out["0_sessions"] = zero

    # 1 session: still the first lap, three sessions left.
    pg.evaluate(SEED, 1)
    pg.wait_for_timeout(150)
    one = pg.evaluate(READ)
    assert one and one["count"] == 1, f"the seed did not log one session: {one}"
    assert one["lap"] == "lap 1 · 3 to close it", (
        f"1 session reports the wrong remainder: {one['lap']!r}"
    )
    out["1_session"] = one

    # One full cycle: the lap closes and the next one starts with all four left.
    pg.evaluate(SEED, 4)
    pg.wait_for_timeout(150)
    four = pg.evaluate(READ)
    assert four and four["count"] == 4, f"the seed did not log four sessions: {four}"
    assert four["lap"] == "lap 2 · 4 to close it", (
        f"a full cycle does not move to the next lap: {four['lap']!r}"
    )
    assert four["pos"] == "4 sessions logged", (
        f"the session count line changed: {four['pos']!r}"
    )
    out["4_sessions"] = four

    # Mid-lap on a later lap: two of four done on lap 2.
    pg.evaluate(SEED, 6)
    pg.wait_for_timeout(150)
    six = pg.evaluate(READ)
    assert six and six["count"] == 6, f"the seed did not log six sessions: {six}"
    assert six["lap"] == "lap 2 · 2 to close it", (
        f"a later lap does not count its remainder: {six['lap']!r}"
    )
    out["6_sessions"] = six

    # Spanish dictionary carries the line too.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(400)
    es = pg.evaluate(READ)
    assert es["lap"] == "vuelta 2 · 2 para cerrarla", (
        f"the Spanish lap line is missing: {es['lap']!r}"
    )
    out["spanish"] = es

    # The pure function agrees with the DOM at the edges.
    edges = pg.evaluate(
        "() => [rotationLap(0, 4), rotationLap(3, 4), rotationLap(4, 4), rotationLap(9, 4)]"
    )
    assert edges == [
        {"lap": 1, "left": 4},
        {"lap": 1, "left": 1},
        {"lap": 2, "left": 4},
        {"lap": 3, "left": 3},
    ], f"rotationLap is wrong at the edges: {edges}"
    out["edges"] = edges

    # Both dictionaries carry the key the line uses.
    keys = pg.evaluate(
        "() => ['plan_rotation_lap'].filter(k => !I18N.en[k] || !I18N.es[k])"
    )
    assert keys == [], f"keys missing from a dictionary: {keys}"
    out["keys"] = keys

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
