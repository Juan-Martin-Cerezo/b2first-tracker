"""Exam sources blocks: all PRACTICE_SOURCES grouped by paper in Today's block language.

Verifies the Exam tab's `.u4-exam-sources` card:
  1. Renders 4 groups with headings in order (Reading & Use of English, Writing,
     Listening, Speaking) and in total as many blocks as PRACTICE_SOURCES.
  2. Every block is a full clickable `<a href>` with target="_blank" and noopener,
     matching the source `url` 1:1, displaying `what`, a concrete usage hint, and
     a part tag whenever the source defines `part`.
  3. Live search filters: typing "listening" leaves only Listening sources;
     clearing (via Clear button and via Escape) restores all sources.
  4. Quick filter chips work: Free leaves only kind === 'free'; each paper chip
     filters to that paper; All restores the full catalogue.
  5. 390x844 (light & dark): single column, no horizontal overflow, all blocks
     and controls >= 44px tall; EN and ES render the same blocks with translated
     UI copy (headings, search, chips, hints, counters) and untranslated source names.
  6. Zero inline `on*` handlers and zero pageerrors.

Saves screenshots in tests/out/:
  exam_sources_390_light.png, exam_sources_390_dark.png, exam_sources_1280_light.png.
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

EXPECTED_ORDER = ["rue", "w", "l", "sp"]
INLINE_HANDLER_RE = re.compile(r'\bon[a-z]+\s*=\s*"')


def inspect_exam_sources(pg):
    return pg.evaluate(
        r"""() => {
            const card = document.querySelector('.u4-exam-sources');
            const root = document.getElementById('examSources');
            if (!card || !root) return null;
            const groups = [...root.querySelectorAll(':scope > .es-group')].map(g => {
                const list = g.querySelector('.wtf-list');
                const lcs = list ? getComputedStyle(list) : null;
                const title = g.querySelector('.es-group-title');
                const sub = g.querySelector('.es-group-sub');
                const cnt = g.querySelector('.es-group-count');
                return {
                    skill: g.dataset.skill || '',
                    title: title ? title.textContent.trim() : '',
                    sub: sub ? sub.textContent.trim() : '',
                    countText: cnt ? cnt.textContent.trim() : '',
                    listDisplay: lcs ? lcs.display : '',
                    listFlexDir: lcs ? lcs.flexDirection : '',
                    blockCount: g.querySelectorAll('a.wtf-block.wtf-source').length,
                };
            });
            const blocks = [...root.querySelectorAll('a.wtf-block.wtf-source')].map(a => {
                const r = a.getBoundingClientRect();
                const name = a.querySelector('.wtf-source-name');
                const what = a.querySelector('.wtf-source-what');
                const hint = a.querySelector('.wtf-hint');
                const part = a.querySelector('.wtf-part-tag');
                return {
                    tag: a.tagName.toLowerCase(),
                    skill: a.dataset.skill || '',
                    kind: a.dataset.kind || '',
                    href: a.getAttribute('href') || '',
                    target: a.getAttribute('target') || '',
                    rel: a.getAttribute('rel') || '',
                    name: name ? name.textContent.replace(/\s*↗\s*$/, '').trim() : '',
                    what: what ? what.textContent.trim() : '',
                    hint: hint ? hint.textContent.trim() : '',
                    partTag: part ? part.textContent.trim() : '',
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    right: Math.round(r.right),
                    top: Math.round(r.top),
                    bottom: Math.round(r.bottom),
                };
            });
            const chips = [...card.querySelectorAll('#examSourcesFilter button.es-chip')].map(b => {
                const r = b.getBoundingClientRect();
                return {
                    filter: b.dataset.esFilter || '',
                    text: b.textContent.trim(),
                    pressed: b.getAttribute('aria-pressed'),
                    h: Math.round(r.height),
                    w: Math.round(r.width),
                };
            });
            const inp = document.getElementById('examSourcesSearch');
            const ir = inp ? inp.getBoundingClientRect() : null;
            const countEl = document.getElementById('examSourcesCount');
            return {
                groups,
                blocks,
                chips,
                searchHeight: ir ? Math.round(ir.height) : 0,
                searchPlaceholder: inp ? inp.getAttribute('placeholder') || '' : '',
                countText: countEl ? countEl.textContent.trim() : '',
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                cardHtml: card.outerHTML,
            };
        }"""
    )


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(250)

    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(250)

    sources = pg.evaluate(
        """() => (typeof PRACTICE_SOURCES !== 'undefined' ? PRACTICE_SOURCES : []).map(s => ({
            n: s.n, url: s.url, skill: s.skill, kind: s.kind, what: s.what, mins: s.mins, part: s.part || []
        }))"""
    )
    assert len(sources) >= 26, f"Unexpectedly small PRACTICE_SOURCES: {len(sources)}"

    # 1 & 2. 4 groups in exam order, total blocks == PRACTICE_SOURCES, full <a> cards
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(120)
    en_light = inspect_exam_sources(pg)
    assert en_light is not None, ".u4-exam-sources or #examSources missing"
    assert not INLINE_HANDLER_RE.search(en_light["cardHtml"]), "Inline on* handler found in .u4-exam-sources"

    assert [g["skill"] for g in en_light["groups"]] == EXPECTED_ORDER, (
        f"Groups out of order: {[g['skill'] for g in en_light['groups']]}"
    )
    assert [g["title"] for g in en_light["groups"]] == [
        "Reading & Use of English",
        "Writing",
        "Listening",
        "Speaking",
    ], f"Unexpected EN group titles: {[g['title'] for g in en_light['groups']]}"
    for g in en_light["groups"]:
        assert g["sub"], f"Group {g['skill']} missing subtitle"
        assert g["countText"], f"Group {g['skill']} missing count"
        assert g["listDisplay"] == "flex" and g["listFlexDir"] == "column", (
            f"Mobile 390 group {g['skill']} not vertical column: {g['listDisplay']}/{g['listFlexDir']}"
        )

    assert len(en_light["blocks"]) == len(sources), (
        f"Rendered {len(en_light['blocks'])} blocks, expected {len(sources)}"
    )
    assert f"{len(sources)} of {len(sources)}" in en_light["countText"], (
        f"Unexpected EN counter: {en_light['countText']!r}"
    )

    by_url = {s["url"]: s for s in sources}
    rendered_urls = [b["href"] for b in en_light["blocks"]]
    assert rendered_urls == [s["url"] for s in sources], "Rendered block hrefs do not match PRACTICE_SOURCES"

    for blk in en_light["blocks"]:
        src = by_url[blk["href"]]
        assert blk["tag"] == "a", f"Block is not <a>: {blk}"
        assert blk["target"] == "_blank", f"Block missing target=_blank: {blk}"
        assert "noopener" in blk["rel"], f"Block missing rel=noopener: {blk}"
        assert blk["name"] == src["n"], f"Block name mismatch: {blk['name']!r} vs {src['n']!r}"
        assert blk["what"] == src["what"], f"Block what mismatch: {blk['what']!r}"
        assert f"{src['mins']} min" in blk["hint"], f"Block hint missing mins: {blk['hint']!r}"
        assert blk["h"] >= 44, f"Block height {blk['h']} < 44px: {blk['name']}"
        assert blk["w"] >= 200, f"Block not full-width card on 390px: {blk['w']}px"
        assert blk["right"] <= en_light["clientWidth"] + 1, f"Block overflows right edge: {blk}"
        if src["part"]:
            assert blk["partTag"].startswith("Part"), f"Missing part tag for {src['n']}: {blk['partTag']!r}"
        else:
            assert blk["partTag"] == "", f"Unexpected part tag for {src['n']}: {blk['partTag']!r}"

    # Verify controls >= 44px and zero horizontal overflow on 390x844 light
    assert en_light["scrollWidth"] <= en_light["clientWidth"] + 1, (
        f"390 light horizontal overflow: {en_light['scrollWidth']} > {en_light['clientWidth']}"
    )
    assert en_light["searchHeight"] >= 44, f"Search input height {en_light['searchHeight']} < 44px"
    assert [c["filter"] for c in en_light["chips"]] == ["all", "free", "rue", "w", "l", "sp"]
    for ch in en_light["chips"]:
        assert ch["h"] >= 44, f"Chip {ch['text']!r} height {ch['h']} < 44px"

    # Capture 390x844 light & dark screenshots anchored to the top of the Exam Sources card
    pg.evaluate("""() => {
        const card = document.querySelector('.u4-exam-sources');
        if (card) window.scrollTo(0, Math.max(0, card.getBoundingClientRect().top + window.scrollY - 100));
    }""")
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "exam_sources_390_light.png"))

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    pg.wait_for_timeout(120)
    en_dark = inspect_exam_sources(pg)
    assert en_dark["scrollWidth"] <= en_dark["clientWidth"] + 1, (
        f"390 dark horizontal overflow: {en_dark['scrollWidth']} > {en_dark['clientWidth']}"
    )
    assert len(en_dark["blocks"]) == len(sources)
    pg.screenshot(path=os.path.join(OUT, "exam_sources_390_dark.png"))
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(100)

    # 3. Live search: "listening" leaves only Listening sources; clearing restores all
    pg.fill("#examSourcesSearch", "listening")
    pg.wait_for_timeout(120)
    search_l = inspect_exam_sources(pg)
    expected_l_count = sum(1 for s in sources if s["skill"] == "l")
    assert len(search_l["blocks"]) == expected_l_count, (
        f"Search 'listening' returned {len(search_l['blocks'])}, expected {expected_l_count}"
    )
    assert all(b["skill"] == "l" for b in search_l["blocks"]), (
        f"Search 'listening' leaked non-listening sources: {[b['skill'] for b in search_l['blocks']]}"
    )
    assert [g["skill"] for g in search_l["groups"]] == ["l"]

    # Clear via Clear button
    pg.click("#examSourcesClear")
    pg.wait_for_timeout(120)
    restored = inspect_exam_sources(pg)
    assert len(restored["blocks"]) == len(sources), (
        f"Clearing search did not restore all blocks: {len(restored['blocks'])} vs {len(sources)}"
    )

    # Clear via Escape key (keyboard accessibility)
    pg.fill("#examSourcesSearch", "flo-joe")
    pg.wait_for_timeout(100)
    assert len(inspect_exam_sources(pg)["blocks"]) == 1, "Search 'flo-joe' should match 1 source"
    pg.locator("#examSourcesSearch").press("Escape")
    pg.wait_for_timeout(100)
    assert len(inspect_exam_sources(pg)["blocks"]) == len(sources), "Escape did not restore all blocks"

    # 4. Filter chips: Free leaves only kind === 'free'; each paper chip filters to that skill
    pg.click("#examSourcesFilter [data-es-filter='free']")
    pg.wait_for_timeout(120)
    free_state = inspect_exam_sources(pg)
    expected_free = sum(1 for s in sources if s["kind"] == "free")
    assert len(free_state["blocks"]) == expected_free, (
        f"Free chip returned {len(free_state['blocks'])}, expected {expected_free}"
    )
    assert all(b["kind"] == "free" for b in free_state["blocks"]), (
        f"Free chip leaked non-free sources: {[b['kind'] for b in free_state['blocks']]}"
    )

    chip_counts = {}
    for skill in EXPECTED_ORDER:
        pg.click(f"#examSourcesFilter [data-es-filter='{skill}']")
        pg.wait_for_timeout(100)
        st = inspect_exam_sources(pg)
        exp_n = sum(1 for s in sources if s["skill"] == skill)
        assert len(st["blocks"]) == exp_n, f"Chip {skill} returned {len(st['blocks'])}, expected {exp_n}"
        assert all(b["skill"] == skill for b in st["blocks"]), f"Chip {skill} leaked other skills"
        chip_counts[skill] = len(st["blocks"])

    pg.click("#examSourcesFilter [data-es-filter='all']")
    pg.wait_for_timeout(100)
    assert len(inspect_exam_sources(pg)["blocks"]) == len(sources), "All chip did not restore full list"

    # 5. Spanish i18n: same blocks & untranslated source names, translated UI copy
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(250)
    es_state = inspect_exam_sources(pg)
    assert len(es_state["blocks"]) == len(sources), (
        f"ES rendered {len(es_state['blocks'])} blocks, expected {len(sources)}"
    )
    assert [b["href"] for b in es_state["blocks"]] == rendered_urls, "ES block hrefs differ from EN"
    assert [b["name"] for b in es_state["blocks"]] == [b["name"] for b in en_light["blocks"]], (
        "Source names should not be translated in ES"
    )
    assert es_state["groups"][0]["title"] == "Reading y Use of English", (
        f"ES group 0 title not translated: {es_state['groups'][0]['title']!r}"
    )
    assert "Mostrando" in es_state["countText"], f"ES counter not translated: {es_state['countText']!r}"
    assert "Buscar" in es_state["searchPlaceholder"], f"ES search placeholder not translated: {es_state['searchPlaceholder']!r}"
    assert es_state["chips"][0]["text"] == "Todas" and es_state["chips"][1]["text"] == "Gratis", (
        f"ES chips not translated: {[c['text'] for c in es_state['chips']]}"
    )
    assert any("Partes" in b["partTag"] for b in es_state["blocks"]), "ES part tags not translated"
    assert any("gratis" in b["hint"] for b in es_state["blocks"]), "ES hints not translated"
    assert es_state["scrollWidth"] <= es_state["clientWidth"] + 1, (
        f"390 ES horizontal overflow: {es_state['scrollWidth']} > {es_state['clientWidth']}"
    )

    # Restore EN and capture 1280x900 desktop screenshot
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.wait_for_timeout(200)
    desktop = inspect_exam_sources(pg)
    assert desktop["scrollWidth"] <= desktop["clientWidth"] + 1, (
        f"1280 horizontal overflow: {desktop['scrollWidth']} > {desktop['clientWidth']}"
    )
    assert len(desktop["blocks"]) == len(sources)
    pg.evaluate("""() => {
        const card = document.querySelector('.u4-exam-sources');
        if (card) window.scrollTo(0, Math.max(0, card.getBoundingClientRect().top + window.scrollY - 72));
    }""")
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "exam_sources_1280_light.png"))

    # 7. Existing Exam controls & "Open the full source library" button still work
    assert pg.locator("#examSelectGrid .exam-card").count() == 4, "4 real mock cards missing"
    assert pg.locator("#exPaper").is_visible(), "Manual paper selector #exPaper missing"
    pg.click(".u4-source-all button")
    pg.wait_for_timeout(200)
    assert pg.evaluate("document.getElementById('v-resources').classList.contains('active')"), (
        "Open the full source library did not open Resources"
    )

    # 6. Zero page errors
    assert page_errors == [], f"Page errors: {page_errors}"

    out = {
        "sources_total": len(sources),
        "groups": [g["skill"] for g in en_light["groups"]],
        "search_listening": len(search_l["blocks"]),
        "free_only": len(free_state["blocks"]),
        "by_skill_chips": chip_counts,
        "en_count": en_light["countText"],
        "es_count": es_state["countText"],
        "screenshots": [
            "exam_sources_390_light.png",
            "exam_sources_390_dark.png",
            "exam_sources_1280_light.png",
        ],
        "page_errors": page_errors,
    }
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
