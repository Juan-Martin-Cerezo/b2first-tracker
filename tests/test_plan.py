"""Tests of the deterministic weekly plan (buildWeeklyPlan) and its PLAN card.

Fixtures injected via page.evaluate with an isolated test user (pattern from
test_streak.py): it uses no real owner data and does not touch data/.
"""

import asyncio
import json
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8088/"

DIAG_FIXTURE = (
    "{date:'2026-10-20',correct:4,total:12,"
    "byPart:{1:{ok:1,n:2},2:{ok:0,n:2},3:{ok:1,n:2},4:{ok:1,n:1},"
    "5:{ok:1,n:2},6:{ok:1,n:1},7:{ok:0,n:2}},weakest:[3,2,7]}"
)


async def main():
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))

        await page.goto(URL, wait_until="networkidle")

        # Clear localStorage on start and use an isolated test user
        await page.evaluate(
            """() => {
            localStorage.clear();
            syncPush = () => {};
            syncPull = async () => null;
            const u = {id: 'test_plan_ci', name: 'TestPlan', color: '#1e3a8a', token: ''};
            localStorage.setItem('b2first_user', JSON.stringify(u));
            localStorage.setItem('ob_test_plan_ci', '1');
            USER = u;
            D = load();
            D.onboarded = true;
            D.log = [];
            D.errs = [];
            delete D.diag;
            hideAuthOverlay();
            hideOnboarding();
            refreshAll();
        }"""
        )

        # 1. No diagnostic -> needDiag visible and 0 slots
        res1 = await page.evaluate(
            """() => {
            D.log = []; D.errs = []; delete D.diag;
            save(); refreshAll();
            const plan = buildWeeklyPlan(D);
            return {
                needDiag: plan.needDiag === true,
                nSlots: plan.slots.length,
                cardVisible: !!document.getElementById('wpNeedDiag'),
                rows: document.querySelectorAll('#wpRows .wp-row').length,
                text: document.getElementById('weeklyPlanCard').textContent
            };
        }"""
        )
        assert res1["needDiag"] is True, f"Expected needDiag, got {res1}"
        assert res1["nSlots"] == 0, f"Expected 0 slots, got {res1}"
        assert res1["cardVisible"] is True, f"needDiag card not visible: {res1}"
        assert res1["rows"] == 0, f"Expected 0 rows, got {res1}"
        assert "Take the diagnostic" in res1["text"], f"Missing CTA: {res1['text']}"
        out["1_sin_diag_needDiag"] = "OK: needDiag visible, 0 slots"

        # 2. Diagnostic weakest:[3,2,7] -> those 3 parts appear in the slots
        await page.evaluate(
            """() => {
            D.diag = %s;
            D.log = []; D.errs = []; D.settings.weekGoal = 5;
            save(); refreshAll();
        }"""
            % DIAG_FIXTURE
        )
        res2 = await page.evaluate(
            "() => buildWeeklyPlan(D).slots.map(s => s.part)"
        )
        parts2 = [x for x in res2 if x is not None]
        for w in (3, 2, 7):
            assert w in parts2, f"Expected weakest part {w} in slots, got {res2}"
        out["2_weakest_en_slots"] = f"OK: parts={res2}"

        # 3. Always exactly 1 Writing slot and 1 Listening slot
        res3 = await page.evaluate(
            """() => {
            const cnt = (p, t) => p.slots.filter(s => s.type === t).length;
            const p5 = buildWeeklyPlan(D);
            D.settings.weekGoal = 6; const p6 = buildWeeklyPlan(D);
            D.settings.weekGoal = 5;
            return {w5: cnt(p5,'w'), l5: cnt(p5,'l'), w6: cnt(p6,'w'), l6: cnt(p6,'l')};
        }"""
        )
        assert res3 == {"w5": 1, "l5": 1, "w6": 1, "l6": 1}, f"Bad w/l counts: {res3}"
        out["3_un_w_un_l"] = f"OK: {res3}"

        # 4. weekGoal:3 -> 3 slots; weekGoal:6 -> 6 slots
        res4 = await page.evaluate(
            """() => {
            D.settings.weekGoal = 3; const n3 = buildWeeklyPlan(D).slots.length;
            D.settings.weekGoal = 6; const n6 = buildWeeklyPlan(D).slots.length;
            D.settings.weekGoal = 5;
            return {n3, n6};
        }"""
        )
        assert res4 == {"n3": 3, "n6": 6}, f"Bad slot counts: {res4}"
        out["4_weekGoal_3_y_6"] = f"OK: {res4}"

        # 5. L-GAP majority -> part 1 or 3; G-ERR majority -> part 2 or 4
        res5 = await page.evaluate(
            """() => {
            D.diag.weakest = [7,5,6];
            D.settings.weekGoal = 6;
            const mk = code => [1,2,3].map(() => ({date:'2026-10-25', code, part:7, note:'x'}));
            D.errs = mk('L-GAP');
            const lex = buildWeeklyPlan(D).slots.map(s => s.part);
            D.errs = mk('G-ERR');
            const gram = buildWeeklyPlan(D).slots.map(s => s.part);
            D.errs = []; D.settings.weekGoal = 5; D.diag.weakest = [3,2,7];
            return {lex, gram};
        }"""
        )
        lex_parts = [x for x in res5["lex"] if x is not None]
        gram_parts = [x for x in res5["gram"] if x is not None]
        assert any(x in (1, 3) for x in lex_parts), f"L-GAP majority -> no part 1/3: {res5['lex']}"
        assert any(x in (2, 4) for x in gram_parts), f"G-ERR majority -> no part 2/4: {res5['gram']}"
        out["5_taxonomia_fill"] = f"OK: lex={res5['lex']}, gram={res5['gram']}"

        # 6. No repeated part on the same day (weekGoal 7 -> some day has 2 slots)
        res6 = await page.evaluate(
            """() => {
            D.settings.weekGoal = 7;
            D.diag.weakest = [7,5,6];
            D.errs = [1,2,3,4].map(() => ({date:'2026-10-25', code:'L-GAP', part:7, note:'x'}));
            const plan = buildWeeklyPlan(D);
            D.settings.weekGoal = 5; D.errs = []; D.diag.weakest = [3,2,7];
            return plan.slots.map(s => ({day: s.day, part: s.part}));
        }"""
        )
        assert len(res6) == 7, f"Expected 7 slots, got {res6}"
        by_day = {}
        for s in res6:
            by_day.setdefault(s["day"], []).append(s["part"])
        for day, ps in by_day.items():
            vals = [x for x in ps if x is not None]
            assert len(vals) == len(set(vals)), f"Repeated part on {day}: {ps}"
        out["6_sin_repetir_por_dia"] = f"OK: per day={by_day}"

        # 7. Each slot's reason is non-empty and cites the data that justifies it
        res7 = await page.evaluate(
            "() => buildWeeklyPlan(D).slots.map(s => s.reason)"
        )
        assert len(res7) >= 5, f"Expected >=5 reasons, got {res7}"
        for r in res7:
            assert isinstance(r, str) and r.strip(), f"Empty reason: {r!r}"
            assert ("diagnostic" in r) or ("error" in r) or ("Writing" in r), f"Reason without data: {r!r}"
        out["7_reasons_con_datos"] = f"OK: {len(res7)} reasons cite diagnostic/errors/Writing"

        # UI: rendered rows, "Why this?", Regenerate and Start -> PARTS
        await page.click("nav button[data-view='plan']")
        rows = await page.eval_on_selector_all(
            "#wpRows .wp-row",
            "els => els.map(e => ({day: e.dataset.day, part: e.dataset.part,"
            " type: e.dataset.type, reason: (e.querySelector('.wp-reason')||{textContent:''}).textContent}))",
        )
        assert len(rows) == 5, f"Expected 5 rows in card, got {len(rows)}"
        assert all(r["reason"].strip() for r in rows), f"Empty reason in row: {rows}"
        await page.click("#wpWhy summary")
        why_open = await page.evaluate("document.getElementById('wpWhy').open === true")
        why_text = await page.eval_on_selector("#wpWhyBody", "e => e.textContent")
        assert why_open is True, "details 'Why this?' did not open"
        assert "weekGoal" in why_text and "14 days" in why_text and "taxonomy" in why_text, f"why incomplete: {why_text}"
        await page.click("#wpRegenBtn")
        rows_after = await page.eval_on_selector_all("#wpRows .wp-row", "els => els.length")
        assert rows_after == 5, f"Regenerate broke rows: {rows_after}"
        first_ue = next(i for i, r in enumerate(rows) if r["type"] == "ue")
        ue_part = int(rows[first_ue]["part"])
        await page.eval_on_selector_all(
            "#wpRows .wp-row", f"els => els[{first_ue}].querySelector('.wp-start').click()"
        )
        nav_state = await page.evaluate(
            "() => ({view: document.querySelector('.view.active')?.id,"
            " filter: PARTS_FILTER, steps: document.querySelectorAll('#partsList .step').length})"
        )
        assert nav_state["view"] == "v-partes", f"Start did not navigate to PARTS: {nav_state}"
        assert nav_state["filter"] == ue_part, f"Filter not applied: {nav_state}"
        assert nav_state["steps"] == 1, f"Filter did not leave 1 part: {nav_state}"
        out["ui_card_y_empezar"] = f"OK: rows=5, why open, Start -> PARTS part {ue_part}"

        # Clean up the test user's localStorage
        await page.evaluate(
            "localStorage.removeItem('b2first_tracker_v1_test_plan_ci'); localStorage.removeItem('b2first_user');"
        )
        assert errs == [], f"JS errors: {errs}"
        out["8_errores_js"] = errs
        await browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
