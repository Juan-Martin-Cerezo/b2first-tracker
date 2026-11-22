"""Phase practice-flow acceptance: intent -> exact resources, always-visible Library, unlimited full mocks.

Verifies:
  1. #v-practice renders the Library immediately without extra clicks, with counter and rows,
     plus a resource mini-summary per part row in #partsList.
  2. Start on Reading Part 2 opens the session on Contents and lists local paper + answer key
     + lesson plan + 2-4 online sources for Part 2 (zero sources from other parts) and a
     primary "Practise online" link opening in a new tab.
  3. Today's cycle counter (#todayCycleValue) is clickable and opens the Library filtered
     to its skill.
  4. In Exam, "Start full mock" opens the pre-flight (not the countdown directly) with all
     4 papers in official order, a sample selector from MAT, and >= 4 free online full mocks;
     after finishing, "Do another full mock" / "Hacer otro full mock" is offered.
  5. Full mock offers exact materials per paper (paper + key + audio + speaking cards) and
     never shows a dead-end "no more mocks" message; service plan allows 3 speaking mocks / 45 min.
  6. 390x844 light & dark with zero horizontal overflow, symmetric EN/ES copy, zero duplicate
     IDs across the whole DOM, zero inline on* handlers, zero page errors.

Saves screenshots in tests/out/:
  practice_library_390_light.png, practice_library_390_dark.png, full_mock_preflight_390_light.png.
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
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
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

    # --- 1. #v-practice shows Library immediately without clicks ------------
    pg.click("nav button[data-view='practice']")
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light'); window.scrollTo(0, 0)")
    pg.wait_for_timeout(250)

    prac = pg.evaluate(
        """() => {
            const view = document.getElementById('v-practice');
            const libCard = document.getElementById('practiceLibraryCard');
            const countEl = document.getElementById('pracLibCount');
            const rows = [...document.querySelectorAll('#pracLibList a.exlib-row')];
            const summaries = [...document.querySelectorAll('#partsList .step .step-res-summary')]
                .map(e => e.textContent.trim());
            const r = libCard ? libCard.getBoundingClientRect() : null;
            return {
                active: view.classList.contains('active'),
                libVisible: !!libCard && getComputedStyle(libCard).display !== 'none' && !libCard.hidden && (r ? r.height > 80 : false),
                countText: countEl ? countEl.textContent.trim() : '',
                rowCount: rows.length,
                summariesCount: summaries.length,
                sampleSummary: summaries[1] || '',
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                html: view.outerHTML,
            };
        }"""
    )
    assert prac["active"], "#v-practice not active"
    assert prac["libVisible"], "Library is not visible in #v-practice without clicks"
    assert prac["rowCount"] > 50, f"Expected full Library rows in Practice, got {prac['rowCount']}"
    assert prac["countText"] == f"{prac['rowCount']} contents", f"Count mismatch: {prac['countText']!r}"
    assert prac["summariesCount"] >= 15, f"Missing part resource summaries: {prac['summariesCount']}"
    assert "online" in prac["sampleSummary"].lower(), f"Part 2 summary missing online count: {prac['sampleSummary']!r}"
    assert prac["scrollWidth"] <= prac["clientWidth"] + 1, f"Practice 390 light overflow: {prac['scrollWidth']} > {prac['clientWidth']}"
    assert not INLINE_HANDLER_RE.search(prac["html"]), "Inline on* handler in #v-practice"

    # Scroll to the Library card for light & dark screenshots
    pg.evaluate("document.getElementById('practiceLibraryCard').scrollIntoView({block:'start'}); if(document.activeElement)document.activeElement.blur();")
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "practice_library_390_light.png"))

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    pg.wait_for_timeout(150)
    dark_overflow = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert dark_overflow <= 1, f"Practice 390 dark overflow: {dark_overflow}"
    pg.screenshot(path=os.path.join(OUT, "practice_library_390_dark.png"))
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light'); window.scrollTo(0, 0)")
    pg.wait_for_timeout(150)
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

    out["4_5_full_mock"] = {
        "samples": [s["id"] for s in fm["samples"]],
        "online_count": len(fm["online"]),
        "next_sample": next_sample,
        "listening_full_types": l_lib["types"],
        "es_do_another": done_es["btnText"],
    }
    out["screenshots"] = [
        "practice_library_390_light.png",
        "practice_library_390_dark.png",
        "full_mock_preflight_390_light.png",
    ]
    out["page_errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
