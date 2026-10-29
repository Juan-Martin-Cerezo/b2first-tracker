"""Tests del plan semanal determinista (buildWeeklyPlan) y su card en PLAN.

Fixtures inyectadas por page.evaluate con usuario aislado (patrón de
test_streak.py): no usa datos reales del owner ni toca data/.
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

        # Limpiar localStorage al empezar y usar un usuario de prueba aislado
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

        # 1. Sin diagnóstico -> needDiag visible y 0 slots
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
        assert "Hacé el diagnóstico" in res1["text"], f"Missing CTA: {res1['text']}"
        out["1_sin_diag_needDiag"] = "OK: needDiag visible, 0 slots"

        # 2. Diagnóstico weakest:[3,2,7] -> esas 3 partes aparecen en los slots
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

        # 3. Siempre exactamente 1 slot de Writing y 1 de Listening
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

        # 5. Mayoría L-GAP -> parte 1 o 3; mayoría G-ERR -> parte 2 o 4
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

        # 6. Ninguna parte repetida el mismo día (weekGoal 7 -> hay día con 2 slots)
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
            assert len(vals) == len(set(vals)), f"Parte repetida el {day}: {ps}"
        out["6_sin_repetir_por_dia"] = f"OK: por día={by_day}"

        # 7. reason de cada slot no vacío y menciona el dato que lo justifica
        res7 = await page.evaluate(
            "() => buildWeeklyPlan(D).slots.map(s => s.reason)"
        )
        assert len(res7) >= 5, f"Expected >=5 reasons, got {res7}"
        for r in res7:
            assert isinstance(r, str) and r.strip(), f"reason vacío: {r!r}"
            assert ("diagnóstico" in r) or ("errores" in r) or ("Writing" in r), f"reason sin dato: {r!r}"
        out["7_reasons_con_datos"] = f"OK: {len(res7)} reasons citan diagnóstico/errores/Writing"

        # UI: filas renderizadas, ¿Por qué esto?, Regenerar y Empezar -> PARTES
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
        assert why_open is True, "details ¿Por qué esto? did not open"
        assert "weekGoal" in why_text and "14 días" in why_text and "taxonomía" in why_text, f"why incomplete: {why_text}"
        await page.click("#wpRegenBtn")
        rows_after = await page.eval_on_selector_all("#wpRows .wp-row", "els => els.length")
        assert rows_after == 5, f"Regenerar broke rows: {rows_after}"
        first_ue = next(i for i, r in enumerate(rows) if r["type"] == "ue")
        ue_part = int(rows[first_ue]["part"])
        await page.eval_on_selector_all(
            "#wpRows .wp-row", f"els => els[{first_ue}].querySelector('.wp-start').click()"
        )
        nav_state = await page.evaluate(
            "() => ({view: document.querySelector('.view.active')?.id,"
            " filter: PARTS_FILTER, steps: document.querySelectorAll('#partsList .step').length})"
        )
        assert nav_state["view"] == "v-partes", f"Empezar no navegó a PARTES: {nav_state}"
        assert nav_state["filter"] == ue_part, f"Filtro mal aplicado: {nav_state}"
        assert nav_state["steps"] == 1, f"Filtro no dejó 1 parte: {nav_state}"
        out["ui_card_y_empezar"] = f"OK: rows=5, why abierto, Empezar -> PARTES parte {ue_part}"

        # Limpiar localStorage del usuario de prueba
        await page.evaluate(
            "localStorage.removeItem('b2first_tracker_v1_test_plan_ci'); localStorage.removeItem('b2first_user');"
        )
        assert errs == [], f"JS errors: {errs}"
        out["8_errores_js"] = errs
        await browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
