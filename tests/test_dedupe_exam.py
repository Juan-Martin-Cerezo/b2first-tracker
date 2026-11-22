"""Phase dedupe-exam acceptance: Exam simulates, Library catalogues without duplicates.

Verifies:
  1. #v-exam has no #examMaterialsCard, no wtfSectionExam*/exMat*, no
     .u4-exam-sources / #examSources / #examSourcesSearch; keeps the 4-paper
     grid, "Start full mock", Speaking exam entry, timer and exam countdown.
  2. #v-exam has a single discreet link ("Papers, keys and practice links live
     in Library") that opens Practice -> Library (Contents expanded, all papers).
  3. Library has zero duplicate rows by normalized URL or normalized name+part;
     #exLibCount matches the exact rendered row count; deduplication prioritizes
     local files over Reference/online duplicates while keeping unique Reference
     items intact.
  4. In Today, each skill's Materials panel shows only unit-contextual local
     materials and part-specific online links (never general part:[] sources or
     the full 74-source list), plus a "More in Library" link that opens Library.
  5. 390x844 light (and dark) without horizontal overflow, >=44px targets,
     symmetric EN/ES copy, zero inline on* handlers, zero page errors.

Saves screenshots in tests/out/:
  exam_clean_390_light.png, library_dedup_390_light.png.
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


def norm_url(u):
    s = (u or "").strip().split("#", 1)[0].rstrip("/").lower()
    return s


def norm_name(n):
    return re.sub(r"\s+", " ", re.sub(r"[—–-]+", " ", (n or "").lower())).strip()


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

    # Load real local material index from /libros.json
    pg.evaluate("loadMaterial()")
    pg.wait_for_function("Object.keys(MAT).length > 0", timeout=8000)
    pg.wait_for_timeout(200)

    # Set an exam date so countdown is active and verifiable too
    pg.evaluate(
        """() => {
            const d = new Date(Date.now() + 45 * 86400 * 1000);
            const iso = d.toISOString().slice(0, 10);
            D.examDates = [iso];
            if (D.profile) D.profile.examDate = iso;
            save();
            refreshAll();
            renderExamCountdown();
        }"""
    )
    pg.wait_for_timeout(200)

    # --- 1. Exam is clean simulation only -----------------------------------
    pg.click("nav button[data-view='exam']")
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light'); window.scrollTo(0, 0)")
    pg.wait_for_timeout(250)

    exam_state = pg.evaluate(
        r"""() => {
            const view = document.getElementById('v-exam');
            const link = document.getElementById('examLibraryLink');
            const lr = link ? link.getBoundingClientRect() : null;
            const cards = [...view.querySelectorAll('#examSelectGrid .exam-card')].map(c => ({
                paper: c.dataset.paper || '',
                action: c.dataset.action || '',
            }));
            const fullBtn = view.querySelector("button[data-action='startFullMock']");
            const timer = document.getElementById('exTimer');
            const manual = document.getElementById('exPaper');
            return {
                active: view.classList.contains('active'),
                hasMaterialsCard: !!document.getElementById('examMaterialsCard'),
                examWtfSections: view.querySelectorAll('[id^="wtfSectionExam"], #exMatRue, #exMatW, #exMatL, #exMatSp').length,
                hasExamSourcesCard: !!view.querySelector('.u4-exam-sources'),
                hasExamSourcesList: !!document.getElementById('examSources'),
                hasExamSourcesSearch: !!document.getElementById('examSourcesSearch'),
                searchInputsInExam: view.querySelectorAll('input[type="search"]').length,
                cards,
                hasFullMockBtn: !!fullBtn,
                fullMockText: fullBtn ? fullBtn.textContent.trim() : '',
                hasTimer: !!timer && timer.textContent.trim().length > 0,
                timerText: timer ? timer.textContent.trim() : '',
                hasManualSelect: !!manual,
                countdownText: (document.getElementById('examCountdown') || {}).textContent || '',
                linkExists: !!link,
                linkText: link ? link.textContent.trim() : '',
                linkH: lr ? Math.round(lr.height) : 0,
                linkRight: lr ? Math.round(lr.right) : 0,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                html: view.outerHTML,
            };
        }"""
    )
    assert exam_state["active"], "#v-exam is not active"
    assert not exam_state["hasMaterialsCard"], "#examMaterialsCard still exists in #v-exam"
    assert exam_state["examWtfSections"] == 0, f"wtfSectionExam*/exMat* still exist: {exam_state['examWtfSections']}"
    assert not exam_state["hasExamSourcesCard"], ".u4-exam-sources still exists in #v-exam"
    assert not exam_state["hasExamSourcesList"], "#examSources still exists in #v-exam"
    assert not exam_state["hasExamSourcesSearch"], "#examSourcesSearch still exists in #v-exam"
    assert exam_state["searchInputsInExam"] == 0, f"Unexpected search inputs in Exam: {exam_state['searchInputsInExam']}"
    assert [c["paper"] for c in exam_state["cards"]] == ["rue", "w", "l", "sp"], (
        f"4-paper grid broken: {exam_state['cards']}"
    )
    assert exam_state["cards"][3]["action"] == "openSpeakingExam", "Speaking exam card action broken"
    assert exam_state["hasFullMockBtn"], "Start full mock button missing"
    assert exam_state["hasTimer"] and exam_state["hasManualSelect"], "Exam timer or paper selector missing"
    assert exam_state["linkExists"], "#examLibraryLink missing in #v-exam"
    assert exam_state["linkText"] == "Papers, keys and practice links live in Library", (
        f"Unexpected Exam Library link copy: {exam_state['linkText']!r}"
    )
    assert exam_state["linkH"] >= 44, f"#examLibraryLink height {exam_state['linkH']} < 44px"
    assert exam_state["linkRight"] <= exam_state["clientWidth"] + 1, "Exam Library link overflows viewport"
    assert exam_state["scrollWidth"] <= exam_state["clientWidth"] + 1, (
        f"Exam 390 light overflow: {exam_state['scrollWidth']} > {exam_state['clientWidth']}"
    )
    assert not INLINE_HANDLER_RE.search(exam_state["html"]), "Inline on* handler found in #v-exam"

    pg.evaluate("if(document.activeElement)document.activeElement.blur(); window.scrollTo(0, 0)")
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "exam_clean_390_light.png"))
    out["1_exam_clean"] = {
        "papers": [c["paper"] for c in exam_state["cards"]],
        "timer": exam_state["timerText"],
        "library_link": exam_state["linkText"],
        "overflow_390": exam_state["scrollWidth"] - exam_state["clientWidth"],
    }

    # Verify Spanish translation of Exam link & zero overflow
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    exam_es = pg.evaluate(
        """() => ({
            linkText: (document.getElementById('examLibraryLink') || {}).textContent.trim(),
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
        })"""
    )
    assert exam_es["linkText"] and exam_es["linkText"] != exam_state["linkText"], (
        f"Exam Library link not translated in ES: {exam_es['linkText']!r}"
    )
    assert "Biblioteca" in exam_es["linkText"], f"ES Exam link missing Biblioteca: {exam_es['linkText']!r}"
    assert exam_es["scrollWidth"] <= exam_es["clientWidth"] + 1, "Exam 390 ES overflow"
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)

    # --- 2. Clicking Exam's Library link opens Practice -> Library ----------
    pg.click("#examLibraryLink")
    pg.wait_for_timeout(300)

    lib_state = pg.evaluate(
        r"""() => {
            const ws = document.getElementById('sessionWorkspace');
            const cnt = document.getElementById('sessionTabContents');
            const adv = document.getElementById('exLibAdvancedFilters');
            const navPractice = document.querySelector("nav button[data-view='practice']");
            const countEl = document.getElementById('exLibCount');
            const rows = [...document.querySelectorAll('#exLibList a.exlib-row')].map(a => ({
                href: a.getAttribute('href') || '',
                name: a.dataset.name || '',
                skill: a.dataset.skill || '',
                origin: a.dataset.origin || '',
                type: a.dataset.type || '',
                parts: (a.dataset.parts || '').split(',').filter(Boolean).sort().join(','),
            }));
            return {
                wsVisible: ws ? !ws.hidden : false,
                cntVisible: cnt ? !cnt.hidden : false,
                advVisible: adv ? !adv.hidden : false,
                practiceNavActive: navPractice ? navPractice.classList.contains('active') : false,
                paperState: EXLIB_STATE.paper,
                countText: countEl ? countEl.textContent.trim() : '',
                rows,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                html: ws ? ws.outerHTML : '',
            };
        }"""
    )
    assert lib_state["wsVisible"] and lib_state["cntVisible"], "Exam link did not open Library Contents"
    assert lib_state["advVisible"], "Library full catalog filters not expanded"
    assert lib_state["practiceNavActive"], "Practice nav item not active after opening Library from Exam"
    assert lib_state["paperState"] == "all", f"Expected paper='all', got {lib_state['paperState']!r}"
    assert len(lib_state["rows"]) > 70, f"Expected full catalog rows, got {len(lib_state['rows'])}"
    assert lib_state["scrollWidth"] <= lib_state["clientWidth"] + 1, (
        f"Library 390 light overflow: {lib_state['scrollWidth']} > {lib_state['clientWidth']}"
    )
    assert not INLINE_HANDLER_RE.search(lib_state["html"]), "Inline on* handler found in Library"

    # --- 3. Library deduplication & exact counter ---------------------------
    seen_urls = {}
    seen_name_part = {}
    dup_urls = []
    dup_name_parts = []
    for r in lib_state["rows"]:
        u = norm_url(r["href"])
        np_key = f"{norm_name(r['name'])}|{r['parts']}"
        if u in seen_urls:
            dup_urls.append((u, seen_urls[u], r["name"]))
        else:
            seen_urls[u] = r["name"]
        if np_key in seen_name_part:
            dup_name_parts.append((np_key, seen_name_part[np_key], r["href"]))
        else:
            seen_name_part[np_key] = r["href"]

    assert not dup_urls, f"Duplicate URLs rendered in Library: {dup_urls}"
    assert not dup_name_parts, f"Duplicate name+part rendered in Library: {dup_name_parts}"
    expected_count = f"{len(lib_state['rows'])} contents"
    assert lib_state["countText"] == expected_count, (
        f"Counter mismatch: {lib_state['countText']!r} != {expected_count!r}"
    )

    # Also verify deduplication priority: local file wins over duplicate Reference/online
    prio_check = pg.evaluate(
        """() => {
            const sample = [
                {id:'ref_dup_url', n:'Ref duplicate paper', skill:'ref', type:'reference', part:[], mins:75, origin:'online', kind:'free', href:'https://example.org/test-paper', what:''},
                {id:'ref_dup_local', n:'B2 First Sample 1 — Reading & Use of English', skill:'ref', type:'reference', part:[], mins:75, origin:'online', kind:'free', href:'https://example.org/sample-1', what:''},
                {id:'loc_paper', n:'B2 First Sample 1 — Reading & Use of English', skill:'rue', type:'paper', part:[], mins:75, origin:'local', kind:'free', href:'/files/sample-1.pdf', what:''},
                {id:'loc_same_url', n:'Local paper same URL', skill:'rue', type:'paper', part:[], mins:75, origin:'local', kind:'free', href:'https://example.org/test-paper/', what:''},
                {id:'ref_unique', n:'Unique Reference Book', skill:'ref', type:'reference', part:[], mins:30, origin:'local', kind:'free', href:'/files/unique-handbook.pdf', what:''},
            ];
            const res = dedupeExerciseLibrary(sample);
            return res.map(x => ({id: x.id, origin: x.origin, skill: x.skill}));
        }"""
    )
    kept_ids = [x["id"] for x in prio_check]
    assert "loc_paper" in kept_ids and "ref_dup_local" not in kept_ids, f"Local did not win over name-dup Reference: {prio_check}"
    assert "loc_same_url" in kept_ids and "ref_dup_url" not in kept_ids, f"Local did not win over URL-dup Reference: {prio_check}"
    assert "ref_unique" in kept_ids, f"Unique Reference item was dropped: {prio_check}"

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light'); if(document.activeElement)document.activeElement.blur(); window.scrollTo(0, 0)")
    pg.mouse.move(0, 0)
    pg.wait_for_timeout(150)
    pg.screenshot(path=os.path.join(OUT, "library_dedup_390_light.png"))

    out["2_3_library_dedup"] = {
        "rows": len(lib_state["rows"]),
        "countText": lib_state["countText"],
        "dup_urls": len(dup_urls),
        "dup_name_parts": len(dup_name_parts),
        "ref_rows": sum(1 for r in lib_state["rows"] if r["skill"] == "ref"),
        "prio_kept": kept_ids,
    }

    # --- 4. Today Materials panels: unit-only + part-specific online + "More in Library" ---
    pg.evaluate("closeSessionStudios(); showView('hoy')")
    pg.wait_for_timeout(200)

    # Check all 4 skills in Today studios
    general_online_urls = set(
        pg.evaluate(
            """() => PRACTICE_SOURCES
                .filter(s => !Array.isArray(s.part) || s.part.length === 0)
                .map(s => s.url.replace(/\\/+$/, '').toLowerCase())"""
        )
    )
    today_panels = {}
    for skill, studio_key, panel_id, chips_id, setup_js in [
        ("rue", "mon-a", "wtfPanelRue", "gUeChips", "document.getElementById('uePart').value='2';"),
        ("w", "mon-b", "wtfPanelW", "gWChips", "document.getElementById('wTipo').value='Essay';"),
        ("l", "fri-a", "wtfPanelL", "gLChips", "document.getElementById('lPart').value='2';"),
        ("sp", "fri-b", "wtfPanelSp", "gSpChips", "if(typeof SP_TODAY!=='undefined'){SP_TODAY.mode='part';SP_TODAY.part=2;}"),
    ]:
        pg.evaluate(
            f"""() => {{
                showView('hoy');
                selectSessionStudio('{studio_key}');
                {setup_js}
                renderGuides();
                setWtfOpen('{skill}', true);
            }}"""
        )
        pg.wait_for_timeout(180)
        panel_info = pg.evaluate(
            """([panelId, chipsId]) => {
                const panel = document.getElementById(panelId);
                const chips = document.getElementById(chipsId);
                const extLinks = [...chips.querySelectorAll('a[href^="http"]')].map(a => ({
                    text: a.textContent.trim(),
                    href: a.getAttribute('href') || '',
                    parts: (a.dataset.parts || '').split(',').filter(Boolean),
                }));
                const localLinks = [...chips.querySelectorAll('a[href^="/files/"]')].length;
                const moreBtn = panel.querySelector('button.wtf-more-lib');
                const mr = moreBtn ? moreBtn.getBoundingClientRect() : null;
                return {
                    panelVisible: panel ? !panel.hidden : false,
                    localLinks,
                    extLinks,
                    moreExists: !!moreBtn,
                    moreText: moreBtn ? moreBtn.textContent.trim() : '',
                    moreH: mr ? Math.round(mr.height) : 0,
                    scrollWidth: document.documentElement.scrollWidth,
                    clientWidth: document.documentElement.clientWidth,
                };
            }""",
            [panel_id, chips_id],
        )
        assert panel_info["panelVisible"], f"Today {skill} Materials panel not visible"
        assert panel_info["localLinks"] >= 1, f"Today {skill} missing local unit materials"
        assert 1 <= len(panel_info["extLinks"]) <= 3, (
            f"Today {skill} should have 1-3 part-specific online links, got {len(panel_info['extLinks'])}: {panel_info['extLinks']}"
        )
        for lnk in panel_info["extLinks"]:
            assert norm_url(lnk["href"]) not in general_online_urls, (
                f"Today {skill} leaked general (part:[]) online source: {lnk}"
            )
            assert lnk["parts"], f"Today {skill} online link missing part scope: {lnk}"
        assert panel_info["moreExists"], f"Today {skill} missing 'More in Library' button"
        assert panel_info["moreText"] == "More in Library", (
            f"Today {skill} bad link text: {panel_info['moreText']!r}"
        )
        assert panel_info["moreH"] >= 44, f"Today {skill} More in Library height {panel_info['moreH']} < 44px"
        assert panel_info["scrollWidth"] <= panel_info["clientWidth"] + 1, (
            f"Today {skill} 390 overflow: {panel_info['scrollWidth']} > {panel_info['clientWidth']}"
        )
        today_panels[skill] = {
            "local": panel_info["localLinks"],
            "online": len(panel_info["extLinks"]),
            "more": panel_info["moreText"],
        }

    # Spanish translation of "More in Library"
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    more_es = pg.evaluate("document.querySelector('#wtfPanelSp button.wtf-more-lib').textContent.trim()")
    assert more_es == "Más en Biblioteca", f"ES 'More in Library' mismatch: {more_es!r}"
    pg.evaluate("setLang('en'); showView('hoy'); selectSessionStudio('fri-b'); renderGuides(); setWtfOpen('sp', true);")
    pg.wait_for_timeout(200)

    # Clicking "More in Library" opens Library filtered to that paper (expanded)
    pg.click("#wtfPanelSp button.wtf-more-lib")
    pg.wait_for_timeout(250)
    from_today = pg.evaluate(
        """() => ({
            cntVisible: !document.getElementById('sessionTabContents').hidden,
            advVisible: !document.getElementById('exLibAdvancedFilters').hidden,
            paper: EXLIB_STATE.paper,
            rows: document.querySelectorAll('#exLibList a.exlib-row').length,
        })"""
    )
    assert from_today["cntVisible"] and from_today["advVisible"], f"More in Library did not open Library: {from_today}"
    assert from_today["paper"] == "sp" and from_today["rows"] > 0, f"Unexpected paper/rows from Today Sp: {from_today}"

    out["4_today_materials"] = today_panels
    out["4_more_in_library_es"] = more_es
    out["4_from_today_sp"] = from_today

    assert page_errors == [], f"Page errors: {page_errors}"
    out["screenshots"] = ["exam_clean_390_light.png", "library_dedup_390_light.png"]
    out["page_errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
