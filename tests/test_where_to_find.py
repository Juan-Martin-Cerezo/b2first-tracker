"""Where to find: vertical material blocks with paired keys, full paper, and separate online.

Verifies all four Today session studios (R&UoE, Writing, Listening, Speaking)
with a realistic stub MAT catalogue:
  1. Each of the 4 sections renders vertical blocks (flex column with gap), not flat chips.
  2. R&UoE pairs R&UoE S1 + Keys S1 in the same block, R&UoE S2 in another, gap > 8px.
  3. Listening Test 1 block contains Questions, Answer key, Audio (2nd line), Tapescript (2nd line).
  4. Online sits in a separate block with "Online" / "En línea" tag and usage hint.
  5. 390x844 light & dark: no horizontal overflow, all links clickable (>=44px), EN & ES copy.
  6. Deep links: per-part blocks point directly to that part's file; Full paper block points
     to the full test (never a single part or folder).

Saves screenshots in tests/out/:
  wtf_<skill>_390_<theme>.png (4 skills x light/dark) and wtf_rue_1280_light.png.
"""
import json
import os

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

STUB_MAT = {
    # R&UoE full sample papers + keys
    "rueS1": "/files/01-Examen-Completo-01/B2-First-sample-paper-1-RUE-2022.pdf",
    "rueS2": "/files/02-Examen-Completo-02/B2-First-sample-paper-2-RUE-2022.pdf",
    "rueFS1": "/files/03-Examen-Completo-For-Schools-01/B2-First-FS-sample-paper-1-RUE-2022.pdf",
    "rueFS2": "/files/04-Examen-Completo-For-Schools-02/FS-sample-paper-2-RUE.pdf",
    "keyS1": "/files/01-Examen-Completo-01/B2-First-RUE-Sample-1-Answer-Key-2022.pdf",
    "keyS2": "/files/02-Examen-Completo-02/sample-paper-2-answer-keys.pdf",
    "keyFS1": "/files/03-Examen-Completo-For-Schools-01/FS-RUE-Sample-1-Answer-Key-2022.pdf",
    "keyFS2": "/files/04-Examen-Completo-For-Schools-02/FS-Answer-key-sample-paper-2.pdf",
    # R&UoE per-part lesson plans + self-study
    **{f"lpR{n}": f"/files/10-Lesson-Plans/B2-First/reading-part-{n}.pdf" for n in range(1, 8)},
    **{f"fR{n}": f"/files/10-Lesson-Plans/B2-First-For-Schools/reading-part-{n}.pdf" for n in range(1, 8)},
    "rAct1": "/files/07-Reading/self-study-reading-activities-1.pdf",
    "rAct1b": "/files/07-Reading/self-study-reading-activities-part-1.pdf",
    "rAct2": "/files/07-Reading/self-study-further-reading-activities.pdf",
    "rGuide": "/files/07-Reading/developing-reading-skills-guide.pdf",
    # Writing full papers + per-part plans + guides
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
    # Listening sample 1, sample 2 per-part, full tests, handbook
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
    # Speaking visuals + examiner notes + per-part plans
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
    ("rue", "mon-a", "studioMonA", "gUeChips"),
    ("w", "mon-b", "studioMonB", "gWChips"),
    ("l", "fri-a", "studioFriA", "gLChips"),
    ("sp", "fri-b", "studioFriB", "gSpChips"),
]


