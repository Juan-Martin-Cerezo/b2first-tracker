"""Fase practice-variety: shared non-repeating exercise pool in Today and Exam.

Verifies:
  1. exercisePool() returns >= 60 real entries (local + online) and >= 8 per
     skill (rue, w, l, sp), deduplicated by href + label, with valid schema.
  2. 10 consecutive calls to pickExercise('rue', null) return >= 8 distinct IDs
     and never two identical IDs in a row.
  3. The last 5 choices (D.pick[key]) never repeat; when the pool is exhausted
     (including a <= 5-item pool), it cycles by LRU without getting stuck or
     repeating consecutively.
  4. "Mark as done" increments D.mat[id].n (for both local via matDone and
     online entries) and future picks avoid done items while unused ones exist.
  5. Today: compact block above Materials with primary CTA, card height <= 180px
     at 390x844, Open link, Give me another, Mark as done, targets >= 44px.
  6. Exam: "Practise a real exercise" above Real mocks with paper + optional
     part selectors and "Give me one" card; collapsible Local materials section
     reusing Today's renderWhereToFind block renderer; existing Exam controls
     intact.
  7. 390x844 light & dark, EN & ES, zero horizontal overflow, zero inline
     handlers, zero pageerrors.

Saves screenshots in tests/out/:
  practice_pick_390_light.png
  exam_pick_390_dark.png
  exam_materials_1280_light.png
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
SKILLS = ["rue", "w", "l", "sp"]


def wait_for_materials(pg):
    pg.evaluate("if (!MATERIALS.length && typeof loadMaterial === 'function') loadMaterial();")
    pg.wait_for_function("Array.isArray(MATERIALS) && MATERIALS.length > 0", timeout=10000)
    pg.wait_for_timeout(150)


def show_today_studio(pg, studio_key, card_id):
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


out = {}
with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(200)
    wait_for_materials(pg)

    # ------------------------------------------------------------------
    # 1. Pool size, per-skill minimums, schema, deduplication, part filter
    # ------------------------------------------------------------------
    pool_info = pg.evaluate(
        """() => {
            const all = exercisePool(null, null);
            const bySkill = {};
            for (const sk of ['rue', 'w', 'l', 'sp']) {
                bySkill[sk] = exercisePool(sk, null).length;
            }
            const rueP1 = exercisePool('rue', 1);
            const hlKeys = new Set(all.map(e => String(e.href).trim() + '\\0' + String(e.label).trim().toLowerCase()));
            const badEntries = all.filter(e =>
                !e.id ||
                (e.kind !== 'local' && e.kind !== 'online') ||
                !['paper', 'lesson', 'online'].includes(e.type) ||
                !(e.part === 'all' || (Number.isInteger(e.part) && e.part >= 1 && e.part <= 7)) ||
                !(typeof e.mins === 'number' && e.mins > 0) ||
                !e.label || !e.href || !e.hint
            );
            const badP1 = rueP1.filter(e => e.part !== 1 && e.part !== 'all');
            return {
                total: all.length,
                localCount: all.filter(e => e.kind === 'local').length,
                onlineCount: all.filter(e => e.kind === 'online').length,
                uniqueHL: hlKeys.size,
                bySkill,
                badCount: badEntries.length,
                badSample: badEntries.slice(0, 3),
                rueP1Total: rueP1.length,
                rueP1Exact: rueP1.filter(e => e.part === 1).length,
                rueP1All: rueP1.filter(e => e.part === 'all').length,
                badP1Count: badP1.length,
            };
        }"""
    )
    assert pool_info["total"] >= 60, f"Pool too small: {pool_info}"
    assert pool_info["uniqueHL"] == pool_info["total"], f"Duplicates by href+label: {pool_info}"
    assert pool_info["badCount"] == 0, f"Invalid pool entries: {pool_info['badSample']}"
    for sk in SKILLS:
        assert pool_info["bySkill"][sk] >= 8, f"Skill {sk} pool < 8: {pool_info['bySkill']}"
    assert pool_info["rueP1Exact"] >= 1 and pool_info["rueP1All"] >= 1, (
        f"Part filter should include exact part + 'all': {pool_info}"
    )
    assert pool_info["badP1Count"] == 0, f"Part 1 filter leaked other parts: {pool_info}"
    out["1_pool"] = {
        "total": pool_info["total"],
        "local": pool_info["localCount"],
        "online": pool_info["onlineCount"],
        "bySkill": pool_info["bySkill"],
    }

    # ------------------------------------------------------------------
    # 2. 10 consecutive calls to pickExercise('rue', null): >=8 distinct,
    #    never two identical in a row, last 5 persisted in D.pick
    # ------------------------------------------------------------------
    ten_picks = pg.evaluate(
        """() => {
            D.pick = {};
            D.mat = {};
            const ids = [];
            for (let i = 0; i < 10; i++) {
                const ex = pickExercise('rue', null);
                ids.push(ex ? ex.id : null);
            }
            const pickState = Array.isArray(D.pick['rue:all']) ? D.pick['rue:all'].slice() : [];
            return { ids, pickState };
        }"""
    )
    ids10 = ten_picks["ids"]
    assert all(ids10), f"Null returned in 10 picks: {ids10}"
    assert len(set(ids10)) >= 8, f"Expected >=8 distinct ids in 10 picks, got {len(set(ids10))}: {ids10}"
    for a, b in zip(ids10, ids10[1:]):
        assert a != b, f"Consecutive duplicate in 10 picks: {a}"
    assert len(ten_picks["pickState"]) == 5, f"D.pick['rue:all'] should store last 5: {ten_picks['pickState']}"
    assert ten_picks["pickState"] == ids10[-5:], f"D.pick['rue:all'] mismatch: {ten_picks['pickState']} vs {ids10[-5:]}"
    out["2_ten_picks"] = {"distinct": len(set(ids10)), "last5_len": len(ten_picks["pickState"])}

    # ------------------------------------------------------------------
    # 3. Last 5 never repeat + LRU cycling when pool is exhausted
    # ------------------------------------------------------------------
    lru_res = pg.evaluate(
        """() => {
            // A) Full real Writing pool: run N + 7 picks to exhaust and cycle
            D.pick = {};
            D.mat = {};
            const wPool = exercisePool('w', null);
            const wSeq = [];
            for (let i = 0; i < wPool.length + 7; i++) {
                const ex = pickExercise('w', null);
                wSeq.push(ex ? ex.id : null);
            }
            let win5Repeat = false;
            for (let i = 0; i <= wSeq.length - 5; i++) {
                if (new Set(wSeq.slice(i, i + 5)).size < 5) win5Repeat = true;
            }
            let consecRepeat = false;
            for (let i = 1; i < wSeq.length; i++) {
                if (wSeq[i] === wSeq[i - 1]) consecRepeat = true;
            }

            // B) Exhaustion on a <= 5-item pool (only online Writing = 5 items)
            const savedMats = MATERIALS;
            MATERIALS = [];
            D.pick = {};
            D.mat = {};
            const smallPool = exercisePool('w', null);
            const smallSeq = [];
            for (let i = 0; i < smallPool.length * 2 + 2; i++) {
                const ex = pickExercise('w', null);
                smallSeq.push(ex ? ex.id : null);
            }
            MATERIALS = savedMats;

            // Empty pool returns null
            const emptyRes = pickExercise('nonexistent_skill', null);

            return {
                wPoolLen: wPool.length,
                wSeqLen: wSeq.length,
                wDistinctFirstCycle: new Set(wSeq.slice(0, wPool.length)).size,
                wNextCycleMatchesLru: wSeq.slice(wPool.length, wPool.length + 5).join('|') === wSeq.slice(0, 5).join('|'),
                win5Repeat,
                consecRepeat,
                smallPoolLen: smallPool.length,
                smallSeq,
                smallFirstFive: smallSeq.slice(0, smallPool.length),
                smallSecondFive: smallSeq.slice(smallPool.length, smallPool.length * 2),
                emptyRes,
            };
        }"""
    )
    assert lru_res["wDistinctFirstCycle"] == lru_res["wPoolLen"], (
        f"Did not visit all {lru_res['wPoolLen']} writing items before repeating: {lru_res}"
    )
    assert not lru_res["win5Repeat"], "Found repeat within 5-pick window"
    assert not lru_res["consecRepeat"], "Found consecutive repeat"
    assert lru_res["wNextCycleMatchesLru"], "After exhaustion, full pool did not cycle LRU"
    assert lru_res["smallPoolLen"] == 5, f"Expected 5 online writing items, got {lru_res['smallPoolLen']}"
    assert all(lru_res["smallSeq"]), f"Got null when cycling 5-item pool: {lru_res['smallSeq']}"
    assert len(set(lru_res["smallFirstFive"])) == 5, f"First 5 of 5-item pool not unique: {lru_res['smallFirstFive']}"
    assert lru_res["smallSecondFive"] == lru_res["smallFirstFive"], (
        f"5-item pool did not cycle in LRU order: {lru_res['smallFirstFive']} vs {lru_res['smallSecondFive']}"
    )
    assert lru_res["emptyRes"] is None, f"Empty pool should return null, got {lru_res['emptyRes']}"
    out["3_lru"] = {
        "w_pool": lru_res["wPoolLen"],
        "small_pool": lru_res["smallPoolLen"],
        "small_lru_exact": True,
    }

    # ------------------------------------------------------------------
    # 4. Today UI + Mark as done (local & online) + <= 180px height at 390x844
    # ------------------------------------------------------------------
    pg.evaluate("D.pick = {}; D.mat = {}; save(); document.documentElement.setAttribute('data-theme', 'light');")
    show_today_studio(pg, "mon-a", "studioMonA")
    pg.wait_for_timeout(120)

    # Check CTA exists above Materials in all 4 studios
    today_cta_order = pg.evaluate(
        """() => {
            return [
                ['pvBoxRue', 'wtfSectionRue'],
                ['pvBoxW', 'wtfSectionW'],
                ['pvBoxL', 'wtfSectionL'],
                ['pvBoxSp', 'wtfSectionSp'],
            ].map(([pvId, wtfId]) => {
                const pv = document.getElementById(pvId);
                const wtf = document.getElementById(wtfId);
                return {
                    pvId,
                    exists: !!pv,
                    aboveWtf: !!(pv && wtf && (pv.compareDocumentPosition(wtf) & Node.DOCUMENT_POSITION_FOLLOWING)),
                };
            });
        }"""
    )
    for row in today_cta_order:
        assert row["exists"] and row["aboveWtf"], f"Today picker not above Materials: {row}"

    # Click primary CTA in R&UoE
    pg.click("#pvBtnRue")
    pg.wait_for_timeout(140)

    today_card = pg.evaluate(
        """() => {
            const box = document.getElementById('pvBoxRue');
            const card = box && box.querySelector('.pv-card');
            if (!card) return null;
            const br = box.getBoundingClientRect();
            const link = card.querySelector('a.pv-open-link');
            const another = card.querySelector('[data-action="pvAnother"]');
            const done = card.querySelector('[data-action="pvMarkDone"]');
            const badge = card.querySelector('.pv-badge');
            const title = card.querySelector('.pv-card-title');
            const hint = card.querySelector('.pv-card-hint');
            const mins = card.querySelector('.pv-mins');
            return {
                boxH: Math.round(br.height),
                id: card.dataset.pvId || '',
                kind: card.dataset.pvKind || '',
                type: card.dataset.pvType || '',
                title: title ? title.textContent.trim() : '',
                badge: badge ? badge.textContent.trim() : '',
                mins: mins ? mins.textContent.trim() : '',
                hint: hint ? hint.textContent.trim() : '',
                href: link ? link.getAttribute('href') || '' : '',
                linkH: link ? Math.round(link.getBoundingClientRect().height) : 0,
                anotherH: another ? Math.round(another.getBoundingClientRect().height) : 0,
                doneH: done ? Math.round(done.getBoundingClientRect().height) : 0,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                html: box.outerHTML,
            };
        }"""
    )
    assert today_card is not None, "Today picked card did not render"
    assert not INLINE_HANDLER_RE.search(today_card["html"]), "Inline on* handler found in Today picker"
    assert today_card["boxH"] <= 180, f"Today picker height {today_card['boxH']}px > 180px at 390x844"
    assert today_card["title"] and today_card["badge"] and today_card["mins"] and today_card["hint"] and today_card["href"], (
        f"Missing fields in Today picked card: {today_card}"
    )
    assert today_card["linkH"] >= 44 and today_card["anotherH"] >= 44 and today_card["doneH"] >= 44, (
        f"Targets < 44px in Today picked card: {today_card}"
    )
    assert today_card["scrollWidth"] <= today_card["clientWidth"] + 1, (
        f"Horizontal overflow at 390x844 in Today: {today_card['scrollWidth']} > {today_card['clientWidth']}"
    )

    # Capture practice_pick_390_light.png
    pg.locator("#studioMonA").scroll_into_view_if_needed()
    pg.wait_for_timeout(120)
    pg.screenshot(path=os.path.join(OUT, "practice_pick_390_light.png"))

    # "Give me another" never returns the same exercise twice in a row
    first_id = today_card["id"]
    pg.click("#pvResRue [data-action='pvAnother']")
    pg.wait_for_timeout(120)
    second_id = pg.evaluate("document.querySelector('#pvResRue .pv-card').dataset.pvId")
    assert second_id and second_id != first_id, f"Give me another returned same id: {second_id}"

    # "Mark as done" increments D.mat[id].n and avoids that exercise next
    pg.click("#pvResRue [data-action='pvMarkDone']")
    pg.wait_for_timeout(140)
    done_check = pg.evaluate(
        """(doneId) => {
            const st = D.mat && D.mat[doneId];
            // Clear D.pick so ONLY D.mat[id].n drives avoidance
            D.pick = {};
            const next1 = pickExercise('rue', null);
            const next2 = pickExercise('rue', null);
            // Also test online mark-as-done explicitly via pvMarkDone
            const onlineEx = exercisePool('rue', null).find(e => e.kind === 'online');
            const fakeBtn = document.createElement('button');
            fakeBtn.dataset.pvId = onlineEx.id;
            fakeBtn.dataset.rel = onlineEx.id;
            fakeBtn.dataset.pvKind = 'online';
            pvMarkDone(fakeBtn);
            const onlineSt = D.mat && D.mat[onlineEx.id];
            return {
                doneN: st ? st.n : 0,
                doneLast: st ? st.last : '',
                avoided1: next1 && next1.id !== doneId,
                avoided2: next2 && next2.id !== doneId,
                onlineN: onlineSt ? onlineSt.n : 0,
                onlineLast: onlineSt ? onlineSt.last : '',
            };
        }""",
        second_id,
    )
    assert done_check["doneN"] == 1 and done_check["doneLast"], f"Mark as done did not record D.mat: {done_check}"
    assert done_check["avoided1"] and done_check["avoided2"], f"Marked-done item was not avoided: {done_check}"
    assert done_check["onlineN"] == 1 and done_check["onlineLast"], f"Online mark as done failed: {done_check}"
    out["4_today_and_done"] = {
        "boxH_390": today_card["boxH"],
        "first_id": first_id,
        "second_id": second_id,
        "doneN": done_check["doneN"],
        "onlineN": done_check["onlineN"],
    }

    # ------------------------------------------------------------------
    # 5. Exam: "Practise a real exercise" above Real mocks + Local materials
    #    reusing renderWhereToFind + existing controls intact
    # ------------------------------------------------------------------
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(200)

    exam_layout = pg.evaluate(
        """() => {
            const picker = document.getElementById('examPracticePicker');
            const mocks = document.querySelector('.u4-real-mocks');
            const mats = document.getElementById('examMaterialsCard');
            const sources = document.querySelector('.u4-exam-sources');
            const pr = picker ? picker.getBoundingClientRect() : null;
            const mr = mocks ? mocks.getBoundingClientRect() : null;
            const matSecs = [...document.querySelectorAll('#examMaterialsStack .wtf-section')].map(s => ({
                id: s.id,
                skill: s.dataset.wtfSkill,
                expanded: s.querySelector('.wtf-toggle').getAttribute('aria-expanded'),
                summary: s.querySelector('.wtf-toggle-summary').textContent.trim(),
                blockCount: s.querySelectorAll('.wtf-list .wtf-block').length,
                hasPaper: s.querySelectorAll('.wtf-block[data-wtf-kind="paper"]').length > 0,
                hasFull: s.querySelectorAll('.wtf-block[data-wtf-kind="full"]').length > 0,
                hasOnline: s.querySelectorAll('.wtf-block[data-wtf-kind="online"]').length > 0,
            }));
            return {
                pickerAboveMocks: !!(pr && mr && pr.bottom <= mr.top + 2),
                hasMats: !!mats,
                hasSources: !!sources,
                mockCards: document.querySelectorAll('#examSelectGrid .exam-card').length,
                hasFullMockBtn: !!document.querySelector('[data-action="startFullMock"]'),
                hasExPaper: !!document.getElementById('exPaper'),
                hasSearch: !!document.getElementById('examSourcesSearch'),
                hasFullLibBtn: !!document.querySelector('.u4-source-all button'),
                matSecs,
                pickerHtml: picker ? picker.outerHTML : '',
                matsHtml: mats ? mats.outerHTML : '',
            };
        }"""
    )
    assert exam_layout["pickerAboveMocks"], "Exam picker is not above Real mocks"
    assert exam_layout["hasMats"] and exam_layout["hasSources"], "Exam materials or sources missing"
    assert exam_layout["mockCards"] == 4, f"Expected 4 real mock cards, got {exam_layout['mockCards']}"
    assert exam_layout["hasFullMockBtn"] and exam_layout["hasExPaper"] and exam_layout["hasSearch"] and exam_layout["hasFullLibBtn"]
    assert not INLINE_HANDLER_RE.search(exam_layout["pickerHtml"]), "Inline on* handler in Exam picker"
    assert not INLINE_HANDLER_RE.search(exam_layout["matsHtml"]), "Inline on* handler in Exam materials"
    assert [s["skill"] for s in exam_layout["matSecs"]] == ["exam-rue", "exam-w", "exam-l", "exam-sp"]
    for s in exam_layout["matSecs"]:
        assert s["expanded"] == "false", f"Exam material section {s['skill']} not collapsed by default"
        assert s["blockCount"] >= 3 and s["hasPaper"] and s["hasFull"] and s["hasOnline"], (
            f"Exam material section {s['skill']} missing paper/full/online blocks: {s}"
        )

    # Select paper + part and click "Give me one"
    pg.select_option("#exPickSkill", "l")
    pg.wait_for_timeout(100)
    l_part_opts = pg.eval_on_selector_all("#exPickPart option", "els => els.map(o => o.value)")
    assert l_part_opts == ["all", "1", "2", "3", "4"], f"Listening part options mismatch: {l_part_opts}"
    pg.select_option("#exPickPart", "2")
    pg.click("#exPickBtn")
    pg.wait_for_timeout(140)

    exam_card = pg.evaluate(
        """() => {
            const card = document.querySelector('#exPickResult .pv-card');
            if (!card) return null;
            const link = card.querySelector('a.pv-open-link');
            const hint = card.querySelector('.pv-card-hint');
            const title = card.querySelector('.pv-card-title');
            const another = card.querySelector('[data-action="pvAnother"]');
            const done = card.querySelector('[data-action="pvMarkDone"]');
            return {
                id: card.dataset.pvId,
                skill: card.dataset.pvSkill,
                title: title ? title.textContent.trim() : '',
                hint: hint ? hint.textContent.trim() : '',
                href: link ? link.getAttribute('href') : '',
                linkH: link ? Math.round(link.getBoundingClientRect().height) : 0,
                anotherH: another ? Math.round(another.getBoundingClientRect().height) : 0,
                doneH: done ? Math.round(done.getBoundingClientRect().height) : 0,
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
            };
        }"""
    )
    assert exam_card is not None, "Exam Give me one did not render a card"
    assert exam_card["skill"] == "l" and exam_card["href"] and exam_card["hint"] and exam_card["title"]
    assert exam_card["linkH"] >= 44 and exam_card["anotherH"] >= 44 and exam_card["doneH"] >= 44
    assert exam_card["scrollWidth"] <= exam_card["clientWidth"] + 1, "Exam 390 light horizontal overflow"

    # Exam Give me another picks a different exercise
    pg.click("#exPickResult [data-action='pvAnother']")
    pg.wait_for_timeout(120)
    exam_card_2 = pg.evaluate("document.querySelector('#exPickResult .pv-card').dataset.pvId")
    assert exam_card_2 and exam_card_2 != exam_card["id"], "Exam Give me another repeated same id"

    # Capture exam_pick_390_dark.png
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); window.scrollTo(0, 0);")
    pg.wait_for_timeout(150)
    dark_ovf = pg.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
    assert dark_ovf["sw"] <= dark_ovf["cw"] + 1, f"Exam 390 dark overflow: {dark_ovf}"
    pg.screenshot(path=os.path.join(OUT, "exam_pick_390_dark.png"))
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    pg.wait_for_timeout(100)

    # ------------------------------------------------------------------
    # 6. Spanish i18n on 390x844 (Today + Exam)
    # ------------------------------------------------------------------
    pg.evaluate("setLang('es')")
    pg.wait_for_timeout(200)
    es_exam = pg.evaluate(
        """() => ({
            pickerTitle: document.querySelector('#examPracticePicker h2').textContent.trim(),
            giveBtn: document.getElementById('exPickBtn').textContent.trim(),
            matsTitle: document.querySelector('#examMaterialsCard h2').textContent.trim(),
            anotherBtn: document.querySelector('#exPickResult [data-action="pvAnother"]').textContent.trim(),
            doneBtn: document.querySelector('#exPickResult [data-action="pvMarkDone"]').textContent.trim(),
            sw: document.documentElement.scrollWidth,
            cw: document.documentElement.clientWidth,
        })"""
    )
    assert es_exam["pickerTitle"] == "Practicá un ejercicio real", f"ES Exam title mismatch: {es_exam}"
    assert es_exam["giveBtn"] == "Dame uno", f"ES Give me one mismatch: {es_exam}"
    assert es_exam["anotherBtn"] == "Dame otro", f"ES Give me another mismatch: {es_exam}"
    assert es_exam["doneBtn"] == "Marcar hecho", f"ES Mark as done mismatch: {es_exam}"
    assert es_exam["matsTitle"] == "Materiales locales por prueba", f"ES materials title mismatch: {es_exam}"
    assert es_exam["sw"] <= es_exam["cw"] + 1, f"Exam 390 ES overflow: {es_exam}"

    show_today_studio(pg, "mon-a", "studioMonA")
    es_today = pg.evaluate(
        """() => ({
            boxH: Math.round(document.getElementById('pvBoxRue').getBoundingClientRect().height),
            another: document.querySelector('#pvResRue [data-action="pvAnother"]').textContent.trim(),
            done: document.querySelector('#pvResRue [data-action="pvMarkDone"]').textContent.trim(),
            sw: document.documentElement.scrollWidth,
            cw: document.documentElement.clientWidth,
        })"""
    )
    assert es_today["boxH"] <= 180, f"Today 390 ES picker height {es_today['boxH']} > 180px"
    assert es_today["another"] == "Dame otro" and es_today["done"] == "Marcar hecho"
    assert es_today["sw"] <= es_today["cw"] + 1, f"Today 390 ES overflow: {es_today}"

    # ------------------------------------------------------------------
    # 7. Desktop 1280x900 Exam Local materials expanded + screenshot
    # ------------------------------------------------------------------
    pg.evaluate("setLang('en')")
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.click("nav button[data-view='exam']")
    pg.wait_for_timeout(200)
    pg.click("#wtfToggleExamRue")
    pg.wait_for_timeout(150)
    desk_mats = pg.evaluate(
        """() => {
            const sec = document.getElementById('wtfSectionExamRue');
            const list = document.getElementById('exMatRue');
            const cs = getComputedStyle(list);
            return {
                expanded: sec.querySelector('.wtf-toggle').getAttribute('aria-expanded'),
                blocks: list.querySelectorAll(':scope > .wtf-block').length,
                display: cs.display,
                sw: document.documentElement.scrollWidth,
                cw: document.documentElement.clientWidth,
            };
        }"""
    )
    assert desk_mats["expanded"] == "true" and desk_mats["blocks"] >= 6
    assert desk_mats["display"] == "grid", f"Desktop exam materials did not use 2-col grid: {desk_mats}"
    assert desk_mats["sw"] <= desk_mats["cw"] + 1, f"Desktop 1280 overflow: {desk_mats}"

    pg.evaluate("""() => {
        const card = document.getElementById('examMaterialsCard');
        if (card) window.scrollTo(0, Math.max(0, card.getBoundingClientRect().top + window.scrollY - 72));
    }""")
    pg.wait_for_timeout(140)
    pg.screenshot(path=os.path.join(OUT, "exam_materials_1280_light.png"))

    # Zero page errors
    assert page_errors == [], f"Page errors: {page_errors}"
    out["5_exam"] = {
        "pickerAboveMocks": exam_layout["pickerAboveMocks"],
        "examCard1": exam_card["id"],
        "examCard2": exam_card_2,
        "matSections": len(exam_layout["matSecs"]),
        "deskRueBlocks": desk_mats["blocks"],
    }
    out["6_es"] = {"exam": es_exam["pickerTitle"], "todayBoxH": es_today["boxH"]}
    out["screenshots"] = [
        "practice_pick_390_light.png",
        "exam_pick_390_dark.png",
        "exam_materials_1280_light.png",
    ]
    out["page_errors"] = page_errors
    browser.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
