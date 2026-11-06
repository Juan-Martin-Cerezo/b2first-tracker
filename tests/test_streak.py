import asyncio
import json
from playwright.async_api import async_playwright

from helpers import isolated_server

URL = isolated_server() + "/"


async def main():
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 360, "height": 780},
            is_mobile=True,
            has_touch=True,
        )
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))

        await page.goto(URL + "app", wait_until="networkidle")

        # Set up an isolated test user in localStorage without touching the owner's data/
        await page.evaluate(
            """() => {
            syncPush = () => {};
            syncPull = async () => null;
            const testUser = {id: 'test_streak_ci', name: 'TestStreak', color: '#1e3a8a', token: ''};
            localStorage.setItem('b2first_user', JSON.stringify(testUser));
            localStorage.setItem('ob_test_streak_ci', '1');
            USER = testUser;
            D = load();
            D.onboarded = true;
            hideAuthOverlay();
            hideOnboarding();
            refreshAll();
        }"""
        )

        # (a) Empty log -> No streak (the top-bar pill is the remaining surface)
        res_a = await page.evaluate(
            """() => {
            D.log = [];
            D.examDates = [];
            D.settings.streakFreeze = 1;
            D.settings.weekGoal = 5;
            save(); refreshAll();
            return {
                st: calcStreak(),
                text: document.getElementById('streakTopNum').textContent.trim(),
                title: document.getElementById('streakTopPill').getAttribute('title') || ''
            };
        }"""
        )
        assert res_a["st"]["current"] == 0, f"Expected 0, got {res_a}"
        assert res_a["text"] == "0", f"Expected the pill to read 0, got {res_a['text']!r}"
        assert res_a["title"], f"Pill lost its label: {res_a}"
        out["a_empty"] = "OK: pill reads 0"

        # (b) Today + yesterday -> 2
        res_b = await page.evaluate(
            """() => {
            const t0 = dayKey(new Date());
            const t1 = _addDaysKey(t0, -1);
            D.log = [
                {type:'ue', date:t1, correct:12, total:20, min:50},
                {type:'lp', date:t0, correct:8, total:10, min:40}
            ];
            save(); refreshAll();
            return {
                st: calcStreak(),
                text: document.getElementById('streakTopNum').textContent.trim()
            };
        }"""
        )
        assert res_b["st"]["current"] == 2, f"Expected current=2, got {res_b}"
        assert res_b["st"]["todayDone"] is True
        assert res_b["st"]["atRisk"] is False
        assert res_b["text"] == "2", f"Expected the pill to read 2, got {res_b['text']!r}"
        out["b_today_yesterday"] = f"OK: current={res_b['st']['current']} ({res_b['text']})"

        # (c) 1-day gap with a shield available -> streak alive and 🛡
        res_c = await page.evaluate(
            """() => {
            const t0 = dayKey(new Date());
            const t2 = _addDaysKey(t0, -2);
            const t3 = _addDaysKey(t0, -3);
            D.settings.streakFreeze = 1;
            D.log = [
                {type:'ue', date:t0, correct:15, total:20, min:50},
                {type:'lp', date:t2, correct:8, total:10, min:40},
                {type:'w',  date:t3, kind:'Essay', score:16, correct:16, total:20, min:35}
            ];
            save(); refreshAll();
            return {
                st: calcStreak(),
                pill: document.getElementById('streakTopNum').textContent.trim()
            };
        }"""
        )
        assert res_c["st"]["current"] == 3, f"Expected current=3 with shield, got {res_c}"
        assert res_c["st"]["freezeUsed"] == 1, f"Expected freezeUsed=1, got {res_c}"
        assert res_c["pill"] == "3", f"Pill disagrees with the shield count: {res_c}"
        out["c_freeze_1day"] = f"OK: current={res_c['st']['current']}, freezeUsed={res_c['st']['freezeUsed']}"

        # (d) 2-day gap -> broken
        res_d = await page.evaluate(
            """() => {
            const t0 = dayKey(new Date());
            const t3 = _addDaysKey(t0, -3);
            const t4 = _addDaysKey(t0, -4);
            D.settings.streakFreeze = 1;
            D.log = [
                {type:'ue', date:t3, correct:15, total:20, min:50},
                {type:'lp', date:t4, correct:8, total:10, min:40}
            ];
            save(); refreshAll();
            const cutNoToday = calcStreak();

            D.log.push({type:'ue', date:t0, correct:14, total:20, min:50});
            save(); refreshAll();
            const cutWithToday = calcStreak();
            return {cutNoToday, cutWithToday};
        }"""
        )
        assert res_d["cutNoToday"]["current"] == 0, f"Expected 0 after 2-day gap, got {res_d}"
        assert res_d["cutWithToday"]["current"] == 1, f"Expected 1 (previous cut) after 2-day gap, got {res_d}"
        out["d_gap_2days_cut"] = f"OK: noToday={res_d['cutNoToday']['current']}, withToday={res_d['cutWithToday']['current']}"

        # (e) Future date ignored
        res_e = await page.evaluate(
            """() => {
            const t0 = dayKey(new Date());
            const future = _addDaysKey(t0, 5);
            D.log = [
                {type:'ue', date:future, correct:18, total:20, min:50},
                {type:'ue', date:t0, correct:14, total:20, min:50}
            ];
            save(); refreshAll();
            return {
                days: Array.from(sessionDays()),
                st: calcStreak()
            };
        }"""
        )
        assert len(res_e["days"]) == 1, f"Future date not ignored: {res_e}"
        assert res_e["st"]["current"] == 1
        out["e_future_ignored"] = f"OK: days={res_e['days']}, current={res_e['st']['current']}"

        # (f) Correct all-time record (longest)
        res_f = await page.evaluate(
            """() => {
            const t0 = dayKey(new Date());
            const t1 = _addDaysKey(t0, -1);
            D.log = [
                {type:'ue', date:'2026-05-01', correct:15, total:20, min:50},
                {type:'ue', date:'2026-05-02', correct:15, total:20, min:50},
                {type:'ue', date:'2026-05-03', correct:15, total:20, min:50},
                {type:'ue', date:'2026-05-04', correct:15, total:20, min:50},
                {type:'ue', date:'2026-05-05', correct:15, total:20, min:50},
                {type:'ue', date:t1, correct:15, total:20, min:50},
                {type:'ue', date:t0, correct:15, total:20, min:50}
            ];
            save(); refreshAll();
            return {
                st: calcStreak()
            };
        }"""
        )
        assert res_f["st"]["current"] == 2 and res_f["st"]["longest"] == 5, f"Expected 2/5, got {res_f}"
        out["f_longest_record"] = f"OK: current={res_f['st']['current']}, longest={res_f['st']['longest']}"

        # (g) Correct weekCount + 3-tap Quick-Log at 360px
        res_g = await page.evaluate(
            """() => {
            const t0 = dayKey(new Date());
            const dt = _parseLocalDay(t0);
            const dow = (dt.getDay() + 6) % 7;
            const mon = _addDaysKey(t0, -dow);
            const prevWeek = _addDaysKey(mon, -3);
            D.log = [
                {type:'ue', date:prevWeek, correct:15, total:20, min:50},
                {type:'ue', date:mon, correct:15, total:20, min:50}
            ];
            save(); refreshAll();
            const before = calcStreak().weekCount;

            openQuickLog();
            qlSetType('lp');
            qlPickRange(6, 10);
            qlSave();
            const st = calcStreak();
            const after = st.weekCount;
            const expectedAfter = (mon === t0) ? 1 : 2;
            return {before, after, expectedAfter, current: st.current,
                    pill: document.getElementById('streakTopNum').textContent.trim()};
        }"""
        )
        assert res_g["before"] == 1, f"Expected weekCount=1 before quicklog, got {res_g}"
        assert res_g["after"] == res_g["expectedAfter"], f"Expected weekCount={res_g['expectedAfter']}, got {res_g}"
        assert res_g["pill"] == str(res_g["current"]), f"Pill out of date: {res_g}"
        out["g_week_count"] = f"OK: weekCount={res_g['after']}"

        # Clean up the test user's localStorage
        await page.evaluate("localStorage.removeItem('b2first_tracker_v1_test_streak_ci'); localStorage.removeItem('b2first_user');")
        assert len(errs) == 0, f"JS errors: {errs}"
        out["js_errors"] = errs
        await browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
