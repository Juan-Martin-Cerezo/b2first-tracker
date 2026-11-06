"""Tests of the deterministic weekly plan (buildWeeklyPlan) and its PLAN card.

The week is the continuous rotation queue: the diagnostic gates the plan, and
the sessions come from the schedule and the units already logged, one skill per
session. Fixtures injected via page.evaluate with an isolated test user
(pattern from test_streak.py): it uses no real owner data and does not touch
data/.
"""

import asyncio
import json
from playwright.async_api import async_playwright

from helpers import isolated_server

URL = isolated_server() + "/"

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

        await page.goto(URL + "app", wait_until="networkidle")

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
            D.settings.schedule = [1,2,3,4,5].map(d => ({day: d, time: '15:30'}));
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

        # 2. The diagnostic gates the plan; the week itself is the rotation
        #    queue: one session per scheduled day, each one single skill and
        #    starting at the first unit when the log is empty.
        await page.evaluate(
            """() => {
            D.diag = %s;
            D.log = []; D.errs = []; D.settings.weekGoal = 5;
            save(); refreshAll();
        }"""
            % DIAG_FIXTURE
        )
        res2 = await page.evaluate(
            """() => buildWeeklyPlan(D).slots.map(s => ({
                type: s.type,
                skills: (s.units || []).map(u => u.skill),
                units: (s.units || []).map(queueUnitLabel),
            }))"""
        )
        assert len(res2) == 5, f"Expected one session per scheduled day: {res2}"
        assert all(r["units"] for r in res2), f"Slot without queue units: {res2}"
        assert all(len(set(r["skills"])) == 1 for r in res2), (
            f"a session mixed skills: {res2}"
        )
        assert res2[0]["units"] == ["Reading part 1"], (
            f"the empty log did not start the queue at unit 1: {res2}"
        )
        out["2_sesiones_de_la_cola"] = f"OK: {[r['units'] for r in res2]}"

        # 3. The position comes from the log: five days with no log interleave
        #    R&UE and Listening; five logged Reading units move the same week
        #    to Writing and Speaking.
        res3 = await page.evaluate(
            """() => {
            const sched = n => [1,2,3,4,5,6,7].slice(0, n)
                .map(d => ({day: d, time: '15:30'}));
            const skills = () => buildWeeklyPlan(D).slots.map(s => s.units[0].skill);
            D.settings.schedule = sched(5); const d5 = skills();
            D.settings.schedule = sched(6); const d6 = skills();
            D.settings.schedule = sched(5);
            D.log = [1,2,3,4,5].map(() => ({date:'2026-10-01', type:'ue', part:1, min:8}));
            const moved = skills();
            D.log = [];
            return {d5, d6, moved};
        }"""
        )
        assert res3["d5"] == ["rue", "l", "rue", "l", "rue"], (
            f"the five-day week is not the queue from unit 1: {res3['d5']}"
        )
        assert res3["d6"] == ["rue", "l", "rue", "l", "rue", "l"], (
            f"the six-day week is not the queue from unit 1: {res3['d6']}"
        )
        assert res3["moved"] == ["w", "sp", "w", "sp", "w"], (
            f"five logged units did not move the queue: {res3['moved']}"
        )
        out["3_posicion_del_log"] = f"OK: {res3}"

        # 4. The slot count is the number of scheduled days.
        res4 = await page.evaluate(
            """() => {
            const sched = n => [1,2,3,4,5,6,7].slice(0, n)
                .map(d => ({day: d, time: '15:30'}));
            D.settings.schedule = sched(3); const n3 = buildWeeklyPlan(D).slots.length;
            D.settings.schedule = sched(6); const n6 = buildWeeklyPlan(D).slots.length;
            D.settings.schedule = sched(5);
            return {n3, n6};
        }"""
        )
        assert res4 == {"n3": 3, "n6": 6}, f"Bad slot counts: {res4}"
        out["4_weekGoal_3_y_6"] = f"OK: {res4}"

        # 5. itemsPerSession: a session takes that many consecutive units of one
        #    skill, and its minutes are the sum of those units.
        res5 = await page.evaluate(
            """() => {
            D.log = []; D.errs = [];
            D.settings.itemsPerSession = 2;
            const plan = buildWeeklyPlan(D);
            D.settings.itemsPerSession = 1;
            return plan.slots.map(s => ({
                skills: s.units.map(u => u.skill),
                min: s.min,
                sum: s.units.reduce((n, u) => n + unitMinutes(u), 0),
            }));
        }"""
        )
        assert res5 and all(
            len(s["skills"]) == 2 and len(set(s["skills"])) == 1 for s in res5
        ), f"two-unit sessions are not two units of one skill: {res5}"
        assert all(s["min"] == s["sum"] for s in res5), (
            f"session minutes are not the sum of its units: {res5}"
        )
        out["5_items_per_session"] = f"OK: {[(s['skills'], s['min']) for s in res5]}"

        # 6. One slot per scheduled day, and no repeated part on the same day.
        res6 = await page.evaluate(
            """() => {
            const old = D.settings.schedule;
            D.settings.schedule = [1,2,3,4,5,6,0].map(d => ({day: d, time: '15:30'}));
            D.diag.weakest = [7,5,6];
            D.errs = [1,2,3,4].map(() => ({date:'2026-10-25', code:'L-GAP', part:7, note:'x'}));
            const plan = buildWeeklyPlan(D);
            D.settings.schedule = old; D.errs = []; D.diag.weakest = [3,2,7];
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

        # 7. Each slot's reason is non-empty and names the skill it trains.
        res7 = await page.evaluate(
            """() => buildWeeklyPlan(D).slots.map(s => ({
                reason: s.reason,
                label: planSkillLabel(s.units[0].skill),
            }))"""
        )
        assert len(res7) >= 5, f"Expected >=5 reasons, got {res7}"
        for r in res7:
            assert isinstance(r["reason"], str) and r["reason"].strip(), (
                f"Empty reason: {r!r}"
            )
            assert r["label"] in r["reason"], f"Reason without its skill: {r!r}"
        out["7_reasons_con_skill"] = f"OK: {len(res7)} reasons name their skill"

        # UI: rendered rows, Regenerate and Start -> RESOURCES
        await page.click("nav button[data-view='plan']")
        rows = await page.eval_on_selector_all(
            "#wpRows .wp-row",
            "els => els.map(e => ({day: e.dataset.day, part: e.dataset.part,"
            " type: e.dataset.type, reason: (e.querySelector('.wp-reason')||{textContent:''}).textContent}))",
        )
        assert len(rows) == 5, f"Expected 5 rows in card, got {len(rows)}"
        assert all(r["reason"].strip() for r in rows), f"Empty reason in row: {rows}"
        assert await page.evaluate("!!document.getElementById('wpWhy')") is False, (
            "the removed 'Why this?' block is still in the DOM"
        )
        assert "why this" not in (
            await page.evaluate("document.getElementById('v-plan').innerText")
        ).lower(), "the removed 'Why this?' copy is still painted"
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
            " filter: RES_FILTER, papers: document.querySelectorAll('#resourcesList .res-paper').length})"
        )
        # Since the Practice/Resources split the sample papers filter lives on
        # the Resources screen, and that is where a plan row sends you.
        assert nav_state["view"] == "v-resources", f"Start did not navigate to RESOURCES: {nav_state}"
        assert nav_state["filter"] == {"type": "ue", "part": ue_part}, f"Filter not applied: {nav_state}"
        assert nav_state["papers"] == 1, f"Filter did not leave one paper: {nav_state}"
        out["ui_card_y_empezar"] = f"OK: rows=5, no why block, Start -> RESOURCES part {ue_part}"

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
