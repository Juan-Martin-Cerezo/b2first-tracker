"""Today compact collapsible resources (fase today-compact).

Verifies Today's 4 "Where to find / Materials" sections across mobile (390x844)
and desktop (1280x800), light & dark themes, EN & ES:
  1. Collapsed by default: section height <= 64px, aria-expanded="false", panel hidden.
  2. Expanded: all rows render; every standard compact row is 40..64px tall,
     single-line truncated hint with full `title`, links >= 44px, caret not position:absolute.
  3. 390x844: expanded panel height well below previous layout baseline
     (< PREV / 1.6 and < 1.6 * PREV) and zero horizontal overflow; 1280x800 uses 2-col grid.
  4. Open/closed state persists in localStorage per skill (b2f_wtf_open_<skill>) across reload.
  5. Deep links intact: R&UoE S1 points to its sample paper PDF, per-part lesson plan points
     to part-1, Full paper points to the full test (never a single part).
  6. EN/ES summary copy: "Materials · N resources" / "Materiales · N recursos".

Saves screenshots in tests/out/:
  today_compact_390_light_closed.png
  today_compact_390_light_open.png
  today_compact_390_dark_closed.png
  today_compact_390_dark_open.png
  today_compact_1280_light_open.png
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# Documented 390x844 expanded list heights measured on HEAD (commit 9a7521a,
# before today-compact) with the same STUB_MAT catalogue and part selections:
#   rue (part 1, 8 blocks): 1099px  |  w (Essay, 11 blocks): 1455px
#   l (part 1, 5 blocks):   1161px  |  sp (part 2, 10 blocks): 1626px
PREV_LIST_HEIGHTS_390 = {
    "rue": 1099,
    "w": 1455,
    "l": 1161,
    "sp": 1626,
}

STUB_MAT = {
    "rueS1": "/files/01-Examen-Completo-01/B2-First-sample-paper-1-RUE-2022.pdf",
    "rueS2": "/files/02-Examen-Completo-02/B2-First-sample-paper-2-RUE-2022.pdf",
    "rueFS1": "/files/03-Examen-Completo-For-Schools-01/B2-First-FS-sample-paper-1-RUE-2022.pdf",
    "rueFS2": "/files/04-Examen-Completo-For-Schools-02/FS-sample-paper-2-RUE.pdf",
    "keyS1": "/files/01-Examen-Completo-01/B2-First-RUE-Sample-1-Answer-Key-2022.pdf",
    "keyS2": "/files/02-Examen-Completo-02/sample-paper-2-answer-keys.pdf",
    "keyFS1": "/files/03-Examen-Completo-For-Schools-01/FS-RUE-Sample-1-Answer-Key-2022.pdf",
    "keyFS2": "/files/04-Examen-Completo-For-Schools-02/FS-Answer-key-sample-paper-2.pdf",
    **{f"lpR{n}": f"/files/10-Lesson-Plans/B2-First/reading-part-{n}.pdf" for n in range(1, 8)},
    **{f"fR{n}": f"/files/10-Lesson-Plans/B2-First-For-Schools/reading-part-{n}.pdf" for n in range(1, 8)},
    "rAct1": "/files/07-Reading/self-study-reading-activities-1.pdf",
    "rAct1b": "/files/07-Reading/self-study-reading-activities-part-1.pdf",
    "rAct2": "/files/07-Reading/self-study-further-reading-activities.pdf",
    "rGuide": "/files/07-Reading/developing-reading-skills-guide.pdf",
    "wS1": "/files/01-Examen-Completo-01/B2-First-sample-paper-1-Writing-2022.pdf",
    "wS2": "/files/02-Examen-Completo-02/B2-First-sample-paper-2-Writing-2022.pdf",
    "wFS1": "/files/03-Examen-Completo-For-Schools-01/B2-First-FS-sample-paper-1-Writing-2022.pdf",
    "wFS2": "/files/04-Examen-Completo-For-Schools-02/FS-Writing-sample-paper-2.pdf",
    "lpW1": "/files/10-Lesson-Plans/B2-First/writing-part-1.pdf",
    "lpW2": "/files/10-Lesson-Plans/B2-First/writing-part-2.pdf",
    "fW1": "/files/10-Lesson-Plans/B2-First-For-Schools/writing-part-1.pdf",
    "fW2": "/files/10-Lesson-Plans/B2-First-For-Schools/writing-part-2.pdf",
    "wAct1": "/files/06-Writing/self-study-writing-activities-part-1.pdf",
    "wAct2": "/files/06-Writing/self-study-further-writing-activities-part-2.pdf",
    "wCheck": "/files/06-Writing/checklist-to-improve-your-writing.pdf",
    "wGuide": "/files/06-Writing/teacher-guide-for-writing.pdf",
    "lS1": "/files/01-Examen-Completo-01/B2-First-sample-paper-1-Listening-2022.pdf",
    "auS1": "/files/01-Examen-Completo-01/sample-paper-1-listening-audio-file.mp3",
    "tsS1": "/files/01-Examen-Completo-01/B2-First-Listening-Sample-1-Tapescript-2022.pdf",
    "lkS1": "/files/01-Examen-Completo-01/B2-First-Listening-Sample-1-Answer-Key-2022.pdf",
    "lS2": "/files/02-Examen-Completo-02/B2-First-sample-paper-2-Listening-2022.pdf",
    "lkS2": "/files/02-Examen-Completo-02/sample-paper-2-answer-keys.pdf",
    **{f"auS2p{n}": f"/files/02-Examen-Completo-02/listening-audio-part-{n}.mp3" for n in range(1, 5)},
    **{f"lpL{n}": f"/files/10-Lesson-Plans/B2-First/listening-part-{n}.pdf" for n in range(1, 5)},
    "lFS1": "/files/03-Examen-Completo-For-Schools-01/FS-sample-paper-1-Listening-2022.pdf",
    "tsFS1": "/files/03-Examen-Completo-For-Schools-01/FS-Listening-Sample-1-Tapescript-2022.pdf",
    "lkFS1": "/files/03-Examen-Completo-For-Schools-01/FS-Listening-Sample-1-Answer-Key-2022.pdf",
    **{f"auFS1p{n}": f"/files/03-Examen-Completo-For-Schools-01/listening-audio-{n}.mp3" for n in range(1, 5)},
    "lFS2": "/files/04-Examen-Completo-For-Schools-02/FS-Listening-sample-paper-2-full-test.pdf",
    "auFS2": "/files/04-Examen-Completo-For-Schools-02/FS-Listening-audio-full-test-2.mp3",
    "lkFS2": "/files/04-Examen-Completo-For-Schools-02/FS-Answer-key-sample-paper-2.pdf",
    "hb": "/files/05-Handbooks/b2-first-handbook.pdf",
    "hbFS": "/files/05-Handbooks/b2-first-for-schools-handbook.pdf",
    "hbA1": "/files/09-Listening/handbook-first-audio/sample-1.mp3",
    "hbFS2": "/files/09-Listening/handbook-for-schools-audio/sample-test-2.mp3",
    **{f"hbA2p{n}": f"/files/09-Listening/handbook-first-audio/sample-2-part-{n}.mp3" for n in range(1, 5)},
    **{f"hbFSp{n}": f"/files/09-Listening/handbook-for-schools-audio/part-{n}.mp3" for n in range(1, 5)},
    "lGuide": "/files/09-Listening/teacher-guide-for-listening.pdf",
    "spS1": "/files/01-Examen-Completo-01/sample-paper-1-speaking.pdf",
    "spS2": "/files/02-Examen-Completo-02/sample-paper-2-speaking.pdf",
    "spFS1": "/files/03-Examen-Completo-For-Schools-01/FS-sample-paper-1-speaking.pdf",
    "spFS2": "/files/04-Examen-Completo-For-Schools-02/FS-Speaking-sample-paper-2.pdf",
    **{f"exC{i}": f"/files/08-Speaking/examiner-comments-{i + 1}.pdf" for i in range(6)},
    **{f"lpSp{n}": f"/files/10-Lesson-Plans/B2-First/speaking-part-{n}.pdf" for n in range(1, 5)},
    **{f"fSp{n}": f"/files/10-Lesson-Plans/B2-First-For-Schools/speaking-part-{n}.pdf" for n in range(1, 5)},
    "spAct": "/files/08-Speaking/self-study-speaking-activities-part-1.pdf",
    "spGuide": "/files/08-Speaking/teacher-guide-for-speaking.pdf",
}

SECTIONS = [
    ("rue", "mon-a", "studioMonA", "wtfSectionRue", "gUeChips", 8),
    ("w", "mon-b", "studioMonB", "wtfSectionW", "gWChips", 11),
    ("l", "fri-a", "studioFriA", "wtfSectionL", "gLChips", 5),
    ("sp", "fri-b", "studioFriB", "wtfSectionSp", "gSpChips", 10),
]


def seed_catalog(pg, lang="en"):
    pg.evaluate(
        """([mat, lang]) => {
            setLang(lang);
            MAT = Object.assign({}, mat);
            document.getElementById('uePart').value = '1';
            document.getElementById('wTipo').value = 'Essay';
            document.getElementById('lPart').value = '1';
            if (typeof SP_TODAY !== 'undefined') {
                SP_TODAY.mode = 'part';
                SP_TODAY.part = 2;
            }
            renderGuides();
        }""",
        [STUB_MAT, lang],
    )
    pg.wait_for_timeout(180)


def show_studio(pg, studio_key, card_id):
    pg.evaluate(
        """([studioKey, cardId]) => {
            showView('hoy');
            selectSessionStudio(studioKey);
            const card = document.getElementById(cardId);
            if (card) {
                let el = card;
                while (el && el !== document.body) {
                    if (getComputedStyle(el).display === 'none') el.style.display = 'block';
                    el = el.parentElement;
                }
            }
            renderGuides();
        }""",
        [studio_key, card_id],
    )
    pg.wait_for_timeout(140)


def inspect_compact(pg, sec_id, list_id):
    return pg.evaluate(
        """([secId, listId]) => {
            const sec = document.getElementById(secId);
            const list = document.getElementById(listId);
            if (!sec || !list) return null;
            const btn = sec.querySelector('.wtf-toggle');
            const summary = sec.querySelector('.wtf-toggle-summary');
            const caret = sec.querySelector('.wtf-caret');
            const panel = sec.querySelector('.wtf-panel');
            const secRect = sec.getBoundingClientRect();
            const btnRect = btn.getBoundingClientRect();
            const listRect = list.getBoundingClientRect();
            const panelRect = panel.getBoundingClientRect();
            const listCs = getComputedStyle(list);
            const caretCs = getComputedStyle(caret);
            const rows = [...list.querySelectorAll(':scope > .wtf-block')].map(b => {
                const r = b.getBoundingClientRect();
                const hint = b.querySelector('.wtf-hint');
                const hintCs = hint ? getComputedStyle(hint) : null;
                const links = [...b.querySelectorAll('a.wtf-link')].map(a => {
                    const ar = a.getBoundingClientRect();
                    return {
                        text: a.textContent.trim(),
                        href: a.getAttribute('href') || '',
                        w: Math.round(ar.width),
                        h: Math.round(ar.height),
                        right: Math.round(ar.right),
                    };
                });
                return {
                    kind: b.dataset.wtfKind || '',
                    hasExtra: b.classList.contains('wtf-has-extra'),
                    h: Math.round(r.height),
                    top: Math.round(r.top),
                    bottom: Math.round(r.bottom),
                    hintText: hint ? hint.textContent.trim() : '',
                    hintTitle: hint ? (hint.getAttribute('title') || '') : '',
                    hintFontSize: hintCs ? parseFloat(hintCs.fontSize) : 0,
                    hintOverflow: hintCs ? hintCs.textOverflow : '',
                    hintWhiteSpace: hintCs ? hintCs.whiteSpace : '',
                    links,
                };
            });
            return {
                expanded: btn.getAttribute('aria-expanded'),
                panelHidden: panel.hidden,
                summaryText: summary ? summary.textContent.trim() : '',
                sectionH: Math.round(secRect.height),
                toggleH: Math.round(btnRect.height),
                panelH: Math.round(panelRect.height),
                listH: Math.round(listRect.height),
                listDisplay: listCs.display,
                gridCols: listCs.gridTemplateColumns,
                caretPos: caretCs.position,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                rows,
            };
        }""",
        [sec_id, list_id],
    )


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.route("**/libros.json", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)

    # Clear any prior localStorage state for wtf sections
    pg.evaluate("""() => {
        ['rue', 'w', 'l', 'sp'].forEach(s => localStorage.removeItem('b2f_wtf_open_' + s));
    }""")
    seed_catalog(pg, "en")

    # 1. Closed by default: height <= 64px, aria-expanded="false", panel hidden, EN summary
    closed_heights = {}
    en_summaries = {}
    for skill, studio_key, card_id, sec_id, list_id, expected_n in SECTIONS:
        show_studio(pg, studio_key, card_id)
        st = inspect_compact(pg, sec_id, list_id)
        assert st is not None, f"{skill}: section missing"
        assert st["expanded"] == "false", f"{skill}: expected aria-expanded='false' by default, got {st['expanded']!r}"
        assert st["panelHidden"] is True, f"{skill}: panel should be hidden by default"
        assert st["sectionH"] <= 64, f"{skill}: closed height {st['sectionH']}px > 64px"
        assert st["toggleH"] >= 44, f"{skill}: toggle target height {st['toggleH']}px < 44px"
        assert st["caretPos"] != "absolute", f"{skill}: caret must not use position:absolute"
        assert st["summaryText"] == f"Materials · {expected_n} resources", (
            f"{skill}: unexpected EN summary {st['summaryText']!r}"
        )
        assert st["scrollWidth"] <= st["clientWidth"] + 1, f"{skill} closed: horizontal overflow"
        closed_heights[skill] = st["sectionH"]
        en_summaries[skill] = st["summaryText"]

    # Capture 390x844 light & dark CLOSED screenshots on R&UoE (shows Log Score CTA immediately!)
    show_studio(pg, "mon-a", "studioMonA")
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.locator("#studioMonA").scroll_into_view_if_needed()
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "today_compact_390_light_closed.png"))

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "today_compact_390_dark_closed.png"))
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(100)

    # 2 & 3. Expand each section on 390x844: row heights 40..64px, expanded height << prev, no overflow
    expanded_heights = {}
    expanded_row_heights = {}
    for skill, studio_key, card_id, sec_id, list_id, expected_n in SECTIONS:
        show_studio(pg, studio_key, card_id)
        pg.click(f"#{sec_id} .wtf-toggle")
        pg.wait_for_timeout(140)
        st = inspect_compact(pg, sec_id, list_id)
        assert st["expanded"] == "true", f"{skill}: expected aria-expanded='true' after click"
        assert st["panelHidden"] is False, f"{skill}: panel still hidden after click"
        assert len(st["rows"]) == expected_n, f"{skill}: expected {expected_n} rows, got {len(st['rows'])}"
        assert st["scrollWidth"] <= st["clientWidth"] + 1, (
            f"{skill} expanded (390): horizontal overflow {st['scrollWidth']} > {st['clientWidth']}"
        )

        # Height comparison vs documented previous layout baseline
        prev_h = PREV_LIST_HEIGHTS_390[skill]
        assert st["panelH"] < prev_h * 1.6, f"{skill}: expanded panel {st['panelH']} >= 1.6x prev ({prev_h})"
        assert st["listH"] * 1.6 < prev_h, (
            f"{skill}: expanded list {st['listH']}px not >=1.6x shorter than previous {prev_h}px"
        )
        expanded_heights[skill] = {"listH": st["listH"], "panelH": st["panelH"], "prevListH": prev_h}

        # Row heights, single-line ellipsis hint with full title, >=44px links
        row_hs = []
        for row in st["rows"]:
            row_hs.append(row["h"])
            if not row["hasExtra"]:
                assert 40 <= row["h"] <= 64, (
                    f"{skill}: standard row height {row['h']}px out of 40..64px range: {row}"
                )
            else:
                assert 40 <= row["h"] <= 145, f"{skill}: multi-line row unexpectedly tall ({row['h']}px): {row}"
            assert row["hintText"], f"{skill}: missing hint in row {row}"
            assert row["hintTitle"] == row["hintText"], f"{skill}: hint missing full title attribute: {row}"
            assert 13 <= row["hintFontSize"] <= 14.5, f"{skill}: hint font-size {row['hintFontSize']}px not 13-14px"
            assert row["hintOverflow"] == "ellipsis" and row["hintWhiteSpace"] == "nowrap", (
                f"{skill}: hint not single-line ellipsis: {row}"
            )
            for lnk in row["links"]:
                assert lnk["h"] >= 44, f"{skill}: link {lnk['text']!r} height {lnk['h']} < 44px"
                assert lnk["w"] >= 44, f"{skill}: link {lnk['text']!r} width {lnk['w']} < 44px"
                assert lnk["right"] <= st["clientWidth"] + 1, f"{skill}: link overflows right: {lnk}"
        expanded_row_heights[skill] = row_hs

    # Capture 390x844 light & dark OPEN screenshots on R&UoE
    show_studio(pg, "mon-a", "studioMonA")
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.locator("#wtfSectionRue").scroll_into_view_if_needed()
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "today_compact_390_light_open.png"))

    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "today_compact_390_dark_open.png"))
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(100)

    # 5. Deep links intact: R&UoE S1 -> sample-paper-1-RUE pdf; Lesson P1 -> part-1; Full paper -> full test
    rue_st = inspect_compact(pg, "wtfSectionRue", "gUeChips")
    s1_row = [r for r in rue_st["rows"] if any(l["text"] == "R&UoE S1" for l in r["links"])]
    assert len(s1_row) == 1, f"R&UoE S1 row missing: {rue_st['rows']}"
    s1_href = [l["href"] for l in s1_row[0]["links"] if l["text"] == "R&UoE S1"][0]
    assert "sample-paper-1-RUE" in s1_href and s1_href.endswith(".pdf"), f"bad R&UoE S1 href: {s1_href}"
    assert any(l["text"] == "Keys S1" and "Answer-Key" in l["href"] for l in s1_row[0]["links"]), (
        f"R&UoE S1 missing paired Keys S1: {s1_row[0]['links']}"
    )
    p1_row = [r for r in rue_st["rows"] if any(l["text"] == "Lesson plan P1" for l in r["links"])]
    assert p1_row and "part-1" in p1_row[0]["links"][0]["href"], f"R&UoE Lesson P1 deep link broken: {p1_row}"
    full_row = [r for r in rue_st["rows"] if r["kind"] == "full"][0]
    full_hrefs = [l["href"] for l in full_row["links"]]
    assert any("sample-paper-1-RUE" in h for h in full_hrefs), f"Full paper missing full test PDF: {full_hrefs}"
    assert not any("part-1" in h or "lpR" in h for h in full_hrefs), f"Full paper points to single part: {full_hrefs}"

    # 4. Persistence in localStorage across reload:
    # Keep only R&UoE open, collapse w/l/sp, reload, verify R&UoE stays open & others closed.
    for skill, studio_key, card_id, sec_id, list_id, _ in SECTIONS:
        if skill != "rue":
            show_studio(pg, studio_key, card_id)
            pg.click(f"#{sec_id} .wtf-toggle")
            pg.wait_for_timeout(80)
    ls_before = pg.evaluate("""() => ({
        rue: localStorage.getItem('b2f_wtf_open_rue'),
        w: localStorage.getItem('b2f_wtf_open_w'),
        l: localStorage.getItem('b2f_wtf_open_l'),
        sp: localStorage.getItem('b2f_wtf_open_sp'),
    })""")
    assert ls_before == {"rue": "1", "w": "0", "l": "0", "sp": "0"}, f"unexpected localStorage: {ls_before}"

    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(300)
    seed_catalog(pg, "en")
    show_studio(pg, "mon-a", "studioMonA")
    assert inspect_compact(pg, "wtfSectionRue", "gUeChips")["expanded"] == "true", "R&UoE did not stay open after reload"
    show_studio(pg, "mon-b", "studioMonB")
    assert inspect_compact(pg, "wtfSectionW", "gWChips")["expanded"] == "false", "Writing did not stay closed after reload"

    # Collapse R&UoE, reload, verify it stays closed
    show_studio(pg, "mon-a", "studioMonA")
    pg.click("#wtfSectionRue .wtf-toggle")
    pg.wait_for_timeout(100)
    assert pg.evaluate("localStorage.getItem('b2f_wtf_open_rue')") == "0"
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(300)
    seed_catalog(pg, "en")
    show_studio(pg, "mon-a", "studioMonA")
    assert inspect_compact(pg, "wtfSectionRue", "gUeChips")["expanded"] == "false", "R&UoE did not stay closed after reload"

    # 6. ES i18n check: "Materiales · N recursos"
    seed_catalog(pg, "es")
    es_summaries = {}
    for skill, studio_key, card_id, sec_id, list_id, expected_n in SECTIONS:
        show_studio(pg, studio_key, card_id)
        st = inspect_compact(pg, sec_id, list_id)
        assert st["summaryText"] == f"Materiales · {expected_n} recursos", (
            f"{skill}: unexpected ES summary {st['summaryText']!r}"
        )
        es_summaries[skill] = st["summaryText"]

    # Desktop 1280x800: 2-column grid for paper rows, Full paper & Online full-width, zero overflow
    pg.set_viewport_size({"width": 1280, "height": 800})
    seed_catalog(pg, "en")
    show_studio(pg, "mon-a", "studioMonA")
    pg.click("#wtfSectionRue .wtf-toggle")
    pg.wait_for_timeout(150)
    desk = inspect_compact(pg, "wtfSectionRue", "gUeChips")
    assert desk["listDisplay"] == "grid", f"1280 desktop list not grid: {desk['listDisplay']}"
    assert len(re.findall(r"\d+(?:\.\d+)?px", desk["gridCols"])) == 2, f"1280 desktop not 2 columns: {desk['gridCols']}"
    assert desk["scrollWidth"] <= desk["clientWidth"] + 1, "1280 desktop horizontal overflow"
    pg.locator("#studioMonA").scroll_into_view_if_needed()
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "today_compact_1280_light_open.png"))

    assert page_errors == [], f"page errors: {page_errors}"
    out = {
        "closed_heights": closed_heights,
        "expanded_heights": expanded_heights,
        "expanded_row_heights": expanded_row_heights,
        "en_summaries": en_summaries,
        "es_summaries": es_summaries,
        "desktop_grid": desk["gridCols"],
        "errors": page_errors,
    }
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
