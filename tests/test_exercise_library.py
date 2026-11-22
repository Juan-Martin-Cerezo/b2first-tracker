"""Unified Practice Library acceptance: By part + Library tabs (local, online & Reference).

Verifies:
  1. PRACTICE_SOURCES.length >= 50, no duplicate URLs, all start with https://.
  2. No #v-resources or #v-exercises views and no Resources/Exercises entries in
     main nav or the More sheet; Practice is the single entry point with tabs
     "By part" (default) and "Library".
  3. The Library renders ALL local (MAT) + online (PRACTICE_SOURCES) + Reference
     entries (handbooks, guides, answer sheets, official platforms) and the
     visible counter matches the rendered row count.
  4. Default order ("Exam order"): papers in fixed order (rue, w, l, sp, ref)
     with Reference grouped at the end, and within each paper sorted by part
     ascending (then type, then mins).
  5. "Shortest first" sorts globally by mins ascending; "A–Z" sorts globally
     alphabetically by name.
  6. Filters: paper Listening leaves only Listening; paper Reference leaves only
     Reference; Part 2 leaves only items covering Part 2; "Free only" excludes
     freemium; search filters both exercises and Reference items; impossible
     query displays empty state and Reset restores all rows.
  7. Every row is a clickable <a> with non-empty href; local rows start with
     /files/ (from MAT) and online rows start with https:// with target=_blank
     and rel=noopener.
  8. 390x844 (light & dark) and 1280x900: single column, rows and controls
     >= 44px, zero horizontal overflow; EN and ES render symmetric controls
     with translated copy; zero inline on* handlers and zero page errors.
  9. Entry buttons from Today (Materials panels), Exam (sources card) and
     legacy showView('resources') open Practice on the Library tab.

Saves screenshots in tests/out/:
  library_390_light.png, library_390_dark.png, practice_tabs_1280_light.png.
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

EXPECTED_SKILLS = ["rue", "w", "l", "sp"]
EXPECTED_GROUP_ORDER = ["rue", "w", "l", "sp", "ref"]
INLINE_HANDLER_RE = re.compile(r'\bon[a-z]+\s*=\s*"')


def inspect_library(pg):
    return pg.evaluate(
        r"""() => {
            const view = document.getElementById('v-practice');
            const libPanel = document.getElementById('practiceTabLibrary');
            const partsPanel = document.getElementById('practiceTabParts');
            const list = document.getElementById('exLibList');
            if (!view || !libPanel || !list) return null;
            const groups = [...list.querySelectorAll(':scope > .exlib-group')].map(g => {
                const title = g.querySelector('.exlib-group-title');
                const cnt = g.querySelector('.exlib-group-count');
                const rows = [...g.querySelectorAll('a.exlib-row')].map(a => ({
                    skill: a.dataset.skill || '',
                    type: a.dataset.type || '',
                    origin: a.dataset.origin || '',
                    kind: a.dataset.kind || '',
                    mins: Number(a.dataset.mins || 0),
                    parts: (a.dataset.parts || '').split(',').filter(Boolean),
                    minPart: Number(a.dataset.minPart || 99),
                    name: a.dataset.name || '',
                }));
                return {
                    skill: g.dataset.skill || '',
                    title: title ? title.textContent.trim() : '',
                    countText: cnt ? cnt.textContent.trim() : '',
                    rows,
                };
            });
            const rows = [...list.querySelectorAll('a.exlib-row')].map(a => {
                const r = a.getBoundingClientRect();
                const openEl = a.querySelector('.exlib-row-open');
                return {
                    tag: a.tagName.toLowerCase(),
                    href: a.getAttribute('href') || '',
                    target: a.getAttribute('target') || '',
                    rel: a.getAttribute('rel') || '',
                    skill: a.dataset.skill || '',
                    type: a.dataset.type || '',
                    origin: a.dataset.origin || '',
                    kind: a.dataset.kind || '',
                    mins: Number(a.dataset.mins || 0),
                    parts: (a.dataset.parts || '').split(',').filter(Boolean),
                    minPart: Number(a.dataset.minPart || 99),
                    name: a.dataset.name || '',
                    openText: openEl ? openEl.textContent.trim() : '',
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    right: Math.round(r.right),
                };
            });
            const tabs = [...view.querySelectorAll('#practiceTabs button.practice-tab')].map(b => ({
                tab: b.dataset.practiceTab || '',
                text: b.textContent.trim(),
                selected: b.getAttribute('aria-selected'),
                h: Math.round(b.getBoundingClientRect().height),
            }));
            const paperChips = [...view.querySelectorAll('#exLibPaperFilter button.exlib-chip')].map(b => ({
                val: b.dataset.exlibPaper || '',
                text: b.textContent.trim(),
                pressed: b.getAttribute('aria-pressed'),
                h: Math.round(b.getBoundingClientRect().height),
            }));
            const partChips = [...view.querySelectorAll('#exLibPartFilter button.exlib-chip')].map(b => ({
                val: b.dataset.exlibPart || '',
                text: b.textContent.trim(),
                pressed: b.getAttribute('aria-pressed'),
                h: Math.round(b.getBoundingClientRect().height),
            }));
            const search = document.getElementById('exLibSearch');
            const sort = document.getElementById('exLibSort');
            const free = document.getElementById('exLibFreeOnly');
            const countEl = document.getElementById('exLibCount');
            const emptyEl = document.getElementById('exLibEmpty');
            const subEl = view.querySelector('#exercisesLibraryCard > .sub');
            const listEl = list.querySelector('.exlib-list');
            const lcs = listEl ? getComputedStyle(listEl) : null;
            return {
                active: view.classList.contains('active'),
                libVisible: !libPanel.hidden,
                partsVisible: partsPanel ? !partsPanel.hidden : false,
                tabs,
                subText: subEl ? subEl.textContent.trim() : '',
                groups,
                rows,
                paperChips,
                partChips,
                searchH: search ? Math.round(search.getBoundingClientRect().height) : 0,
                searchPh: search ? (search.getAttribute('placeholder') || '') : '',
                sortVal: sort ? sort.value : '',
                sortH: sort ? Math.round(sort.getBoundingClientRect().height) : 0,
                sortOptions: sort ? [...sort.options].map(o => ({v: o.value, t: o.textContent.trim()})) : [],
                freeChecked: free ? !!free.checked : false,
                countText: countEl ? countEl.textContent.trim() : '',
                emptyVisible: emptyEl ? getComputedStyle(emptyEl).display !== 'none' : false,
                listDisplay: lcs ? lcs.display : '',
                listFlexDir: lcs ? lcs.flexDirection : '',
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                html: view.outerHTML,
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
    pg.wait_for_timeout(300)

    # Ensure local material index is loaded from /libros.json
    pg.evaluate("loadMaterial()")
    pg.wait_for_function("Object.keys(MAT).length > 0", timeout=8000)
    pg.wait_for_timeout(200)

    # 2. Old #v-resources / #v-exercises and menu entries are gone
    removed = pg.evaluate(
        """() => ({
            vResources: !!document.getElementById('v-resources'),
            vExercises: !!document.getElementById('v-exercises'),
            vLibros: !!document.getElementById('v-libros'),
            navResources: !!document.querySelector("nav button[data-view='resources']"),
            navExercises: !!document.querySelector("nav button[data-view='exercises']"),
            moreResources: !!document.querySelector("#moreSheet [data-view='resources']"),
            moreExercises: !!document.querySelector("#moreSheet [data-view='exercises']"),
            navLabels: [...document.querySelectorAll('#sideNav .nav-label')].map(e => e.textContent.trim()),
        })"""
    )
    assert not removed["vResources"], "#v-resources still exists in DOM"
    assert not removed["vExercises"], "#v-exercises still exists in DOM"
    assert not removed["vLibros"], "#v-libros still exists in DOM"
    assert not removed["navResources"], "Resources nav button still exists"
    assert not removed["navExercises"], "Exercises nav button still exists"
    assert not removed["moreResources"], "Resources item still exists in More sheet"
    assert not removed["moreExercises"], "Exercises item still exists in More sheet"
    assert "Resources" not in removed["navLabels"], f"Resources still in nav: {removed['navLabels']}"
    assert "Exercises" not in removed["navLabels"], f"Exercises still in nav: {removed['navLabels']}"

    # 1. PRACTICE_SOURCES >= 50, no duplicate URLs, all https://
    sources = pg.evaluate(
        """() => (typeof PRACTICE_SOURCES !== 'undefined' ? PRACTICE_SOURCES : []).map(s => ({
            n: s.n, url: s.url, skill: s.skill, kind: s.kind, what: s.what, mins: s.mins, part: s.part || []
        }))"""
    )
    assert len(sources) >= 50, f"PRACTICE_SOURCES has only {len(sources)} entries (need >= 50)"
    urls = [s["url"] for s in sources]
    assert len(urls) == len(set(urls)), "Duplicate URLs found in PRACTICE_SOURCES"
    for s in sources:
        assert s["url"].startswith("https://"), f"Non-https URL: {s['url']}"
        assert s["skill"] in EXPECTED_SKILLS, f"Invalid skill: {s}"
        assert s["kind"] in ("free", "freemium"), f"Invalid kind: {s}"
        assert isinstance(s["mins"], int) and s["mins"] > 0, f"Invalid mins: {s}"
        assert isinstance(s["what"], str) and len(s["what"]) > 20, f"Short what: {s}"
    by_skill = {k: sum(1 for s in sources if s["skill"] == k) for k in EXPECTED_SKILLS}
    assert all(v >= 8 for v in by_skill.values()), f"Unbalanced PRACTICE_SOURCES: {by_skill}"

    # 2b. Practice default tab is "By part"
    pg.evaluate("showView('practice')")
    pg.wait_for_timeout(200)
    default_st = inspect_library(pg)
    assert default_st["active"], "#v-practice not active"
    assert default_st["partsVisible"] and not default_st["libVisible"], (
        f"Practice default tab is not By part: parts={default_st['partsVisible']}, lib={default_st['libVisible']}"
    )
    assert [t["text"] for t in default_st["tabs"]] == ["By part", "Library"], (
        f"Unexpected Practice tabs: {default_st['tabs']}"
    )
    for tab in default_st["tabs"]:
        assert tab["h"] >= 44, f"Practice tab height {tab['h']} < 44px: {tab}"

    # 9a. Entry from Today Materials panel opens Practice -> Library tab
    pg.evaluate("showView('hoy')")
    pg.wait_for_timeout(200)
    opened_today = pg.evaluate(
        """() => {
            const ids = ['wtfSectionRue', 'wtfSectionW', 'wtfSectionL', 'wtfSectionSp'];
            for (const id of ids) {
                const sec = document.getElementById(id);
                if (!sec) continue;
                const btn = sec.querySelector('.wtf-browse-btn');
                if (!btn) continue;
                setWtfOpen(sec.dataset.wtfSkill, true);
                btn.click();
                return id;
            }
            return null;
        }"""
    )
    assert opened_today is not None, "No Today Materials library button found"
    pg.wait_for_timeout(200)
    st_today = inspect_library(pg)
    assert st_today["active"] and st_today["libVisible"], (
        f"Today button in {opened_today} did not open Practice -> Library"
    )
    today_btns = pg.evaluate(
        """() => ['wtfPanelRue', 'wtfPanelW', 'wtfPanelL', 'wtfPanelSp'].map(id =>
            !!document.querySelector('#' + id + ' .wtf-browse-btn')
        )"""
    )
    assert all(today_btns), f"Missing library button in Today panels: {today_btns}"

    # 9b. Legacy showView('resources') redirects to Practice -> Library tab
    pg.evaluate("showView('hoy')")
    pg.wait_for_timeout(120)
    pg.evaluate("showView('resources')")
    pg.wait_for_timeout(200)
    st_redir = inspect_library(pg)
    assert st_redir["active"] and st_redir["libVisible"], (
        "showView('resources') did not redirect to Practice -> Library"
    )

    # 9c. Entry from Exam sources card opens Practice -> Library tab
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(200)
    pg.click("#examBrowseExercisesBtn")
    pg.wait_for_timeout(200)
    st_exam = inspect_library(pg)
    assert st_exam["active"] and st_exam["libVisible"], (
        "Exam '#examBrowseExercisesBtn' did not open Practice -> Library"
    )

    # 3. All local + online + Reference entries listed, counter matches rendered rows
    expected_catalog = pg.evaluate("buildExerciseLibrary()")
    expected_local = [x for x in expected_catalog if x["origin"] == "local" and x["skill"] != "ref"]
    expected_online = [x for x in expected_catalog if x["origin"] == "online" and x["skill"] != "ref"]
    expected_ref = [x for x in expected_catalog if x["skill"] == "ref"]
    assert len(expected_local) > 0, "No local exercises built from MAT"
    assert len(expected_online) == len(sources), (
        f"Online count {len(expected_online)} != PRACTICE_SOURCES {len(sources)}"
    )
    assert len(expected_ref) >= 5, f"Expected Reference entries in library, got {len(expected_ref)}"

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(120)
    state = inspect_library(pg)
    assert state is not None and state["active"] and state["libVisible"], "Practice Library not active"
    assert state["subText"] == "Every paper, key, audio and verified source in one ordered list.", (
        f"Unexpected Library subtitle: {state['subText']!r}"
    )
    assert not INLINE_HANDLER_RE.search(state["html"]), "Inline on* handler found in #v-practice"

    assert len(state["rows"]) == len(expected_catalog), (
        f"Rendered {len(state['rows'])} rows, expected {len(expected_catalog)}"
    )
    assert state["countText"] == f"{len(state['rows'])} items", (
        f"Counter mismatch: {state['countText']!r} vs {len(state['rows'])}"
    )

    # 4. Default order: papers in fixed order ending with Reference, within each paper minPart ascending
    assert [g["skill"] for g in state["groups"]] == EXPECTED_GROUP_ORDER, (
        f"Paper groups out of order: {[g['skill'] for g in state['groups']]}"
    )
    assert state["groups"][-1]["title"] == "Reference", (
        f"Last group title is not Reference: {state['groups'][-1]['title']!r}"
    )
    for g in state["groups"]:
        min_parts = [r["minPart"] for r in g["rows"]]
        assert min_parts == sorted(min_parts), (
            f"Group {g['skill']} parts not ascending: {min_parts[:20]}"
        )

    # 7. Every row has non-empty href; local starts with /files/, online starts with https://
    for r in state["rows"]:
        assert r["tag"] == "a", f"Row is not <a>: {r}"
        assert r["href"], f"Empty href on row: {r}"
        if r["origin"] == "local":
            assert r["href"].startswith("/files/"), f"Local row href does not start with /files/: {r['href']}"
        else:
            assert r["href"].startswith("https://"), f"Online row href not https://: {r['href']}"
            assert r["target"] == "_blank", f"Online row missing target=_blank: {r}"
            assert "noopener" in r["rel"], f"Online row missing noopener: {r}"
        assert r["h"] >= 44, f"Row height {r['h']} < 44px: {r['name']}"
        assert r["right"] <= state["clientWidth"] + 1, f"Row overflows right edge: {r}"

    # 8a. Mobile 390x844 light & dark checks + screenshots
    assert state["listDisplay"] == "flex" and state["listFlexDir"] == "column", (
        f"Mobile list not single column: {state['listDisplay']}/{state['listFlexDir']}"
    )
    assert state["scrollWidth"] <= state["clientWidth"] + 1, (
        f"390 light horizontal overflow: {state['scrollWidth']} > {state['clientWidth']}"
    )
    assert state["searchH"] >= 44, f"Search input height {state['searchH']} < 44px"
    assert state["sortH"] >= 44, f"Sort select height {state['sortH']} < 44px"
    for ch in state["paperChips"] + state["partChips"]:
        assert ch["h"] >= 44, f"Chip {ch['text']!r} height {ch['h']} < 44px"

    pg.evaluate("window.scrollTo(0, 0)")
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "library_390_light.png"))

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(120)
    dark_state = inspect_library(pg)
    assert dark_state["scrollWidth"] <= dark_state["clientWidth"] + 1, (
        f"390 dark horizontal overflow: {dark_state['scrollWidth']} > {dark_state['clientWidth']}"
    )
    pg.screenshot(path=os.path.join(OUT, "library_390_dark.png"))
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(100)

    # 5. Sorting: Shortest first (mins ascending) and A-Z (alphabetical)
    pg.select_option("#exLibSort", "shortest")
    pg.wait_for_timeout(120)
    st_short = inspect_library(pg)
    assert len(st_short["rows"]) == len(expected_catalog)
    mins_seq = [r["mins"] for r in st_short["rows"]]
    assert mins_seq == sorted(mins_seq), f"Shortest first not sorted by mins: {mins_seq[:20]}"

    pg.select_option("#exLibSort", "az")
    pg.wait_for_timeout(120)
    st_az = inspect_library(pg)
    assert len(st_az["rows"]) == len(expected_catalog)
    az_ok = pg.evaluate(
        """() => {
            const names = [...document.querySelectorAll('#exLibList a.exlib-row')].map(a => a.dataset.name || '');
            for (let i = 1; i < names.length; i++) {
                if (names[i - 1].localeCompare(names[i], 'en', {sensitivity: 'base'}) > 0) {
                    return {ok: false, i, prev: names[i - 1], curr: names[i]};
                }
            }
            return {ok: true, n: names.length};
        }"""
    )
    assert az_ok["ok"], f"A-Z sort out of order: {az_ok}"

    # Restore Exam order
    pg.select_option("#exLibSort", "exam")
    pg.wait_for_timeout(100)

    # 6. Filters: Listening, Reference, Part 2, Free only, Search, Empty state
    pg.click("#exLibPaperFilter [data-exlib-paper='l']")
    pg.wait_for_timeout(100)
    st_l = inspect_library(pg)
    assert st_l["rows"], "Listening filter returned 0 rows"
    assert all(r["skill"] == "l" for r in st_l["rows"]), "Listening filter leaked other papers"
    assert [g["skill"] for g in st_l["groups"]] == ["l"]
    assert st_l["countText"] == f"{len(st_l['rows'])} items"

    pg.click("#exLibPaperFilter [data-exlib-paper='ref']")
    pg.wait_for_timeout(100)
    st_ref = inspect_library(pg)
    assert len(st_ref["rows"]) == len(expected_ref), (
        f"Reference filter returned {len(st_ref['rows'])}, expected {len(expected_ref)}"
    )
    assert all(r["skill"] == "ref" for r in st_ref["rows"]), "Reference filter leaked other papers"
    assert [g["skill"] for g in st_ref["groups"]] == ["ref"]

    pg.click("#exLibPaperFilter [data-exlib-paper='all']")
    pg.click("#exLibPartFilter [data-exlib-part='2']")
    pg.wait_for_timeout(100)
    st_p2 = inspect_library(pg)
    assert st_p2["rows"], "Part 2 filter returned 0 rows"
    assert all("2" in r["parts"] for r in st_p2["rows"]), (
        f"Part 2 filter leaked non-part-2 rows: {[r['parts'] for r in st_p2['rows'] if '2' not in r['parts']][:5]}"
    )

    pg.click("#exLibPartFilter [data-exlib-part='all']")
    pg.check("#exLibFreeOnly")
    pg.wait_for_timeout(100)
    st_free = inspect_library(pg)
    expected_free_n = sum(1 for x in expected_catalog if x["kind"] == "free")
    assert len(st_free["rows"]) == expected_free_n, (
        f"Free only count {len(st_free['rows'])} != expected {expected_free_n}"
    )
    assert all(r["kind"] == "free" for r in st_free["rows"]), "Free only leaked freemium rows"
    assert len(st_free["rows"]) < len(expected_catalog), "Expected at least one freemium source to be excluded"
    pg.uncheck("#exLibFreeOnly")
    pg.wait_for_timeout(100)

    pg.fill("#exLibSearch", "Academic Phrasebank")
    pg.wait_for_timeout(100)
    st_q = inspect_library(pg)
    assert len(st_q["rows"]) == 1, f"Search 'Academic Phrasebank' expected 1 row, got {len(st_q['rows'])}"
    assert "Academic Phrasebank" in st_q["rows"][0]["name"]
    assert st_q["countText"] == "1 item"

    # Search finds Reference items too
    pg.fill("#exLibSearch", "Cambridge One")
    pg.wait_for_timeout(100)
    st_ref_q = inspect_library(pg)
    assert len(st_ref_q["rows"]) == 1 and st_ref_q["rows"][0]["skill"] == "ref", (
        f"Search 'Cambridge One' did not find Reference row: {st_ref_q['rows']}"
    )

    # Empty state & Reset
    pg.fill("#exLibSearch", "zzz-no-such-exercise-999")
    pg.wait_for_timeout(100)
    st_empty = inspect_library(pg)
    assert len(st_empty["rows"]) == 0
    assert st_empty["emptyVisible"], "Empty state not shown when 0 results"
    assert st_empty["countText"] == "0 items"
    pg.click("#exLibEmpty button[data-action='resetExLibFilters']")
    pg.wait_for_timeout(100)
    assert len(inspect_library(pg)["rows"]) == len(expected_catalog), "Reset filters did not restore all rows"

    # 8b. Spanish i18n: same controls, translated labels, no overflow
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(250)
    es_state = inspect_library(pg)
    assert len(es_state["rows"]) == len(expected_catalog)
    assert [t["text"] for t in es_state["tabs"]] == ["Por parte", "Biblioteca"], (
        f"ES Practice tabs not translated: {es_state['tabs']}"
    )
    assert [c["val"] for c in es_state["paperChips"]] == [c["val"] for c in state["paperChips"]]
    assert [c["val"] for c in es_state["partChips"]] == [c["val"] for c in state["partChips"]]
    assert [o["v"] for o in es_state["sortOptions"]] == [o["v"] for o in state["sortOptions"]]
    assert "elementos" in es_state["countText"], f"ES counter not translated: {es_state['countText']!r}"
    assert "Buscar" in es_state["searchPh"], f"ES placeholder not translated: {es_state['searchPh']!r}"
    assert es_state["paperChips"][0]["text"] == "Todas las pruebas"
    assert es_state["paperChips"][-1]["text"] == "Referencia"
    assert es_state["partChips"][1]["text"] == "Parte 1"
    assert es_state["sortOptions"][0]["t"] == "Orden del examen"
    assert es_state["groups"][-1]["title"] == "Referencia"
    assert es_state["scrollWidth"] <= es_state["clientWidth"] + 1, (
        f"390 ES horizontal overflow: {es_state['scrollWidth']} > {es_state['clientWidth']}"
    )

    # Restore EN and capture 1280x900 desktop screenshot of Practice tabs + Library
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.wait_for_timeout(200)
    desktop = inspect_library(pg)
    assert desktop["scrollWidth"] <= desktop["clientWidth"] + 1, (
        f"1280 horizontal overflow: {desktop['scrollWidth']} > {desktop['clientWidth']}"
    )
    assert len(desktop["rows"]) == len(expected_catalog)
    pg.evaluate("window.scrollTo(0, 0)")
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "practice_tabs_1280_light.png"))

    assert page_errors == [], f"Page errors: {page_errors}"

    out = {
        "practice_sources": len(sources),
        "practice_sources_by_skill": by_skill,
        "library_total": len(expected_catalog),
        "library_local": len(expected_local),
        "library_online": len(expected_online),
        "library_reference": len(expected_ref),
        "filter_listening": len(st_l["rows"]),
        "filter_reference": len(st_ref["rows"]),
        "filter_part2": len(st_p2["rows"]),
        "filter_free": len(st_free["rows"]),
        "en_count": state["countText"],
        "es_count": es_state["countText"],
        "screenshots": [
            "library_390_light.png",
            "library_390_dark.png",
            "practice_tabs_1280_light.png",
        ],
        "page_errors": page_errors,
    }
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
