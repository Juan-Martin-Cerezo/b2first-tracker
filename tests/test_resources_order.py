"""Phase 83: online practice leads each skill, and the nav never hides a card.

Inside every skill group the online practice card comes first and the
sample cards follow. In the library, the online block precedes the
downloads in the DOM. Finally, anchored scrolls (scroll 0 and
goToPartFilter) leave the destination below the sticky header, whose
height is measured at runtime instead of hard-coded.
"""
import json
import os

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# Enough documents for every skill to render one sample card after the
# online card, so the first-card check is not the only card in the group.
MAT_KEYS = [
    "rueS1", "keyS1", *["lpR%d" % n for n in range(1, 8)],
    "wS1", "lpW1", "lpW2",
    "lS1", "auS1", "tsS1", "lkS1", *["lpL%d" % n for n in range(1, 5)],
    "spS1", *["lpSp%d" % n for n in range(1, 5)],
]


def rect(pg, selector):
    return pg.eval_on_selector(
        selector,
        """el => { const r = el.getBoundingClientRect();
                 return {top: r.top, bottom: r.bottom, height: r.height}; }""",
    )


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
    pg.evaluate("window.scrollTo(0,0)")
    pg.wait_for_timeout(300)

    # 1. In every skill group, the first card is the online one: it carries
    #    an http link (and later cards prove the samples were rendered too).
    groups = pg.eval_on_selector_all(
        "#resourcesList .res-paper",
        """papers => papers.map(p => {
            const card = p.querySelector('.listen-test');
            return {
                type: p.dataset.resType,
                title: card ? card.querySelector('.lt-head').textContent.trim() : null,
                hrefs: card ? [...card.querySelectorAll('a.chip')].map(a => a.getAttribute('href')) : [],
                cards: p.querySelectorAll('.listen-test').length,
            };
        })""",
    )
    assert groups, "no skill group rendered"
    for group in groups:
        assert group["cards"] > 0, f"skill {group['type']} has no cards"
        assert any((h or "").startswith("http") for h in group["hrefs"]), (
            f"the first card of {group['type']} is not online: {group}"
        )
    out["first_card"] = {g["type"]: g["title"] for g in groups}

    # 2. Inside #practiceBooks the online block precedes the downloads in the
    #    DOM, not only on screen.
    dom_order = pg.evaluate(
        """() => {
        const books = document.getElementById('practiceBooks');
        const online = books && books.querySelector('#onlineList');
        const downloads = books && books.querySelector('#matList');
        if (!online || !downloads) return null;
        const FOLLOWING = 4; /* Node.DOCUMENT_POSITION_FOLLOWING */
        return {
            onlineBeforeDownloads: !!(online.compareDocumentPosition(downloads) & FOLLOWING),
            onlineCard: online.closest('.card') ? online.closest('.card').id : null,
            downloadCard: downloads.closest('.card') ? downloads.closest('.card').id : null,
        };
    }"""
    )
    assert dom_order, "#practiceBooks does not hold both blocks"
    assert dom_order["onlineBeforeDownloads"], f"downloads precede online: {dom_order}"
    out["dom_order"] = dom_order

    # 3. At scroll 0 the first card of the view sits below the nav.
    geometry = pg.evaluate(
        """() => {
        const nav = document.getElementById('sideNav').getBoundingClientRect();
        const first = document.querySelector('#v-resources .card').getBoundingClientRect();
        return {
            scrollY: window.scrollY,
            navBottom: nav.bottom,
            navHeight: nav.height,
            firstTop: first.top,
            offset: getComputedStyle(document.documentElement).getPropertyValue('--nav-offset').trim(),
        };
    }"""
    )
    assert geometry["scrollY"] == 0, f"not at scroll 0: {geometry}"
    assert geometry["firstTop"] >= geometry["navBottom"] - 1, (
        f"the nav covers the first card at scroll 0: {geometry}"
    )
    out["scroll0"] = geometry

    pg.locator("#v-resources").screenshot(path=os.path.join(OUT, "resources_order.png"))

    # 4. An anchor jump (goToPartFilter) leaves the destination card clear of
    #    the nav, not tucked underneath it.
    pg.evaluate("goToPartFilter(3,'ue')")
    pg.wait_for_timeout(1200)
    jumped = pg.evaluate(
        """() => {
        const nav = document.getElementById('sideNav').getBoundingClientRect();
        const panel = document.getElementById('practiceResources').getBoundingClientRect();
        const card = document.querySelector("#resourcesList .res-paper[data-res-type='ue'] .listen-test");
        const r = card.getBoundingClientRect();
        return {
            scrollY: window.scrollY,
            navBottom: nav.bottom,
            panelTop: panel.top,
            cardTop: r.top,
            cardBottom: r.bottom,
            title: card.querySelector('.lt-head').textContent.trim(),
        };
    }"""
    )
    assert jumped["scrollY"] > 0, f"goToPartFilter did not scroll: {jumped}"
    assert jumped["panelTop"] >= jumped["navBottom"] - 1, (
        f"the samples panel is under the nav: {jumped}"
    )
    assert jumped["cardTop"] >= jumped["navBottom"] - 1, (
        f"the destination card is under the nav: {jumped}"
    )
    out["after_go_to_part"] = jumped

    assert page_errors == [], f"page errors: {page_errors}"
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
