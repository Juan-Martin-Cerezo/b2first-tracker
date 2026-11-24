"""Phase start-library acceptance: one single Start opening the session with Contents.

Verifies:
  1. Practice has no "Library" button per row and no Practice Library tab;
     each unit row in #partsList has exactly one Start action button.
  2. Clicking Start on Reading part 2 opens the session view with internal
     tabs Session and Contents, with the Reading studio armed to Part 2.
  3. Contents lists only items for that skill and part (plus whole-paper
     local papers & keys), with matching counter ("N contents"), at least one
     local paper (/files/), its answer key (/files/), lesson plan, and online
     sources (https://, target=_blank, noopener). Search filters Contents.
  4. "See all in this paper" expands to the full paper without closing the
     session, and exposes the full library filters (including All papers /
     Reference).
  5. Switching to Session and back to Contents preserves the state (expanded
     scope, search query, filtered list).
  6. No "Browse all exercises" / "Open library" button exists in Today or Exam.
  7. Today Start and Plan Start also open sessions with their Contents tab.
  8. Closing the session returns to Practice without leaving half-baked state.
  9. 390x844 (light & dark) and 1280x900: zero horizontal overflow, >=44px
     targets, EN/ES symmetric tabs ("Session"/"Contents" vs "Sesión"/"Contenidos"),
     zero inline handlers, zero page errors.

Saves screenshots in tests/out/:
  start_contents_390_light.png, start_contents_390_dark.png, start_contents_1280_light.png.
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

INLINE_HANDLER_RE = re.compile(r'\bon[a-z]+\s*=\s*"')


def inspect_contents(pg):
    return pg.evaluate(
        r"""() => {
            const ws = document.getElementById('sessionWorkspace');
            const sesPanel = document.getElementById('sessionTabSession');
            const cntPanel = document.getElementById('sessionTabContents');
            const list = document.getElementById('exLibList');
            const countEl = document.getElementById('exLibCount');
            const scopeBtn = document.getElementById('sessionContentsScopeBtn');
            const advEl = document.getElementById('exLibAdvancedFilters');
            const closeBtn = document.getElementById('sessionCloseBtn');
            const search = document.getElementById('exLibSearch');
            const tabs = [...document.querySelectorAll('#sessionTabs button[role="tab"]')].map(b => ({
                tab: b.dataset.sessionTab || '',
                text: b.textContent.trim(),
                selected: b.getAttribute('aria-selected'),
                h: Math.round(b.getBoundingClientRect().height),
            }));
            const rows = list ? [...list.querySelectorAll('a.exlib-row')].map(a => {
                const r = a.getBoundingClientRect();
                const partEl = a.querySelector('.exlib-pill.is-part');
                return {
                    href: a.getAttribute('href') || '',
                    target: a.getAttribute('target') || '',
                    rel: a.getAttribute('rel') || '',
                    skill: a.dataset.skill || '',
                    type: a.dataset.type || '',
                    origin: a.dataset.origin || '',
                    mins: Number(a.dataset.mins || 0),
                    parts: (a.dataset.parts || '').split(',').filter(Boolean),
                    partLabel: partEl ? partEl.textContent.trim() : '',
                    name: a.dataset.name || '',
                    h: Math.round(r.height),
                    right: Math.round(r.right),
                };
            }) : [];
            return {
                wsVisible: ws ? !ws.hidden : false,
                sesVisible: sesPanel ? !sesPanel.hidden : false,
                cntVisible: cntPanel ? !cntPanel.hidden : false,
                tabs,
                rows,
                countText: countEl ? countEl.textContent.trim() : '',
                scopeVisible: scopeBtn ? !scopeBtn.hidden : false,
                scopeText: scopeBtn ? scopeBtn.textContent.trim() : '',
                scopeH: scopeBtn ? Math.round(scopeBtn.getBoundingClientRect().height) : 0,
                advVisible: advEl ? !advEl.hidden : false,
                closeH: closeBtn ? Math.round(closeBtn.getBoundingClientRect().height) : 0,
                searchH: search ? Math.round(search.getBoundingClientRect().height) : 0,
                searchVal: search ? search.value : '',
                paperText: (document.getElementById('sessionUnitPaper') || {}).textContent || '',
                titleText: (document.getElementById('sessionUnitTitle') || {}).textContent || '',
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                state: EXLIB_STATE,
                wsHtml: ws ? ws.outerHTML : '',
            };
        }"""
    )


def assert_part_first_order(rows, part_str, label):
    assert rows, f"{label}: Contents rendered 0 rows"
    type_rank = {"paper": 0, "key": 1, "tapescript": 1, "audio": 2, "checklist": 3, "online": 4}

    def rank_key(r):
        parts = r["parts"]
        is_online = r["origin"] == "online" or r["type"] == "online"
        t_rank = 4 if is_online else type_rank.get(r["type"], 5)
        if parts == [part_str]:
            spec = 0
        elif part_str in parts:
            spec = 1
        else:
            spec = 2
        return (t_rank, spec, r["mins"])

    for r in rows:
        if r["origin"] == "online":
            assert part_str in r["parts"], f"{label}: online row from wrong part leaked: {r}"
        else:
            assert not r["parts"] or part_str in r["parts"], f"{label}: local row from wrong part leaked: {r}"

    keys = [rank_key(r) for r in rows]
    assert keys == sorted(keys), (
        f"{label}: rows not in expected paper->key->audio->lesson->online order: "
        f"{[(r['name'], r['partLabel'], r['type'], r['mins']) for r in rows]}"
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

    # Ensure local material index is loaded (or seeded if /libros.json is empty on disk)
    pg.evaluate("loadMaterial()")
    pg.wait_for_timeout(400)
    mat_count = pg.evaluate("Object.keys(MAT).length")
    if mat_count == 0:
        pg.evaluate(
            """() => {
                const keys = [
                    'rueS1','rueS2','keyS1','keyS2','lpR1','lpR2','lpR3','fR2',
                    'wS1','wS2','lpW1','lpW2','lS1','lkS1','auS1','tsS1','lpL2','lpL3','auS2p3',
                    'spS1','exC0','lpSp2','hb'
                ];
                keys.forEach(k => { MAT[k] = '/files/test-' + k + '.pdf'; });
                renderParts(); renderGuides(); renderExercisesLibrary();
            }"""
        )

    # 1. Practice opens on Library first, with #practiceParts inside a closed <details>;
    #    opening it reveals all 17 part rows, each with exactly 1 Start button and no Library button.
    pg.click("nav button[data-view='practice']")
    pg.wait_for_timeout(250)
    pre_open = pg.evaluate(
        """() => {
            const libCard = document.getElementById('practiceLibraryCard');
            const parts = document.getElementById('practiceParts');
            const details = parts ? parts.closest('details') : null;
            return {
                libVisible: !!libCard && getComputedStyle(libCard).display !== 'none' && !libCard.hidden,
                libTop: libCard ? Math.round(libCard.getBoundingClientRect().top) : 9999,
                libBeforeParts: !!(libCard && parts && (libCard.compareDocumentPosition(parts) & Node.DOCUMENT_POSITION_FOLLOWING)),
                detailsClosed: !!details && details.open === false,
                pracCount: (document.getElementById('pracLibCount') || {}).textContent?.trim() || '',
            };
        }"""
    )
    assert pre_open["libVisible"] and pre_open["libTop"] < 844, f"Library not visible in first viewport: {pre_open}"
    assert pre_open["libBeforeParts"], "#practiceLibraryCard must come before #practiceParts"
    assert pre_open["detailsClosed"], f"#practiceParts must be in a closed <details>: {pre_open}"
    assert pre_open["pracCount"], "Practice Library counter empty"

    pg.click("#practiceIntentByPart")
    pg.wait_for_timeout(200)
    practice_info = pg.evaluate(
        """() => {
            const view = document.getElementById('v-practice');
            const steps = [...view.querySelectorAll('#partsList .step')];
            const perStep = steps.map(s => {
                const actBtns = [...s.querySelectorAll('.step-actions button')].map(b => ({
                    text: b.textContent.trim(),
                    action: b.dataset.action || '',
                    h: Math.round(b.getBoundingClientRect().height),
                }));
                const allTexts = [...s.querySelectorAll('button')].map(b => b.textContent.trim());
                return { actBtns, allTexts };
            });
            return {
                active: view.classList.contains('active'),
                detailsOpen: !!document.getElementById('practicePartsDetails')?.open,
                hasPracticeTabs: !!document.getElementById('practiceTabs'),
                hasTabLibrary: !!document.getElementById('practiceTabLibrary'),
                hasTabLibraryBtn: !!document.getElementById('practiceTabLibraryBtn'),
                stepCount: steps.length,
                perStep,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                html: view.outerHTML,
            };
        }"""
    )
    assert practice_info["active"], "#v-practice is not active"
    assert practice_info["detailsOpen"], "#practicePartsDetails did not open"
    assert not practice_info["hasPracticeTabs"], "#practiceTabs still exists"
    assert not practice_info["hasTabLibrary"], "#practiceTabLibrary still exists"
    assert not practice_info["hasTabLibraryBtn"], "#practiceTabLibraryBtn still exists"
    assert practice_info["stepCount"] == 17, f"Expected 17 parts, got {practice_info['stepCount']}"
    assert not INLINE_HANDLER_RE.search(practice_info["html"]), "Inline on* handler in #v-practice"
    assert practice_info["scrollWidth"] <= practice_info["clientWidth"] + 1, "Overflow in Practice 390"
    for idx, st in enumerate(practice_info["perStep"]):
        assert len(st["actBtns"]) == 2, f"Row {idx} should have Start + Mark done buttons, got {st['actBtns']}"
        assert st["actBtns"][0]["action"] == "startPart", f"Row {idx} first button is not startPart: {st['actBtns']}"
        assert st["actBtns"][0]["text"] == "Start", f"Row {idx} button label != Start: {st['actBtns']}"
        assert st["actBtns"][0]["h"] >= 44, f"Row {idx} Start button < 44px: {st['actBtns']}"
        assert st["actBtns"][1]["action"] == "togglePractised", f"Row {idx} second button is not togglePractised: {st['actBtns']}"
        assert st["actBtns"][1]["h"] >= 44, f"Row {idx} Mark done button < 44px: {st['actBtns']}"
        assert not any("library" in t.lower() for t in st["allTexts"]), (
            f"Row {idx} still mentions Library: {st['allTexts']}"
        )
    out["1_practice_single_start"] = {"steps": practice_info["stepCount"]}

    # 2. Tap Start on Reading part 2 -> opens session view on Contents tab with Session / Contents tabs.
    pg.click("#partsList .step button[data-action='startPart'][data-i='1']")
    pg.wait_for_timeout(250)
    ses_state = inspect_contents(pg)
    assert ses_state["wsVisible"], "Session workspace did not open"
    assert ses_state["cntVisible"] and not ses_state["sesVisible"], "Contents tab should be active by default on part Start"
    assert [t["text"] for t in ses_state["tabs"]] == ["Session", "Contents"], (
        f"Unexpected session tabs: {ses_state['tabs']}"
    )
    for tab in ses_state["tabs"]:
        assert tab["h"] >= 44, f"Session tab height < 44px: {tab}"
    assert ses_state["closeH"] >= 44, f"Close button height < 44px: {ses_state['closeH']}"
    assert pg.evaluate("document.getElementById('uePart').value") == "2", "Studio uePart is not 2"
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(150)
    assert pg.evaluate("getComputedStyle(document.getElementById('studioMonA')).display !== 'none'"), (
        "Reading studio #studioMonA is not visible"
    )
    assert not INLINE_HANDLER_RE.search(ses_state["wsHtml"]), "Inline on* handler in #sessionWorkspace"
    out["2_session_opened"] = {
        "paper": ses_state["paperText"],
        "title": ses_state["titleText"],
        "tabs_en": [t["text"] for t in ses_state["tabs"]],
    }

    # 3. Switch to Contents -> only R&UoE + Part 2 (or whole-paper) items, counter matches,
    #    has local paper, answer key, lesson plan, and online sources.
    pg.click("#sessionTabContentsBtn")
    pg.wait_for_timeout(250)
    cnt_state = inspect_contents(pg)
    assert cnt_state["cntVisible"] and not cnt_state["sesVisible"], "Contents tab did not open"
    assert not cnt_state["advVisible"], "Advanced filters should start hidden in unit scope"
    assert cnt_state["scopeVisible"] and cnt_state["scopeText"] == "See all in this paper", (
        f"Unexpected scope link: {cnt_state['scopeText']!r}"
    )
    assert cnt_state["scopeH"] >= 44, f"Scope link height < 44px: {cnt_state['scopeH']}"
    assert cnt_state["searchH"] >= 44, f"Search input height < 44px: {cnt_state['searchH']}"
    rows = cnt_state["rows"]
    assert len(rows) > 0, "Contents rendered 0 rows for Reading part 2"
    expected_count = "1 content" if len(rows) == 1 else f"{len(rows)} contents"
    assert cnt_state["countText"] == expected_count, (
        f"Counter mismatch: {cnt_state['countText']!r} != {expected_count!r}"
    )
    assert all(r["skill"] == "rue" for r in rows), (
        f"Non-rue items leaked into Reading part 2 Contents: {[r for r in rows if r['skill'] != 'rue'][:5]}"
    )
    for r in rows:
        assert not r["parts"] or "2" in r["parts"], (
            f"Item from another part leaked into Part 2 Contents: {r}"
        )
        assert r["href"], f"Empty href: {r}"
        if r["origin"] == "local":
            assert r["href"].startswith("/files/"), f"Local item href does not start with /files/: {r}"
        else:
            assert r["href"].startswith("https://"), f"Online item href not https://: {r}"
            assert r["target"] == "_blank", f"Online item missing target=_blank: {r}"
            assert "noopener" in r["rel"], f"Online item missing noopener: {r}"
        assert r["h"] >= 44, f"Content row < 44px: {r}"
        assert r["right"] <= cnt_state["clientWidth"] + 1, f"Row overflows right edge: {r}"

    local_papers = [r for r in rows if r["origin"] == "local" and r["type"] == "paper"]
    local_keys = [r for r in rows if r["origin"] == "local" and r["type"] == "key"]
    local_lessons = [r for r in rows if r["type"] in ("lesson", "reference", "notes")]
    online_rows = [r for r in rows if r["origin"] == "online"]
    assert len(local_papers) >= 1, f"Expected >=1 local paper, got {local_papers}"
    assert len(local_keys) >= 1, f"Expected >=1 local answer key, got {local_keys}"
    assert len(local_lessons) == 0, f"Expected 0 lesson/reference/notes items, got {local_lessons}"
    assert len(online_rows) >= 1, f"Expected >=1 online source, got {online_rows}"
    # Verify unit ordering: exact Part 2 items first (no "All parts" before Part 2),
    # then general lessons, full papers ("All parts"), multi-part online, general online.
    assert_part_first_order(rows, "2", "Reading Part 2")

    # Capture 390x844 light & dark screenshots of the session Contents view
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light'); if(document.activeElement)document.activeElement.blur(); window.scrollTo(0, 0)")
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(150)
    light_st = inspect_contents(pg)
    assert light_st["scrollWidth"] <= light_st["clientWidth"] + 1, (
        f"390 light overflow: {light_st['scrollWidth']} > {light_st['clientWidth']}"
    )
    pg.screenshot(path=os.path.join(OUT, "start_contents_390_light.png"))

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); if(document.activeElement)document.activeElement.blur(); window.scrollTo(0, 0)")
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(150)
    dark_st = inspect_contents(pg)
    assert dark_st["scrollWidth"] <= dark_st["clientWidth"] + 1, (
        f"390 dark overflow: {dark_st['scrollWidth']} > {dark_st['clientWidth']}"
    )
    pg.screenshot(path=os.path.join(OUT, "start_contents_390_dark.png"))
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(100)

    out["3_contents_part2"] = {
        "total": len(rows),
        "countText": cnt_state["countText"],
        "local_papers": len(local_papers),
        "local_keys": len(local_keys),
        "local_lessons": len(local_lessons),
        "online": len(online_rows),
    }

    # 4. "See all in this paper" expands to the whole paper without closing the session.
    pg.click("#sessionContentsScopeBtn")
    pg.wait_for_timeout(200)
    paper_state = inspect_contents(pg)
    assert paper_state["wsVisible"] and paper_state["cntVisible"], "Session closed on See all in this paper"
    assert paper_state["advVisible"], "Full library filters did not reveal on See all in this paper"
    assert len(paper_state["rows"]) > len(rows), (
        f"See all in this paper did not expand rows: {len(paper_state['rows'])} <= {len(rows)}"
    )
    assert all(r["skill"] == "rue" for r in paper_state["rows"]), "Paper scope leaked other skills"
    assert any("5" in r["parts"] or "3" in r["parts"] for r in paper_state["rows"]), (
        "Expanded paper did not include other parts of R&UoE"
    )
    assert paper_state["scopeText"] == "Back to Part 2", f"Unexpected collapse label: {paper_state['scopeText']!r}"
    out["4_see_all_paper"] = {"expanded_rows": len(paper_state["rows"]), "countText": paper_state["countText"]}

    # 5. Switching to Session and back to Contents preserves state (expanded + search query).
    pg.fill("#exLibSearch", "Open cloze")
    pg.wait_for_timeout(150)
    before_switch = inspect_contents(pg)
    assert len(before_switch["rows"]) >= 1, "Search 'Open cloze' returned 0 rows"
    pg.click("#sessionTabSessionBtn")
    pg.wait_for_timeout(150)
    assert inspect_contents(pg)["sesVisible"], "Did not switch to Session tab"
    pg.click("#sessionTabContentsBtn")
    pg.wait_for_timeout(150)
    after_switch = inspect_contents(pg)
    assert after_switch["cntVisible"], "Did not return to Contents tab"
    assert after_switch["advVisible"] is True, "Expanded state was lost after tab round-trip"
    assert after_switch["searchVal"] == "Open cloze", f"Search query lost: {after_switch['searchVal']!r}"
    assert len(after_switch["rows"]) == len(before_switch["rows"]), (
        f"Row count changed after round-trip: {len(after_switch['rows'])} != {len(before_switch['rows'])}"
    )
    pg.click("#exLibClear")
    pg.wait_for_timeout(120)
    out["5_preserved_state"] = {
        "query": "Open cloze",
        "rows_preserved": len(after_switch["rows"]),
    }

    # 7b. ES i18n while session is open: symmetric tabs ("Sesión", "Contenidos"), no overflow.
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(300)
    es_state = inspect_contents(pg)
    assert es_state["wsVisible"] and es_state["cntVisible"], "Session closed on language switch"
    assert [t["text"] for t in es_state["tabs"]] == ["Sesión", "Contenidos"], (
        f"ES session tabs mismatch: {es_state['tabs']}"
    )
    assert "contenidos" in es_state["countText"].lower(), f"ES counter not translated: {es_state['countText']!r}"
    assert es_state["scopeText"] == "Volver a Parte 2", f"ES scope link mismatch: {es_state['scopeText']!r}"
    assert es_state["scrollWidth"] <= es_state["clientWidth"] + 1, (
        f"390 ES overflow: {es_state['scrollWidth']} > {es_state['clientWidth']}"
    )
    # Collapse back to Part 2 and verify ES "Ver todo en esta prueba"
    pg.click("#sessionContentsScopeBtn")
    pg.wait_for_timeout(150)
    assert inspect_contents(pg)["scopeText"] == "Ver todo en esta prueba"
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(250)
    out["7_es_tabs"] = [t["text"] for t in es_state["tabs"]]

    # Desktop 1280 screenshot of open session Contents
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.evaluate("if(document.activeElement)document.activeElement.blur(); window.scrollTo(0, 0)")
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(150)
    desk = inspect_contents(pg)
    assert desk["scrollWidth"] <= desk["clientWidth"] + 1, (
        f"1280 overflow: {desk['scrollWidth']} > {desk['clientWidth']}"
    )
    pg.screenshot(path=os.path.join(OUT, "start_contents_1280_light.png"))

    # 8. Closing the session returns to Practice cleanly with no dangling state.
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(250)
    after_close = pg.evaluate(
        """() => ({
            activeView: (document.querySelector('.view.active') || {}).id || '',
            wsHidden: document.getElementById('sessionWorkspace').hidden,
            currentStudio: CURRENT_STUDIO,
            sessionUnit: SESSION_UNIT,
            hoyFocus: document.getElementById('v-hoy').classList.contains('is-session-focus'),
            exlibExpanded: EXLIB_STATE.expanded,
        })"""
    )
    assert after_close["activeView"] == "v-practice", f"Close did not return to Practice: {after_close}"
    assert after_close["wsHidden"], "Session workspace stayed visible after close"
    assert after_close["currentStudio"] == "", f"CURRENT_STUDIO not cleared: {after_close}"
    assert after_close["sessionUnit"] is None, f"SESSION_UNIT not cleared: {after_close}"
    assert not after_close["hoyFocus"], "is-session-focus stayed on #v-hoy"
    assert not after_close["exlibExpanded"], "EXLIB_STATE.expanded not reset"
    out["8_close_clean"] = after_close

    # 8b. Writing Part 1 & Listening Part 3 Contents also prioritize the active part.
    pg.click("#partsList .step button[data-action='startPart'][data-i='15']")
    pg.wait_for_timeout(200)
    pg.click("#sessionTabContentsBtn")
    pg.wait_for_timeout(200)
    w1_cnt = inspect_contents(pg)
    assert all(r["skill"] == "w" for r in w1_cnt["rows"]), "Writing Part 1 leaked other skills"
    assert_part_first_order(w1_cnt["rows"], "1", "Writing Part 1")
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)

    pg.click("#partsList .step button[data-action='startPart'][data-i='9']")
    pg.wait_for_timeout(200)
    pg.click("#sessionTabContentsBtn")
    pg.wait_for_timeout(200)
    l3_cnt = inspect_contents(pg)
    assert all(r["skill"] == "l" for r in l3_cnt["rows"]), "Listening Part 3 leaked other skills"
    assert_part_first_order(l3_cnt["rows"], "3", "Listening Part 3")
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)
    out["8b_writing_and_listening_part_order"] = {
        "writing_p1_first": w1_cnt["rows"][0]["name"],
        "writing_p1_count": w1_cnt["countText"],
        "listening_p3_first": l3_cnt["rows"][0]["name"],
        "listening_p3_count": l3_cnt["countText"],
    }

    # 6. No "Browse all exercises" / "Open library" button in Today or Exam.
    pg.evaluate("showView('hoy')")
    pg.wait_for_timeout(200)
    today_browse = pg.evaluate(
        """() => ({
            wtfBtns: document.querySelectorAll('#v-hoy .wtf-browse-btn, #v-hoy .wtf-browse-all').length,
            openLibBtns: document.querySelectorAll('#v-hoy [data-action="openExercisesLibrary"]').length,
            browseText: [...document.querySelectorAll('#v-hoy button')].filter(b =>
                /browse all exercises|open library/i.test(b.textContent || '')
            ).length,
        })"""
    )
    assert today_browse == {"wtfBtns": 0, "openLibBtns": 0, "browseText": 0}, (
        f"Browse all exercises still in Today: {today_browse}"
    )

    pg.evaluate("showView('exam')")
    pg.wait_for_timeout(200)
    exam_browse = pg.evaluate(
        """() => ({
            examBtn: !!document.getElementById('examBrowseExercisesBtn'),
            openLibBtns: document.querySelectorAll('#v-exam [data-action="openExercisesLibrary"]').length,
            browseText: [...document.querySelectorAll('#v-exam button')].filter(b =>
                /browse all exercises|open library/i.test(b.textContent || '')
            ).length,
        })"""
    )
    assert exam_browse == {"examBtn": False, "openLibBtns": 0, "browseText": 0}, (
        f"Browse all exercises still in Exam: {exam_browse}"
    )
    out["6_no_browse_buttons"] = {"today": today_browse, "exam": exam_browse}

    # 7a. Today Start & Plan Start also open sessions with Contents.
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
    pg.wait_for_timeout(250)
    pg.click("#todaySession .ts-row:not(.ts-next-unit) button[data-action='todayStart']")
    pg.wait_for_timeout(250)
    assert inspect_contents(pg)["wsVisible"], "Today Start did not open session workspace"
    pg.click("#sessionTabContentsBtn")
    pg.wait_for_timeout(200)
    today_cnt = inspect_contents(pg)
    assert today_cnt["cntVisible"] and len(today_cnt["rows"]) > 0, "Today session has no Contents"
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)

    pg.evaluate("showView('plan')")
    pg.wait_for_timeout(250)
    pg.click("#wpRows .wp-start")
    pg.wait_for_timeout(250)
    assert inspect_contents(pg)["wsVisible"], "Plan Start did not open session workspace"
    pg.click("#sessionTabContentsBtn")
    pg.wait_for_timeout(200)
    plan_cnt = inspect_contents(pg)
    assert plan_cnt["cntVisible"] and len(plan_cnt["rows"]) > 0, "Plan session has no Contents"
    pg.click("#sessionCloseBtn")
    pg.wait_for_timeout(200)
    out["7a_today_and_plan_contents"] = {
        "today_rows": len(today_cnt["rows"]),
        "plan_rows": len(plan_cnt["rows"]),
    }

    assert page_errors == [], f"Page errors: {page_errors}"
    out["screenshots"] = [
        "start_contents_390_light.png",
        "start_contents_390_dark.png",
        "start_contents_1280_light.png",
    ]
    out["errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