def open_studio(pg, studio_key, card_id):
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
            if (card) {
                const sec = card.querySelector('.wtf-section');
                const btn = sec && sec.querySelector('.wtf-toggle');
                if (btn && btn.getAttribute('aria-expanded') !== 'true') {
                    btn.click();
                }
            }
        }""",
        [studio_key, card_id],
    )
    pg.wait_for_timeout(180)


def inspect_section(pg, container_id):
    return pg.evaluate(
        """(cid) => {
            const c = document.getElementById(cid);
            if (!c) return null;
            const cs = getComputedStyle(c);
            const blocks = [...c.querySelectorAll(':scope > .wtf-block')].map(b => {
                const r = b.getBoundingClientRect();
                const main = b.querySelector('.wtf-main');
                const extra = b.querySelector('.wtf-extra');
                const links = [...b.querySelectorAll('a')].map(a => {
                    const ar = a.getBoundingClientRect();
                    return {
                        text: a.textContent.trim(),
                        href: a.getAttribute('href') || '',
                        inExtra: !!a.closest('.wtf-extra'),
                        w: Math.round(ar.width),
                        h: Math.round(ar.height),
                        top: Math.round(ar.top),
                        right: Math.round(ar.right),
                    };
                });
                const tag = b.querySelector('.wtf-tag');
                const hint = b.querySelector('.wtf-hint');
                const head = b.querySelector('.wtf-head');
                return {
                    kind: b.dataset.wtfKind || '',
                    cls: b.className,
                    head: head ? head.textContent.trim() : '',
                    tag: tag ? tag.textContent.trim() : '',
                    hint: hint ? hint.textContent.trim() : '',
                    top: r.top,
                    bottom: r.bottom,
                    height: r.height,
                    mainTop: main ? main.getBoundingClientRect().top : null,
                    extraTop: extra ? extra.getBoundingClientRect().top : null,
                    links: links,
                };
            });
            return {
                display: cs.display,
                flexDirection: cs.flexDirection,
                rowGap: parseFloat(cs.rowGap) || 0,
                chipsCount: c.querySelectorAll('.chip').length,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                blocks: blocks,
            };
        }""",
        container_id,
    )


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)

    # Seed stub catalogue AFTER setLang('en') so refreshAll() does not reset
    # SP_TODAY.part or overwrite MAT via an idle /libros.json fetch.
    pg.route("**/libros.json", lambda route: route.fulfill(status=200, content_type="application/json", body="[]"))
    pg.evaluate(
        """(mat) => {
            setLang('en');
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
        STUB_MAT,
    )
    pg.wait_for_timeout(300)

    # 1-5 (EN, light & dark, 390x844)
    en_data = {}
    for theme in ("light", "dark"):
        pg.evaluate(
            "(th) => { document.documentElement.setAttribute('data-theme', th); }",
            theme,
        )
        pg.wait_for_timeout(120)
        for skill, studio_key, card_id, cid in SECTIONS:
            open_studio(pg, studio_key, card_id)
            data = inspect_section(pg, cid)
            assert data is not None, f"{skill}: container #{cid} missing"
            assert data["display"] in ("flex", "block"), f"{skill}: bad display {data['display']}"
            if data["display"] == "flex":
                assert data["flexDirection"] == "column", f"{skill}: not vertical column: {data['flexDirection']}"
            assert data["chipsCount"] == 0, f"{skill}: flat .chip elements remain inside #{cid}"
            assert len(data["blocks"]) >= 3, f"{skill}: expected paper + full + online blocks, got {len(data['blocks'])}"

            # Vertical stacking & spacing > 8px between adjacent blocks
            for a, b in zip(data["blocks"], data["blocks"][1:]):
                gap = b["top"] - a["bottom"]
                assert gap > 8, f"{skill} ({theme}): gap between blocks is {gap:.1f}px (need > 8px)"

            # No horizontal overflow at 390x844
            assert data["scrollWidth"] <= data["clientWidth"] + 1, (
                f"{skill} ({theme}): horizontal overflow {data['scrollWidth']} > {data['clientWidth']}"
            )

            # Every link clickable with >=44px target height
            for blk in data["blocks"]:
                assert blk["hint"], f"{skill}: block missing usage hint: {blk}"
                for lnk in blk["links"]:
                    assert lnk["href"], f"{skill}: empty href in {lnk}"
                    assert lnk["h"] >= 44, f"{skill} ({theme}): link {lnk['text']!r} height {lnk['h']} < 44px"
                    assert lnk["w"] >= 44, f"{skill} ({theme}): link {lnk['text']!r} width {lnk['w']} < 44px"
                    assert lnk["right"] <= data["clientWidth"] + 1, (
                        f"{skill} ({theme}): link {lnk['text']!r} overflows viewport right ({lnk['right']})"
                    )

            # Online block is separate, last, tagged "Online", has hint, not inside paper row
            online_blocks = [b for b in data["blocks"] if b["kind"] == "online"]
            assert len(online_blocks) == 1, f"{skill}: expected 1 online block, got {online_blocks}"
            assert data["blocks"][-1]["kind"] == "online", f"{skill}: online block is not last"
            assert online_blocks[0]["tag"].lower() == "online", f"{skill}: bad online tag {online_blocks[0]['tag']!r}"
            assert len(online_blocks[0]["hint"]) >= 20, f"{skill}: online hint too short: {online_blocks[0]['hint']!r}"

            # Full paper block is separate and tagged "Full paper"
            full_blocks = [b for b in data["blocks"] if b["kind"] == "full"]
            assert len(full_blocks) == 1, f"{skill}: expected 1 full paper block, got {full_blocks}"
            assert full_blocks[0]["tag"].lower() == "full paper", f"{skill}: bad full tag {full_blocks[0]['tag']!r}"

            # Capture 390x844 light & dark screenshots of each section
            guide_loc = pg.locator(f"#{cid}").locator("..")
            guide_loc.scroll_into_view_if_needed()
            pg.wait_for_timeout(100)
            pg.screenshot(path=os.path.join(OUT, f"wtf_{skill}_390_{theme}.png"))

            if theme == "light":
                en_data[skill] = data

    # 2. R&UoE: R&UoE S1 + Keys S1 in same block; R&UoE S2 in another; vertical gap > 8px
    rue_blocks = en_data["rue"]["blocks"]
    s1_blocks = [b for b in rue_blocks if any(l["text"] == "R&UoE S1" for l in b["links"])]
    s2_blocks = [b for b in rue_blocks if any(l["text"] == "R&UoE S2" for l in b["links"])]
    assert len(s1_blocks) == 1, f"expected 1 R&UoE S1 block: {s1_blocks}"
    assert len(s2_blocks) == 1, f"expected 1 R&UoE S2 block: {s2_blocks}"
    s1_texts = [l["text"] for l in s1_blocks[0]["links"]]
    s2_texts = [l["text"] for l in s2_blocks[0]["links"]]
    assert "R&UoE S1" in s1_texts and "Keys S1" in s1_texts, f"R&UoE S1 and Keys S1 not in same block: {s1_texts}"
    assert "R&UoE S2" not in s1_texts, f"R&UoE S2 leaked into S1 block: {s1_texts}"
    assert "R&UoE S2" in s2_texts and "Keys S2" in s2_texts, f"R&UoE S2 and Keys S2 not paired: {s2_texts}"
    assert s2_blocks[0]["top"] - s1_blocks[0]["bottom"] > 8, "gap between S1 and S2 <= 8px"

    # 3. Listening: Test 1 block contains Questions, Answer key, Audio (2nd line), Tapescript (2nd line)
    l_blocks = en_data["l"]["blocks"]
    t1_blocks = [b for b in l_blocks if b["head"] == "Listening test 1"]
    assert len(t1_blocks) == 1, f"expected 1 Listening test 1 block: {[b['head'] for b in l_blocks]}"
    t1 = t1_blocks[0]
    t1_labels = {l["text"]: l for l in t1["links"]}
    for needed in ("Questions", "Answer key", "Audio", "Tapescript"):
        assert needed in t1_labels, f"Listening test 1 missing {needed}: {list(t1_labels)}"
    assert not t1_labels["Questions"]["inExtra"], "Questions should be on line 1"
    assert not t1_labels["Answer key"]["inExtra"], "Answer key should be on line 1"
    assert t1_labels["Audio"]["inExtra"], "Audio should be on line 2 (.wtf-extra)"
    assert t1_labels["Tapescript"]["inExtra"], "Tapescript should be on line 2 (.wtf-extra)"
    assert t1["extraTop"] > t1["mainTop"], f"extra line not below main line: {t1}"

    # 6. Deep links: per-part blocks point directly to that part's file; Full paper points to full test
    # R&UoE: per-part Lesson plan P1 vs S1 vs Full paper
    rue_part1 = [b for b in rue_blocks if any(l["text"] == "Lesson plan P1" for l in b["links"])]
    assert rue_part1, "R&UoE Lesson plan P1 block missing"
    part1_href = rue_part1[0]["links"][0]["href"]
    assert "part-1" in part1_href and part1_href.endswith(".pdf"), f"bad per-part href: {part1_href}"
    s1_href = [l["href"] for l in s1_blocks[0]["links"] if l["text"] == "R&UoE S1"][0]
    assert "sample-paper-1-RUE" in s1_href and s1_href.endswith(".pdf"), f"bad R&UoE S1 href: {s1_href}"
    rue_full = [b for b in rue_blocks if b["kind"] == "full"][0]
    rue_full_hrefs = [l["href"] for l in rue_full["links"]]
    assert any("sample-paper-1-RUE" in h for h in rue_full_hrefs), f"R&UoE full paper missing full PDF: {rue_full_hrefs}"
    assert any(h.startswith("https://") for h in rue_full_hrefs), f"R&UoE full paper missing online link: {rue_full_hrefs}"
    assert not any("part-1" in h or "lpR" in h for h in rue_full_hrefs), f"R&UoE full paper points to single part: {rue_full_hrefs}"

    # Listening: Test 2 part 1 vs Test 1 vs Full test
    l_part1 = [b for b in l_blocks if b["head"] == "Listening test 2 · part 1"]
    assert l_part1, f"Listening test 2 · part 1 missing: {[b['head'] for b in l_blocks]}"
    l_part1_hrefs = [l["href"] for l in l_part1[0]["links"]]
    assert any("part-1" in h and h.endswith(".mp3") for h in l_part1_hrefs), f"Listening part 1 audio not deep-linked: {l_part1_hrefs}"
    t1_q_href = t1_labels["Questions"]["href"]
    assert "sample-paper-1-Listening" in t1_q_href and t1_q_href.endswith(".pdf"), f"bad Listening Test 1 href: {t1_q_href}"
    l_full = [b for b in l_blocks if b["kind"] == "full"][0]
    l_full_hrefs = [l["href"] for l in l_full["links"]]
    assert any("full-test" in h for h in l_full_hrefs), f"Listening full paper missing full test: {l_full_hrefs}"
    assert any(h.startswith("https://") for h in l_full_hrefs), f"Listening full paper missing online full test: {l_full_hrefs}"
    assert not any("part-1" in h or "auS2p" in h or "lpL" in h for h in l_full_hrefs), (
        f"Listening full paper points to single part: {l_full_hrefs}"
    )

    # Writing & Speaking per-part vs Full paper deep links
    w_blocks = en_data["w"]["blocks"]
    w_p1 = [b for b in w_blocks if any(l["text"] == "Lesson W1" for l in b["links"])]
    assert w_p1 and "part-1" in w_p1[0]["links"][0]["href"], f"Writing Lesson W1 bad href: {w_p1}"
    w_full_hrefs = [l["href"] for l in w_blocks if l["kind"] == "full" for l in l["links"]]
    assert not any("part-1" in h for h in w_full_hrefs), f"Writing full paper points to part: {w_full_hrefs}"

    sp_blocks = en_data["sp"]["blocks"]
    sp_p2 = [b for b in sp_blocks if any(l["text"] == "Lesson P2" for l in b["links"])]
    assert sp_p2 and "part-2" in sp_p2[0]["links"][0]["href"], f"Speaking Lesson P2 bad href: {sp_p2}"
    sp_full_hrefs = [l["href"] for l in sp_blocks if l["kind"] == "full" for l in l["links"]]
    assert not any("part-2" in h for h in sp_full_hrefs), f"Speaking full paper points to part: {sp_full_hrefs}"

    # 5b. ES i18n check: instructions & tags translated, file names (R&UoE S1, Keys S1) preserved
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light'); setLang('es'); renderGuides();")
    pg.wait_for_timeout(300)
    es_hints = {}
    for skill, studio_key, card_id, cid in SECTIONS:
        open_studio(pg, studio_key, card_id)
        es_data = inspect_section(pg, cid)
        assert es_data["scrollWidth"] <= es_data["clientWidth"] + 1, f"{skill} (es): horizontal overflow"
        online_es = [b for b in es_data["blocks"] if b["kind"] == "online"][0]
        full_es = [b for b in es_data["blocks"] if b["kind"] == "full"][0]
        assert online_es["tag"].lower() == "en línea", f"{skill} (es): online tag not translated: {online_es['tag']!r}"
        assert full_es["tag"].lower() == "examen completo", f"{skill} (es): full tag not translated: {full_es['tag']!r}"
        assert online_es["hint"] != en_data[skill]["blocks"][-1]["hint"], f"{skill}: online hint not translated to ES"
        es_hints[skill] = online_es["hint"]
        if skill == "rue":
            es_s1 = [b for b in es_data["blocks"] if any(l["text"] == "R&UoE S1" for l in b["links"])]
            assert es_s1 and any(l["text"] == "Keys S1" for l in es_s1[0]["links"]), "R&UoE S1 / Keys S1 names changed in ES"

    # 7. Empty catalog never invents local paper blocks
    pg.evaluate("MAT = {}; setLang('en'); renderGuides();")
    pg.wait_for_timeout(150)
    for skill, studio_key, card_id, cid in SECTIONS:
        open_studio(pg, studio_key, card_id)
        empty_data = inspect_section(pg, cid)
        paper_blocks = [b for b in empty_data["blocks"] if b["kind"] == "paper"]
        assert paper_blocks == [], f"{skill}: invented paper blocks on empty MAT: {paper_blocks}"

    # Desktop 1280x800 screenshot of R&UoE (and Listening) in light mode with stub catalog
    pg.set_viewport_size({"width": 1280, "height": 800})
    pg.evaluate(
        """(mat) => {
            MAT = Object.assign({}, mat);
            document.documentElement.setAttribute('data-theme', 'light');
            document.getElementById('uePart').value = '1';
            setLang('en');
            renderGuides();
        }""",
        STUB_MAT,
    )
    open_studio(pg, "mon-a", "studioMonA")
    pg.locator("#studioMonA").screenshot(path=os.path.join(OUT, "wtf_rue_1280_light.png"))

    assert page_errors == [], f"page errors: {page_errors}"
    out = {
        "sections": {k: len(v["blocks"]) for k, v in en_data.items()},
        "rue_s1_links": s1_texts,
        "listening_t1_links": list(t1_labels.keys()),
        "es_online_hints": es_hints,
        "errors": page_errors,
    }
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
