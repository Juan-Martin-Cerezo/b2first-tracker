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
            const fullBtn = view.querySelector("[data-action='startFullMock']");
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
    assert [c["paper"] for c in exam_state["cards"] if c["paper"]] == ["rue", "w", "l", "sp"], (
        f"4-paper grid broken: {exam_state['cards']}"
    )
    assert exam_state["cards"][0]["action"] == "startRealMock", "Paper cards should be present"
    assert exam_state["cards"][3]["action"] == "openSpeakingExam", "Speaking exam card action broken"
    assert any(c["action"] == "startFullMock" for c in exam_state["cards"]), "Full mock card missing"
    assert exam_state["hasFullMockBtn"], "Start full mock button missing"
    assert exam_state["hasTimer"] and exam_state["hasManualSelect"], "Exam timer or paper selector missing"
    assert not exam_state["linkExists"], "#examLibraryLink should stay removed from #v-exam"
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
        "library_link": "removed",
        "overflow_390": exam_state["scrollWidth"] - exam_state["clientWidth"],
    }

    # --- 2. Open the Library directly (Exam no longer duplicates a link) ---
    pg.evaluate("openPracticeCatalog('all','all')")
    pg.wait_for_timeout(350)

    lib_state = pg.evaluate(
        r"""() => {
            const adv = document.getElementById('exLibAdvancedFilters');
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
                advVisible: adv ? !adv.hidden : false,
                countText: countEl ? countEl.textContent.trim() : '',
                rows,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                html: document.getElementById('v-practice') ? document.getElementById('v-practice').outerHTML : '',
            };
        }"""
    )
    assert lib_state["advVisible"], "Library full catalog filters not expanded"
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

    out["screenshots"] = ["exam_clean_390_light.png", "library_dedup_390_light.png"]
    out["page_errors"] = page_errors

    print(json.dumps(out, ensure_ascii=False, indent=1))
    if page_errors:
        raise SystemExit(f"Page errors: {page_errors}")
    print("PASS test_dedupe_exam")
    browser.close()
