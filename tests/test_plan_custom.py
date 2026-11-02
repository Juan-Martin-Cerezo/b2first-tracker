"""Phase 45: one sentence per day in the PLAN surface.

Runs standalone against an isolated server (helpers.isolated_server) and the
shared throwaway account. Assertions use buildWeeklyPlan() evaluated in the
page plus the rendered DOM. Screenshots land in tests/out/ (gitignored).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = Path(__file__).with_name("out")
OUT.mkdir(exist_ok=True)

BASE_PROFILE = """{
    examDate:null, examDateUnknown:true, targetGrade:'B',
    skills:{rue:3,w:2,l:3,sp:2}, hoursWeek:6,
    days:['mon','wed','sat'], struggles:[], strugglesDeclared:[],
    declaredAt:'2026-10-30T12:00:00Z'
}"""


def reset(pg, week=None, extra=None):
    settings = dict(extra or {})
    settings["week"] = week or {}
    pg.evaluate(
        """(settings) => {
        D.profile = %s;
        D.diag = null;
        D.log = [];
        D.errs = [];
        D.examDates = [];
        D.settings = Object.assign(JSON.parse(JSON.stringify(SETTINGS_DEFAULT)), settings);
        migratePlanSettings(D.settings);
        save();
        refreshAll();
    }"""
        % BASE_PROFILE,
        settings,
    )


def main():
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL + "app", wait_until="networkidle")
        login_owner(pg, URL)
        pg.wait_for_timeout(300)

        # 1. All days auto: only non-off days get sessions, every row is Suggested.
        reset(pg)
        pg.evaluate("showView('plan')")
        pg.wait_for_timeout(200)
        res1 = pg.evaluate(
            """() => {
            const plan = buildWeeklyPlan(D);
            const week = planWeek(D.settings);
            return {
                slots: plan.slots.map(sl => ({dayKey:sl.dayKey, origin:sl.origin})),
                offOk: plan.slots.every(sl => week[sl.dayKey].mode !== 'off'),
                rows: document.querySelectorAll('#wpRows .wp-row').length,
            };
        }"""
        )
        assert res1["slots"], f"an all-auto week produced no sessions: {res1}"
        assert all(s["origin"] == "auto" for s in res1["slots"]), f"non-auto slot: {res1}"
        assert res1["offOk"], f"a session landed on an off day: {res1}"
        assert res1["rows"] == len(res1["slots"]), f"card rows mismatch: {res1}"
        out["1_todo_auto"] = f"OK: {res1['rows']} auto rows, no off day"

        # 2. Monday custom whole-UoE: one session, 30 min, 18:00, Yours.
        reset(
            pg,
            week={
                "mon": {
                    "mode": "custom",
                    "preset": "ue_full",
                    "min": 30,
                    "time": "18:00",
                }
            },
        )
        pg.evaluate("showView('plan')")
        pg.wait_for_timeout(150)
        res2 = pg.evaluate(
            """() => {
            const plan = buildWeeklyPlan(D);
            const mon = plan.slots.filter(sl => sl.dayKey === 'mon');
            const row = document.querySelector('#wpRows .wp-row[data-day-key="mon"]');
            return {
                mon: mon.map(sl => ({dayKey:sl.dayKey,min:sl.min,time:sl.time,type:sl.type,part:sl.part,items:sl.items,origin:sl.origin})),
                title: mon.length ? planSlotLabel(mon[0]) : '',
                week: D.settings.week.mon
            };
        }"""
        )
        assert len(res2["mon"]) == 1, f"expected one Monday session: {res2}"
        mon = res2["mon"][0]
        assert mon["type"] == "ue" and mon["part"] is None, f"not the whole UoE paper: {mon}"
        assert mon["min"] == 30, f"day minutes ignored: {mon}"
        assert mon["time"] == "18:00", f"day time ignored: {mon}"
        assert mon["origin"] == "custom", f"custom origin lost: {mon}"
        assert "whole paper" in res2["title"].lower(), f"title does not name the paper: {res2['title']!r}"
        assert res2["week"]["min"] == 30 and res2["week"]["time"] == "18:00", f"week row not stored: {res2}"
        before = res2["mon"]
        pg.click("#wpRegenBtn")
        pg.wait_for_function(
            "document.getElementById('wpRegenStatus').textContent.indexOf('Plan rebuilt') >= 0",
            timeout=5000,
        )
        after = pg.evaluate(
            """() => {
            const mon = buildWeeklyPlan(D).slots.filter(sl => sl.dayKey === 'mon');
            return mon.map(sl => ({dayKey:sl.dayKey,min:sl.min,time:sl.time,type:sl.type,part:sl.part,items:sl.items,origin:sl.origin}));
        }"""
        )
        assert after == before, f"Regenerate changed a custom Monday:\n{before}\n!=\n{after}"
        out["2_lunes_custom"] = f"OK: UoE whole paper, {mon['min']} min at {mon['time']}, Yours, regen-safe"

        # 3. Wednesday off: no Wednesday session, even after Regenerate.
        reset(pg, week={"wed": {"mode": "off"}})
        pg.evaluate("showView('plan')")
        pg.wait_for_timeout(150)
        assert pg.evaluate(
            "() => buildWeeklyPlan(D).slots.filter(sl => sl.dayKey === 'wed').length"
        ) == 0, "off Wednesday received a session"
        pg.click("#wpRegenBtn")
        pg.wait_for_function(
            "document.getElementById('wpRegenStatus').textContent.indexOf('Plan rebuilt') >= 0",
            timeout=5000,
        )
        assert pg.evaluate(
            "() => buildWeeklyPlan(D).slots.filter(sl => sl.dayKey === 'wed').length"
        ) == 0, "Regenerate added a Wednesday session on a rest day"
        assert pg.evaluate(
            "() => document.querySelectorAll('#wpRows .wp-row[data-day-key=\"wed\"]').length"
        ) == 0, "rest day leaked into the week card"
        assert pg.evaluate(
            "() => document.querySelector('#planCustomBody select[data-week-day=\"wed\"]').value"
        ) == "off", "the Wednesday row no longer says rest day"
        out["3_miercoles_off"] = "OK: no Wednesday session before or after Regenerate"

        # 4. Thursday specific parts: exactly UoE 4 + Listening 2 in one session.
        reset(
            pg,
            week={
                "thu": {
                    "mode": "custom",
                    "preset": "parts",
                    "parts": {"ue": [4], "l": [2], "sp": [], "w": []},
                    "min": 45,
                }
            },
        )
        res4 = pg.evaluate(
            """() => {
            const thu = buildWeeklyPlan(D).slots.filter(sl => sl.dayKey === 'thu');
            return {n: thu.length, items: thu.length ? thu[0].items : [], title: thu.length ? planSlotLabel(thu[0]) : ''};
        }"""
        )
        assert res4["n"] == 1, f"expected one Thursday session: {res4}"
        items = sorted((it["type"], it["part"]) for it in res4["items"])
        assert items == [("l", 2), ("ue", 4)], f"Thursday parts are not exactly UoE 4 + L 2: {res4}"
        assert "UoE" in res4["title"] and "Listening" in res4["title"], f"title missing a paper: {res4}"
        out["4_jueves_partes"] = f"OK: {items}"

        # 5. Tuesday ue_l: one session covering both papers at the day's min.
        reset(
            pg,
            week={
                "tue": {
                    "preset": "ue_l",
                    "min": 60,
                    "time": "17:00",
                }
            },
        )
        res5 = pg.evaluate(
            """() => {
            const tue = buildWeeklyPlan(D).slots.filter(sl => sl.dayKey === 'tue');
            return {n: tue.length, min: tue.length ? tue[0].min : null,
                    items: tue.length ? tue[0].items : [],
                    types: tue.length ? tue[0].items.map(it => it.type) : []};
        }"""
        )
        assert res5["n"] == 1, f"expected one Tuesday session: {res5}"
        assert res5["types"] == ["ue", "l"], f"ue_l did not cover both papers: {res5}"
        assert all(it["part"] is None for it in res5["items"]), f"whole papers expected: {res5}"
        assert res5["min"] == 60, f"day minutes ignored: {res5}"
        out["5_martes_ue_l"] = f"OK: one session, {res5['min']} min, {res5['types']}"

        # 6. Legacy customSlots migrate into week on load, old keys disappear.
        res6 = pg.evaluate(
            """() => {
            const doc = JSON.parse(localStorage.getItem(userKey())) || {};
            doc.settings = {
                lang:'en', slotMin:45,
                planMode:'custom', customRotate:true,
                rueParts:[1,2,3], lParts:[1,2], spParts:[1], wKinds:['Email'],
                customSlots:[
                    {day:'tue', time:'18:30', min:40, type:'ue', part:3, kind:null, timed:false},
                    {day:'thu', time:'', min:30, type:'l', part:2, kind:null, timed:false}
                ]
            };
            doc.profile = null; doc.diag = null; doc.log = []; doc.errs = [];
            localStorage.setItem(userKey(), JSON.stringify(doc));
            D = load();
            const s = D.settings;
            return {
                tue: s.week.tue, thu: s.week.thu,
                old: ['customSlots','planMode','customRotate','rueParts','lParts','spParts','wKinds']
                    .filter(k => k in s),
                plan: buildWeeklyPlan(D).slots.map(sl => ({dayKey:sl.dayKey,origin:sl.origin,items:sl.items}))
            };
        }"""
        )
        assert not res6["old"], f"legacy keys survived the migration: {res6['old']}"
        assert res6["tue"]["mode"] == "custom", f"Tuesday did not migrate: {res6['tue']}"
        assert res6["tue"]["min"] == 40 and res6["tue"]["time"] == "18:30", f"slot min/time lost: {res6['tue']}"
        assert 3 in res6["tue"]["parts"]["ue"], f"Tuesday part lost: {res6['tue']}"
        assert res6["thu"]["min"] == 30 and res6["thu"]["parts"]["l"] == [2], f"Thursday not migrated: {res6['thu']}"
        assert len(res6["plan"]) == 2, f"migrated week did not build: {res6['plan']}"
        assert {s["dayKey"] for s in res6["plan"]} == {"tue", "thu"}, f"wrong migrated days: {res6['plan']}"
        out["6_migracion"] = f"OK: {res6['tue']['parts']} / {res6['thu']['parts']}, old keys gone"

        # 7. One control per concern: the old ids and widgets are gone.
        reset(pg)
        pg.evaluate("showView('plan')")
        pg.wait_for_timeout(150)
        res7 = pg.evaluate(
            """() => {
            const old = ['pADay','pBDay','pATime','pBTime','scheduleRowsContainer',
                         'pcSlotMin_plan','pcWeekGoal_plan','pcPreviewBody_plan','pWeekGoal'];
            return {
                present: old.filter(id => !!document.getElementById(id)),
                rows: document.querySelectorAll('#planCustomBody .wk-row').length,
                selects: document.querySelectorAll('#planCustomBody select.wk-select').length,
                legacy: document.querySelectorAll('#planCustomBody [data-pc-field], #planCustomBody .pc-table, #planCustomBody .chip-btn').length,
                radios: document.querySelectorAll('#planCustomBody input[name^="pcMode"]').length,
                order: Array.from(document.getElementById('v-plan').children).map(el => el.id).filter(Boolean)
            };
        }"""
        )
        assert res7["present"] == [], f"old controls still in the DOM: {res7['present']}"
        assert res7["rows"] == 7 and res7["selects"] == 7, f"not seven day rows: {res7}"
        assert res7["legacy"] == 0, f"legacy editor markup remains: {res7}"
        assert res7["radios"] == 0, f"mode radio remains: {res7}"
        assert res7["order"] == ["examCountdown", "weeklyPlanCard", "planCustom", "planTuning", "planAccount"], (
            f"PLAN tab order changed: {res7['order']}"
        )
        out["7_un_control_por_dia"] = f"OK: {res7['rows']} rows, old ids absent, order={res7['order']}"

        # 8. Mobile 360x800: the week card never overflows horizontally.
        pg.set_viewport_size({"width": 360, "height": 800})
        pg.evaluate("showView('plan')")
        pg.wait_for_timeout(150)
        pg.select_option('#planCustomBody select[data-week-day="mon"]', "parts")
        pg.wait_for_timeout(200)
        overflow = pg.evaluate(
            """() => {
            const el = document.getElementById('planCustom');
            return {sw: el.scrollWidth, cw: el.clientWidth,
                    doc: document.documentElement.scrollWidth, win: window.innerWidth,
                    parts: document.querySelectorAll('#planCustomBody .wk-parts').length};
        }"""
        )
        assert overflow["parts"] == 1, f"parts control did not appear: {overflow}"
        assert overflow["sw"] <= overflow["cw"] + 1, f"#planCustom overflows at 360px: {overflow}"
        assert overflow["doc"] <= overflow["win"] + 1, f"page overflows at 360px: {overflow}"
        out["8_movil_360"] = f"OK: {overflow['sw']} <= {overflow['cw']}"

        # Screenshots: desktop dark, mobile 390, and a mixed Suggested/Yours card.
        reset(
            pg,
            week={
                "mon": {"mode": "custom", "preset": "ue_full", "min": 30, "time": "18:00"},
                "wed": {"mode": "off"},
                "thu": {"mode": "custom", "preset": "parts",
                        "parts": {"ue": [4], "l": [2], "sp": [], "w": []}, "min": 45},
            },
        )
        pg.set_viewport_size({"width": 1280, "height": 900})
        pg.evaluate("applyTheme('dark'); showView('plan'); window.scrollTo(0,0)")
        pg.wait_for_timeout(250)
        pg.screenshot(path=str(OUT / "plan45_desktop_dark.png"), full_page=True)
        pg.locator("#planCustom").screenshot(path=str(OUT / "plan45_week_rows.png"))
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.evaluate(
            "showView('plan'); document.getElementById('planCustom')"
            ".scrollIntoView({block:'start'}); window.scrollBy(0,-70)"
        )
        pg.wait_for_timeout(250)
        pg.screenshot(path=str(OUT / "plan45_mobile_390.png"))
        pg.evaluate("applyTheme('light')")

        assert errs == [], f"JS errors: {errs}"
        out["errores_js"] = errs
        out["screenshots"] = ["plan45_desktop_dark.png", "plan45_mobile_390.png"]
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
