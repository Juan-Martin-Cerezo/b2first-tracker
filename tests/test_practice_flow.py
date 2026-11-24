"""Phase practice-first & practice-flow acceptance: Practice opens on Library hub.

Verifies:
  1. Clicking nav Practice opens #v-practice with #practiceLibraryCard visible in the first
     viewport (top < 844), counter > 0 (187 contents in EN, exam group order), and filters work.
  2. #practiceLibraryCard precedes #practiceParts in DOM order.
  3. #practiceParts lives inside a <details> closed by default; opening it exposes all 17 Start buttons.
  4. The 2 intent cards exist: "Full mock" opens #v-exam with pre-flight visible;
     "Practise by part" opens the parts <details>.
  5. Start on Reading Part 2 opens the session on Contents with local + online resources.
  6. Today's cycle counter opens the Practice Library filtered to its skill; Full Mock pre-flight works.
  7. 390x844 & 1280x800 light/dark: zero horizontal overflow, search visible without scroll,
     FAB does not overlap search or intent cards, symmetric EN/ES copy, zero duplicate IDs,
     zero inline on* handlers, zero console/page errors.

Saves screenshots in tests/out/:
  practice_hub_390_light.png, practice_hub_390_dark.png, practice_hub_1280_light.png,
  full_mock_preflight_390_light.png.
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)

import plans  # noqa: E402
from helpers import isolated_server, login_owner  # noqa: E402

URL = isolated_server() + "/"
OUT = os.path.join(TESTS, "out")
os.makedirs(OUT, exist_ok=True)
INLINE_HANDLER_RE = re.compile(r'\bon[a-z]+\s*=\s*"')


def seed_mat_if_empty(pg):
    pg.evaluate("loadMaterial()")
    pg.wait_for_timeout(400)
    if pg.evaluate("Object.keys(MAT).length") == 0:
        pg.evaluate(
            """() => {
                const keys = [
                    'rueS1','rueS2','rueFS1','rueFS2','keyS1','keyS2','keyFS1','keyFS2',
                    'lpR1','lpR2','lpR3','fR2',
                    'wS1','wS2','wFS1','wFS2','lpW1','lpW2',
                    'lS1','lS2','lFS1','lFS2','lkS1','lkS2','lkFS1','lkFS2','auS1','auFS2','tsS1','auS2p1','auS2p2','lpL2',
                    'spS1','spS2','spFS1','spFS2','exC0','exC1','lpSp2','hb'
                ];
                keys.forEach(k => { MAT[k] = '/files/test-' + k + '.pdf'; });
                renderEx(); renderParts(); renderGuides(); renderExercisesLibrary(); renderFullMockPreflight();
            }"""
        )


out = {}

# Verify plans.py limits raised to 3 mocks / 45 min
assert plans.DAY_SPEAKING_MOCKS == 3, plans.DAY_SPEAKING_MOCKS
assert plans.DAY_SPEAKING_MINUTES == 45, plans.DAY_SPEAKING_MINUTES
assert plans.LIMITS["service"]["speaking"]["mocks"] == 3
assert plans.LIMITS["service"]["speaking"]["minutes"] == 45
assert plans.LIMITS["owner"]["speaking"]["mocks"] == 1_000_000

with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    console_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.on(
        "console",
        lambda m: console_errors.append(m.text)
        if m.type == "error" and "Failed to load resource" not in m.text
        else None,
    )
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(300)
    seed_mat_if_empty(pg)

    # 6a. Zero duplicate IDs across entire DOM
    dup_ids = pg.evaluate(
        """() => {
            const seen = new Map();
            const dups = [];
            document.querySelectorAll('[id]').forEach(el => {
                const id = el.id;
                if (!id) return;
                seen.set(id, (seen.get(id) || 0) + 1);
            });
            seen.forEach((n, id) => { if (n > 1) dups.push({id, n}); });
            return dups;
        }"""
    )
    assert dup_ids == [], f"Duplicate DOM ids found: {dup_ids}"
    out["duplicate_ids"] = 0

    # --- 1. Nav Practice opens Library first, in first viewport, parts collapsed ---
    pg.click("nav button[data-view='practice']")
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light'); window.scrollTo(0, 0)")
    pg.wait_for_timeout(250)

    prac = pg.evaluate(
        """() => {
            const view = document.getElementById('v-practice');
            const libCard = document.getElementById('practiceLibraryCard');
            const parts = document.getElementById('practiceParts');
            const details = parts ? parts.closest('details') : null;
            const countEl = document.getElementById('pracLibCount');
            const searchEl = document.getElementById('pracLibSearch');
            const fab = document.getElementById('qlFab');
            const intentMock = document.getElementById('practiceIntentFullMock');
            const intentPart = document.getElementById('practiceIntentByPart');
            const rows = [...document.querySelectorAll('#pracLibList a.exlib-row')];
            const groupSkills = [...document.querySelectorAll('#pracLibList .exlib-group')].map(g => g.dataset.skill);
            const summaries = [...document.querySelectorAll('#partsList .step .step-res-summary')]
                .map(e => e.textContent.trim());
            const box = el => {
                if (!el) return null;
                const b = el.getBoundingClientRect();
                return {top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right), w: Math.round(b.width), h: Math.round(b.height)};
            };
            const libBeforeParts = !!(libCard && parts && (libCard.compareDocumentPosition(parts) & Node.DOCUMENT_POSITION_FOLLOWING));
            return {
                active: view.classList.contains('active'),
                libVisible: !!libCard && getComputedStyle(libCard).display !== 'none' && !libCard.hidden,
                libBox: box(libCard),
                searchBox: box(searchEl),
                countBox: box(countEl),
                fabBox: box(fab),
                intentMockBox: box(intentMock),
                intentPartBox: box(intentPart),
                libBeforeParts,
                hasDetails: !!details,
                detailsOpen: details ? details.open : null,
                startBtnsCount: document.querySelectorAll('#partsList .step button[data-action="startPart"]').length,
                countText: countEl ? countEl.textContent.trim() : '',
                rowCount: rows.length,
                groupSkills,
                summariesCount: summaries.length,
                sampleSummary: summaries[1] || '',
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                html: view.outerHTML,
            };
        }"""
    )

    def overlaps(a, b):
        return a and b and a["w"] > 0 and a["h"] > 0 and b["w"] > 0 and b["h"] > 0 and not (
            a["right"] <= b["left"] or b["right"] <= a["left"] or a["bottom"] <= b["top"] or b["bottom"] <= a["top"]
        )

    assert prac["active"], "#v-practice not active"
    assert prac["libVisible"], "Library is not visible in #v-practice without clicks"
    assert prac["libBox"] and prac["libBox"]["top"] < 844, f"Library not in first viewport: {prac['libBox']}"
    assert prac["searchBox"] and 0 <= prac["searchBox"]["top"] and prac["searchBox"]["bottom"] <= 844, f"Search not visible without scroll: {prac['searchBox']}"
    assert prac["countBox"] and prac["countBox"]["bottom"] <= 844, f"Counter not visible without scroll: {prac['countBox']}"
    assert prac["intentMockBox"] and prac["intentMockBox"]["h"] >= 44, f"Full mock card missing or <44px: {prac['intentMockBox']}"
    assert prac["intentPartBox"] and prac["intentPartBox"]["h"] >= 44, f"Practise by part card missing or <44px: {prac['intentPartBox']}"
    assert not overlaps(prac["fabBox"], prac["searchBox"]), f"FAB overlaps search: fab={prac['fabBox']} search={prac['searchBox']}"
    assert not overlaps(prac["fabBox"], prac["intentMockBox"]), f"FAB overlaps Full mock card: fab={prac['fabBox']} card={prac['intentMockBox']}"
    assert not overlaps(prac["fabBox"], prac["intentPartBox"]), f"FAB overlaps By part card: fab={prac['fabBox']} card={prac['intentPartBox']}"
    assert prac["libBeforeParts"], "#practiceLibraryCard must appear before #practiceParts in DOM"
    assert prac["hasDetails"] and prac["detailsOpen"] is False, f"#practiceParts must be inside closed <details>: {prac}"
    assert prac["rowCount"] > 40, f"Expected real-practice Library rows in Practice, got {prac['rowCount']}"
    assert prac["countText"] == f"{prac['rowCount']} contents", f"Count mismatch: {prac['countText']!r}"
    assert prac["groupSkills"] == ["rue", "w", "l", "sp"], f"Unexpected Library group order: {prac['groupSkills']}"
    # Verify 0 lessons, 0 reference, 0 examiner notes in Library
    banned_rows = pg.evaluate(
        """() => [...document.querySelectorAll('#pracLibList a.exlib-row')].filter(a => {
            const t = a.dataset.type || '';
            const s = a.dataset.skill || '';
            const n = (a.dataset.name || '').toLowerCase();
            return t === 'lesson' || t === 'reference' || t === 'notes' || s === 'ref'
                || /lesson plan|teacher guide|handbook|examiner (notes|comments)/i.test(n);
        }).map(a => ({name: a.dataset.name, type: a.dataset.type, skill: a.dataset.skill}))"""
    )
    assert banned_rows == [], f"Filler/non-practice items leaked into Library: {banned_rows}"
    assert pg.locator("#pracLibPaperFilter [data-exlib-paper='ref']").count() == 0, "Reference filter chip still present"
    assert prac["summariesCount"] == 17, f"Expected 17 part summaries, got {prac['summariesCount']}"
    assert prac["startBtnsCount"] == 17, f"Expected 17 Start buttons, got {prac['startBtnsCount']}"
    assert "online" in prac["sampleSummary"].lower(), f"Part 2 summary missing online count: {prac['sampleSummary']!r}"
    assert "lesson" not in prac["sampleSummary"].lower(), f"Part summary still mentions lesson: {prac['sampleSummary']!r}"
    assert prac["scrollWidth"] <= prac["clientWidth"] + 1, f"Practice 390 light overflow: {prac['scrollWidth']} > {prac['clientWidth']}"
    assert not INLINE_HANDLER_RE.search(prac["html"]), "Inline on* handler in #v-practice"

    # Screenshots at scroll=0 (390 light & dark, and 1280 light)
    pg.evaluate("if(document.activeElement)document.activeElement.blur(); window.scrollTo(0, 0)")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "practice_hub_390_light.png"))

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); window.scrollTo(0, 0)")
    pg.wait_for_timeout(150)
    dark_overflow = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert dark_overflow <= 1, f"Practice 390 dark overflow: {dark_overflow}"
    pg.screenshot(path=os.path.join(OUT, "practice_hub_390_dark.png"))

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.set_viewport_size({"width": 1280, "height": 800})
    pg.evaluate("window.scrollTo(0, 0); if(document.activeElement)document.activeElement.blur()")
    pg.wait_for_timeout(150)
    desk_overflow = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert desk_overflow <= 1, f"Practice 1280 overflow: {desk_overflow}"
    pg.screenshot(path=os.path.join(OUT, "practice_hub_1280_light.png"))

    pg.set_viewport_size({"width": 390, "height": 844})
    pg.evaluate("window.scrollTo(0, 0)")
    pg.wait_for_timeout(150)

    # Library filters work inside Practice
    pg.fill("#pracLibSearch", "open cloze")
    pg.wait_for_timeout(150)
    filtered_search = pg.eval_on_selector_all("#pracLibList a.exlib-row", "els => els.length")
    assert 0 < filtered_search < prac["rowCount"], f"Search filter failed: {filtered_search}"
    pg.click("#pracLibPaperFilter button[data-exlib-paper='rue']")
    pg.wait_for_timeout(120)
    filtered_rue = pg.eval_on_selector_all("#pracLibList a.exlib-row", "els => els.length")
    assert filtered_rue > 0, "R&UoE filter returned 0 rows"
    pg.evaluate("resetExLibFilters(true, 'practice')")
    pg.wait_for_timeout(150)
    assert pg.eval_on_selector_all("#pracLibList a.exlib-row", "els => els.length") == prac["rowCount"], "Reset did not restore full Library"

    # --- 1b. Practised toggle: marks item, moves to end of group, Hide done hides it, persists across reload ---
    pg.evaluate("D.practised = {}; save(); refreshAll(); showView('practice');")
    pg.wait_for_timeout(150)
    log_len_before = pg.evaluate("D.log.length")
    first_item = pg.evaluate(
        """() => {
            const grp = document.querySelector('#pracLibList .exlib-group[data-skill="rue"]');
            const wraps = [...grp.querySelectorAll('.exlib-row-wrap')];
            return {
                key: wraps[0].dataset.practisedKey,
                totalInGrp: wraps.length,
                btnH: Math.round(wraps[0].querySelector('.practised-btn').getBoundingClientRect().height),
            };
        }"""
    )
    assert first_item["key"].startswith("lib:"), f"Unexpected lib practised key: {first_item}"
    assert first_item["btnH"] >= 44, f"Practised button height < 44px: {first_item}"
    pg.locator("#pracLibList .exlib-group[data-skill='rue'] .exlib-row-wrap").first.locator(".practised-btn").click()
    pg.wait_for_timeout(200)

    after_mark = pg.evaluate(
        """(key) => {
            const grp = document.querySelector('#pracLibList .exlib-group[data-skill="rue"]');
            const wraps = [...grp.querySelectorAll('.exlib-row-wrap')];
            const last = wraps[wraps.length - 1];
            return {
                savedDate: D.practised[key] || '',
                logLen: D.log.length,
                lastKey: last ? last.dataset.practisedKey : '',
                lastDone: last ? last.dataset.practised : '',
                lastBtnText: last ? last.querySelector('.practised-btn').textContent.trim() : '',
                overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            };
        }""",
        first_item["key"],
    )
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", after_mark["savedDate"]), f"Practised date not YYYY-MM-DD: {after_mark}"
    assert after_mark["logLen"] == log_len_before, "Marking practised must not modify D.log"
    assert after_mark["lastKey"] == first_item["key"], f"Marked item did not move to end of group: {after_mark}"
    assert after_mark["lastDone"] == "1" and "✓" in after_mark["lastBtnText"], after_mark
    assert after_mark["overflow"] <= 1, f"Library practised 390 overflow: {after_mark}"

    # Screenshot showing practised state in Library (filter to Part 1 so Hide done + unpractised + Done ✓ at bottom all appear in frame)
    pg.click("#pracLibPartFilter button[data-exlib-part='1']")
    pg.wait_for_timeout(150)
    pg.evaluate("""() => {
        document.documentElement.setAttribute('data-theme', 'light');
        const el = document.getElementById('pracLibHideDone');
        if (el) window.scrollTo(0, Math.max(0, el.getBoundingClientRect().top + window.scrollY - 110));
        if (document.activeElement) document.activeElement.blur();
    }""")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "library_practised_390_light.png"))
    pg.click("#pracLibPartFilter button[data-exlib-part='all']")
    pg.wait_for_timeout(150)

    # Hide done checkbox removes marked items and updates counter
    assert not pg.is_checked("#pracLibHideDone"), "Hide done should default off"
    pg.check("#pracLibHideDone")
    pg.wait_for_timeout(150)
    hidden_state = pg.evaluate(
        """(key) => ({
            rows: document.querySelectorAll('#pracLibList a.exlib-row').length,
            countText: document.getElementById('pracLibCount').textContent.trim(),
            present: !!document.querySelector('#pracLibList .exlib-row-wrap[data-practised-key="' + CSS.escape(key) + '"]'),
        })""",
        first_item["key"],
    )
    assert hidden_state["present"] is False, f"Hide done did not hide marked item: {hidden_state}"
    assert hidden_state["rows"] == prac["rowCount"] - 1, f"Hide done row count wrong: {hidden_state}"
    assert hidden_state["countText"] == f"{hidden_state['rows']} contents", hidden_state
    pg.uncheck("#pracLibHideDone")
    pg.wait_for_timeout(150)

    # Persist across reload, then unmark and verify reload
    pg.wait_for_timeout(500)
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    seed_mat_if_empty(pg)
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(250)
    persisted = pg.evaluate(
        """(key) => {
            const grp = document.querySelector('#pracLibList .exlib-group[data-skill="rue"]');
            const wraps = [...grp.querySelectorAll('.exlib-row-wrap')];
            const last = wraps[wraps.length - 1];
            return {
                date: (D.practised || {})[key] || '',
                lastKey: last ? last.dataset.practisedKey : '',
                lastDone: last ? last.dataset.practised : '',
            };
        }""",
        first_item["key"],
    )
    assert persisted["date"] and persisted["lastKey"] == first_item["key"] and persisted["lastDone"] == "1", (
        f"Practised state did not persist after reload: {persisted}"
    )
    # Unmark
    pg.locator("#pracLibList .exlib-group[data-skill='rue'] .exlib-row-wrap").last.locator(".practised-btn").click()
    pg.wait_for_timeout(500)
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    seed_mat_if_empty(pg)
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(250)
    assert pg.evaluate("(k) => !(D.practised && D.practised[k])", first_item["key"]), "Unmark did not persist after reload"
    out["1b_practised_library"] = {"key": first_item["key"], "persisted": True, "hide_done_rows": hidden_state["rows"]}

    # EN/ES copy check on Practice Hub
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    es_hub = pg.evaluate(
        """() => ({
            title: document.querySelector('#v-practice .page-title').textContent.trim(),
            sub: document.querySelector('#v-practice .page-sub').textContent.trim(),
            mockTitle: document.querySelector('#practiceIntentFullMock .practice-intent-title').textContent.trim(),
            partTitle: document.querySelector('#practiceIntentByPart .practice-intent-title').textContent.trim(),
            summary: document.getElementById('practicePartsSummary').textContent.trim(),
            count: document.getElementById('pracLibCount').textContent.trim(),
            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        })"""
    )
    assert es_hub["title"] == "Práctica", es_hub
    assert "full mock" in es_hub["sub"].lower() and "papers" in es_hub["sub"].lower(), es_hub
    assert es_hub["mockTitle"] == "Full mock" and es_hub["partTitle"] == "Practicar por parte", es_hub
    assert "ejercicios por parte" in es_hub["summary"].lower(), es_hub
    assert "contenidos" in es_hub["count"].lower(), es_hub
    assert es_hub["overflow"] <= 1, f"Practice 390 ES overflow: {es_hub}"
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)

    # Intent 1: "Full mock" opens #v-exam with pre-flight visible
    pg.click("#practiceIntentFullMock")
    pg.wait_for_timeout(250)
    fm_from_intent = pg.evaluate(
        """() => ({
            view: (document.querySelector('.view.active') || {}).id || '',
            preflightVisible: !document.getElementById('fullMockPreflight').hidden,
        })"""
    )
    assert fm_from_intent == {"view": "v-exam", "preflightVisible": True}, f"Full mock intent failed: {fm_from_intent}"
    pg.evaluate("closeFullMockPreflight()")
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(250)

    # Intent 2: "Practise by part" opens the parts <details>
    assert pg.evaluate("!document.getElementById('practicePartsDetails').open"), "Details should still be closed before clicking Practise by part"
    pg.click("#practiceIntentByPart")
    pg.wait_for_timeout(250)
    parts_opened = pg.evaluate(
        """() => ({
            open: document.getElementById('practicePartsDetails').open,
            visibleStarts: [...document.querySelectorAll('#partsList .step button[data-action="startPart"]')].filter(b => b.getBoundingClientRect().height >= 44).length,
        })"""
    )
    assert parts_opened["open"] is True and parts_opened["visibleStarts"] == 17, f"Practise by part did not reveal 17 Start buttons: {parts_opened}"

    out["1_practice_library"] = {"rows": prac["rowCount"], "count": prac["countText"], "summary_p2": prac["sampleSummary"]}

    # --- 2. Start on Reading Part 2 opens session on Contents ---------------
    pg.click("#partsList .step button[data-action='startPart'][data-i='1']")
    pg.wait_for_timeout(250)
    part2 = pg.evaluate(
        """() => {
            const ws = document.getElementById('sessionWorkspace');
            const cnt = document.getElementById('sessionTabContents');
            const ses = document.getElementById('sessionTabSession');
            const primary = document.getElementById('sessionOnlinePrimaryBtn');
            const rows = [...document.querySelectorAll('#exLibList a.exlib-row')].map(a => ({
                name: a.dataset.name || '',
                skill: a.dataset.skill || '',
                type: a.dataset.type || '',
                origin: a.dataset.origin || '',
                href: a.getAttribute('href') || '',
                parts: (a.dataset.parts || '').split(',').filter(Boolean),
            }));
            return {
                wsVisible: !ws.hidden,
                cntVisible: !cnt.hidden,
                sesVisible: !ses.hidden,
                primaryVisible: primary && !document.getElementById('sessionOnlinePrimaryWrap').hidden,
                primaryHref: primary ? primary.getAttribute('href') : '',
                primaryTarget: primary ? primary.getAttribute('target') : '',
                primaryText: primary ? primary.textContent.trim() : '',
                rows,
            };
        }"""
    )
    assert part2["wsVisible"] and part2["cntVisible"] and not part2["sesVisible"], f"Start did not open Contents: {part2}"
    assert part2["primaryVisible"] and part2["primaryHref"].startswith("https://") and part2["primaryTarget"] == "_blank", part2
    papers = [r for r in part2["rows"] if r["origin"] == "local" and r["type"] == "paper"]
    keys = [r for r in part2["rows"] if r["origin"] == "local" and r["type"] == "key"]
    online = [r for r in part2["rows"] if r["origin"] == "online"]
    assert len(papers) >= 1, f"Missing paper in Part 2 Contents: {part2['rows']}"
    assert len(keys) >= 1, f"Missing key in Part 2 Contents: {part2['rows']}"
    assert 2 <= len(online) <= 4, f"Expected 2-4 online sources for Part 2, got {len(online)}: {online}"
    for r in part2["rows"]:
        assert r["skill"] == "rue", f"Wrong skill leaked: {r}"
        if r["origin"] == "online":
            assert "2" in r["parts"], f"Online source from another part leaked into Part 2: {r}"
        else:
            assert not r["parts"] or "2" in r["parts"], f"Local item from another part leaked into Part 2: {r}"
    # Order check: paper before key before lesson before online
    first_paper = min(i for i, r in enumerate(part2["rows"]) if r["type"] == "paper")
    first_key = min(i for i, r in enumerate(part2["rows"]) if r["type"] == "key")
    first_online = min(i for i, r in enumerate(part2["rows"]) if r["origin"] == "online")
    assert first_paper < first_key < first_online, f"Wrong Contents order: paper@{first_paper}, key@{first_key}, online@{first_online}"
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)
    out["2_part2_contents"] = {"papers": len(papers), "keys": len(keys), "online": len(online), "primary": part2["primaryText"]}

    # --- 3. Today's cycle counter is clickable and opens filtered Library ---
    pg.evaluate(
        """() => {
            D.profile = {
                examDate: null, targetGrade: 'B',
                skills: {rue: 3, w: 3, l: 3, sp: 3},
                hoursWeek: 6, days: [0,1,2,3,4,5,6],
                struggles: [], strugglesDeclared: [],
            };
            D.settings.schedule = [0,1,2,3,4,5,6].map(day => ({day, time: '15:00'}));
            D.settings.rotationMode = 'by-part';
            D.settings.itemsPerSession = 1;
            save();
            refreshAll();
            showView('hoy');
        }"""
    )
    pg.wait_for_timeout(200)
    cyc = pg.evaluate(
        """() => {
            const el = document.getElementById('todayCycleValue');
            const r = el ? el.getBoundingClientRect() : null;
            return {
                tag: el ? el.tagName.toLowerCase() : '',
                skill: el ? (el.dataset.skill || '') : '',
                text: el ? el.textContent.trim() : '',
                h: r ? Math.round(r.height) : 0,
            };
        }"""
    )
    assert cyc["tag"] == "button", f"#todayCycleValue is not a button: {cyc}"
    assert cyc["skill"] in ("rue", "w", "l", "sp"), f"Missing skill on cycle counter: {cyc}"
    assert cyc["h"] >= 44, f"#todayCycleValue height {cyc['h']} < 44px"
    pg.click("#todayCycleValue")
    pg.wait_for_timeout(250)
    after_cyc = pg.evaluate(
        """() => ({
            view: (document.querySelector('.view.active') || {}).id || '',
            paper: EXLIB_PRACTICE_STATE.paper,
            skills: [...new Set([...document.querySelectorAll('#pracLibList a.exlib-row')].map(a => a.dataset.skill))],
            count: document.querySelectorAll('#pracLibList a.exlib-row').length,
        })"""
    )
    assert after_cyc["view"] == "v-practice", f"Cycle counter did not open Practice Library: {after_cyc}"
    assert after_cyc["paper"] == cyc["skill"], f"Library paper {after_cyc['paper']!r} != cycle skill {cyc['skill']!r}"
    assert after_cyc["skills"] == [cyc["skill"]] and after_cyc["count"] > 0, after_cyc
    out["3_today_cycle_click"] = {"skill": cyc["skill"], "rows": after_cyc["count"]}

    # --- 4 & 5. Exam Full Mock Pre-flight, exact materials & unlimited exit --
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(250)
    pg.click("button[data-action='startFullMock']")
    pg.wait_for_timeout(250)

    fm = pg.evaluate(
        """() => {
            const box = document.getElementById('fullMockPreflight');
            const papers = [...document.querySelectorAll('#fmPapersList .fm-paper-row')].map(row => ({
                paper: row.dataset.fmPaper || '',
                text: row.querySelector('.fm-paper-name')?.textContent.trim() || '',
                matBtn: !!row.querySelector('button[data-action="openFullPaperLibrary"]'),
                links: [...row.querySelectorAll('.fm-paper-links a')].map(a => ({
                    text: a.textContent.trim(),
                    href: a.getAttribute('href') || '',
                })),
            }));
            const samples = [...document.querySelectorAll('#fmSampleList button.fm-sample-btn')].map(b => ({
                id: b.dataset.sample || '',
                text: b.textContent.trim(),
                pressed: b.getAttribute('aria-pressed'),
            }));
            const online = [...document.querySelectorAll('#fmOnlineList a.fm-online-card')].map(a => ({
                text: a.textContent.trim(),
                href: a.getAttribute('href') || '',
                target: a.getAttribute('target') || '',
            }));
            return {
                visible: !!box && !box.hidden,
                doneVisible: getComputedStyle(document.getElementById('fmDoneBanner')).display !== 'none',
                timerRunning: !!exIv,
                papers,
                samples,
                online,
                startSeqExists: !!document.getElementById('fmStartSeqBtn'),
                aiQuotaText: (document.getElementById('fmAiQuota') || {}).textContent?.trim() || '',
                allText: box ? box.textContent.toLowerCase() : '',
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
            };
        }"""
    )
    assert fm["visible"], "Full mock pre-flight did not open"
    assert not fm["doneVisible"], "Done banner should be hidden before finishing a full mock"
    assert not fm["timerRunning"], "Start full mock started countdown blindly instead of pre-flight"
    assert [x["paper"] for x in fm["papers"]] == ["rue", "w", "l", "sp"], fm["papers"]
    assert all(x["matBtn"] for x in fm["papers"]), f"Missing Open materials button in pre-flight: {fm['papers']}"
    assert len(fm["samples"]) >= 2, f"Expected local samples in selector: {fm['samples']}"
    assert len(fm["online"]) >= 4, f"Expected >= 4 online full mocks, got {len(fm['online'])}: {fm['online']}"
    assert all(o["href"].startswith("https://") and o["target"] == "_blank" for o in fm["online"]), fm["online"]
    assert fm["startSeqExists"], "Start 195' sequence button missing"
    assert fm["aiQuotaText"], "AI speaking quota info missing"
    assert "no hay más" not in fm["allText"] and "no more mocks" not in fm["allText"]
    # Verify exact materials on R&UoE (paper + key) and Listening (paper + key + audio)
    rue_links = [x["text"].lower() for x in fm["papers"][0]["links"]]
    l_links = [x["text"].lower() for x in fm["papers"][2]["links"]]
    assert any("paper" in t for t in rue_links) and any("key" in t for t in rue_links), rue_links
    assert any("paper" in t for t in l_links) and any("key" in t for t in l_links) and any("audio" in t for t in l_links), l_links
    assert fm["scrollWidth"] <= fm["clientWidth"] + 1, f"Pre-flight 390 overflow: {fm['scrollWidth']} > {fm['clientWidth']}"

    pg.evaluate("document.getElementById('fullMockPreflight').scrollIntoView({block:'start'}); if(document.activeElement)document.activeElement.blur();")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "full_mock_preflight_390_light.png"))

    # Finish mock -> "Do another full mock" / "Hacer otro full mock" available
    pg.evaluate("markFullMockCompleted()")
    pg.wait_for_timeout(150)
    done_en = pg.evaluate(
        """() => ({
            bannerVisible: !document.getElementById('fmDoneBanner').hidden,
            btnText: document.getElementById('fmDoAnotherBtn').textContent.trim(),
        })"""
    )
    assert done_en["bannerVisible"] and done_en["btnText"] == "Do another full mock", done_en

    # Spanish symmetry check on pre-flight and Practice Library
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    done_es = pg.evaluate(
        """() => ({
            btnText: document.getElementById('fmDoAnotherBtn').textContent.trim(),
            onlineTitle: document.querySelector('#fullMockPreflight [data-i18n="fm_online_title"]').textContent.trim(),
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
        })"""
    )
    assert done_es["btnText"] == "Hacer otro full mock", done_es
    assert "online" in done_es["onlineTitle"].lower(), done_es
    assert done_es["scrollWidth"] <= done_es["clientWidth"] + 1, "Pre-flight 390 ES overflow"

    # Clicking "Hacer otro full mock" advances to next sample cleanly
    first_sample = fm["samples"][0]["id"]
    pg.click("#fmDoAnotherBtn")
    pg.wait_for_timeout(150)
    next_sample = pg.evaluate("FULL_MOCK.sample")
    assert next_sample != first_sample, f"Do another full mock did not advance sample: {next_sample}"

    # Mark a full mock paper as practised -> stores mock:rue, shows "Hecho" badge in ES, allows unmarking
    pg.click("#fmPapersList .fm-paper-row[data-fm-paper='rue'] .practised-mock-btn")
    pg.wait_for_timeout(150)
    mock_marked = pg.evaluate(
        """() => {
            const row = document.querySelector('#fmPapersList .fm-paper-row[data-fm-paper="rue"]');
            return {
                saved: (D.practised || {})['mock:rue'] || '',
                doneAttr: row ? row.dataset.practised : '',
                text: row ? row.textContent : '',
            };
        }"""
    )
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", mock_marked["saved"]), f"mock:rue not saved: {mock_marked}"
    assert mock_marked["doneAttr"] == "1" and "Hecho" in mock_marked["text"], mock_marked
    pg.click("#fmPapersList .fm-paper-row[data-fm-paper='rue'] .practised-mock-btn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("!(D.practised && D.practised['mock:rue'])"), "Unmarking mock:rue failed"

    # Clicking "Abrir materiales" on Listening in pre-flight opens Library filtered to Listening full paper
    pg.click("#fmPapersList .fm-paper-row[data-fm-paper='l'] button[data-action='openFullPaperLibrary']")
    pg.wait_for_timeout(250)
    l_lib = pg.evaluate(
        """() => ({
            view: (document.querySelector('.view.active') || {}).id || '',
            paper: EXLIB_PRACTICE_STATE.paper,
            scope: EXLIB_PRACTICE_STATE.scope,
            types: [...new Set([...document.querySelectorAll('#pracLibList a.exlib-row')].map(a => a.dataset.type))],
            skills: [...new Set([...document.querySelectorAll('#pracLibList a.exlib-row')].map(a => a.dataset.skill))],
        })"""
    )
    assert l_lib["view"] == "v-practice" and l_lib["paper"] == "l" and l_lib["scope"] == "full", l_lib
    assert l_lib["skills"] == ["l"], l_lib
    assert "paper" in l_lib["types"] and "key" in l_lib["types"] and "audio" in l_lib["types"], l_lib

    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(150)
    assert page_errors == [], f"Page errors: {page_errors}"
    assert console_errors == [], f"Console errors: {console_errors}"

    out["4_5_full_mock"] = {
        "samples": [s["id"] for s in fm["samples"]],
        "online_count": len(fm["online"]),
        "next_sample": next_sample,
        "listening_full_types": l_lib["types"],
        "es_do_another": done_es["btnText"],
    }
    out["screenshots"] = [
        "practice_hub_390_light.png",
        "practice_hub_390_dark.png",
        "practice_hub_1280_light.png",
        "full_mock_preflight_390_light.png",
    ]
    out["page_errors"] = page_errors
    out["console_errors"] = console_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
