"""Continuous rotation tests across weeks for by-part and full-section modes.

Sessions cycle R&UE -> Listening -> Writing -> Speaking continuously without
resetting at week boundaries, anchored to logged sessions + D.sessionOffset.
Uses an isolated test user (pattern from test_plan.py) and never touches data/.
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

READ_PLAN_JS = """() => {
    const slots = (WEEK_PLAN && WEEK_PLAN.slots) || [];
    const upcoming = [...document.querySelectorAll('#planUpcomingPreview .up-row')].map(r => ({
        day: r.dataset.day,
        skill: r.dataset.skill || '',
        label: ((r.querySelector('.badge') || {}).textContent || '').trim(),
    }));
    const nextUp = [...document.querySelectorAll('#wpQueuePreview .wp-next')].map(r => ({
        day: r.dataset.day,
        units: (r.dataset.units || '').split(',').filter(Boolean),
    }));
    return {
        types: slots.map(s => s.type),
        skills: slots.map(s => (s.units && s.units[0]) ? s.units[0].skill : s.type),
        units: slots.map(s => (s.units || []).map(queueUnitLabel)),
        mins: slots.map(s => s.min),
        days: slots.map(s => s.day),
        upcoming,
        nextUp,
        weekBlock: (document.getElementById('wpWeekBlock') || {}).textContent || '',
    };
}"""


async def seed_plan(page, days, mode="by-part", log=None, per=1, offset=0):
    schedule = [{"day": d, "time": "15:30"} for d in days]
    await page.evaluate(
        """([schedule, mode, log, per, offset]) => {
            D.log = log.slice();
            D.errs = [];
            D.sessionOffset = offset;
            D.settings.schedule = schedule;
            D.settings.sessions = schedule;
            D.settings.rotationMode = mode;
            D.settings.itemsPerSession = per;
            save();
            refreshAll();
            renderPlan();
        }""",
        [schedule, mode, log or [], per, offset],
    )
    await page.wait_for_timeout(150)
    return await page.evaluate(READ_PLAN_JS)


async def main():
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))

        await page.goto(URL + "app", wait_until="load")
        await page.wait_for_function(
            "() => typeof load === 'function' && typeof buildWeeklyPlan === 'function'"
        )
        await page.wait_for_timeout(300)

        await page.evaluate(
            """() => {
            localStorage.clear();
            syncPush = () => {};
            syncPull = async () => null;
            const u = {id: 'test_rot_cont_ci', name: 'TestRotCont', color: '#1e3a8a', token: ''};
            localStorage.setItem('b2first_user', JSON.stringify(u));
            localStorage.setItem('ob_test_rot_cont_ci', '1');
            USER = u;
            D = load();
            D.onboarded = true;
            D.diag = %s;
            D.log = [];
            D.errs = [];
            D.sessionOffset = 0;
            hideAuthOverlay();
            hideOnboarding();
            setLang('en');
            refreshAll();
        }"""
            % DIAG_FIXTURE
        )
        await page.click("nav button[data-view='plan']")
        await page.wait_for_timeout(200)

        three_days = [1, 3, 5]  # Mon, Wed, Fri
        two_days = [1, 5]       # Mon, Fri

        # 1. by-part, 3 days: empty log -> ['rue','l','w']; 3 done -> ['sp','rue','l']
        bp3_empty = await seed_plan(page, three_days, mode="by-part", log=[], per=1)
        assert bp3_empty["skills"] == ["rue", "l", "w"], (
            f"by-part 3 days empty log wrong: {bp3_empty}"
        )
        assert bp3_empty["types"] == ["ue", "l", "w"], bp3_empty
        assert bp3_empty["units"] == [
            ["Reading part 1"],
            ["Listening part 1"],
            ["Writing essay"],
        ], bp3_empty["units"]

        bp3_log = [
            {"date": "2026-10-01", "type": "ue", "part": 1, "correct": 6, "total": 8, "min": 8},
            {"date": "2026-10-03", "type": "lp", "part": 1, "correct": 6, "total": 8, "min": 10},
            {"date": "2026-10-05", "type": "w", "kind": "Essay", "score": 14, "min": 40},
        ]
        bp3_after = await seed_plan(page, three_days, mode="by-part", log=bp3_log, per=1)
        assert bp3_after["skills"] == ["sp", "rue", "l"], (
            f"by-part 3 days after 3 sessions wrong: {bp3_after}"
        )
        assert bp3_after["types"] == ["sp", "ue", "l"], bp3_after
        assert bp3_after["units"] == [
            ["Speaking part 1"],
            ["Reading part 2"],
            ["Listening part 2"],
        ], bp3_after["units"]

        # itemsPerSession=2 keeps 2 consecutive units of the same skill and continues
        bp3_per2_empty = await seed_plan(page, three_days, mode="by-part", log=[], per=2)
        assert bp3_per2_empty["skills"] == ["rue", "l", "w"], bp3_per2_empty
        assert bp3_per2_empty["units"] == [
            ["Reading part 1", "Reading part 2"],
            ["Listening part 1", "Listening part 2"],
            ["Writing essay", "Writing article"],
        ], bp3_per2_empty["units"]

        bp3_per2_log = [
            {"date": "2026-10-01", "type": "ue", "part": 1, "min": 8},
            {"date": "2026-10-01", "type": "ue", "part": 2, "min": 8},
            {"date": "2026-10-03", "type": "lp", "part": 1, "min": 10},
            {"date": "2026-10-03", "type": "lp", "part": 2, "min": 10},
            {"date": "2026-10-05", "type": "w", "kind": "Essay", "min": 40},
            {"date": "2026-10-05", "type": "w", "kind": "Article", "min": 40},
        ]
        bp3_per2_after = await seed_plan(page, three_days, mode="by-part", log=bp3_per2_log, per=2)
        assert bp3_per2_after["skills"] == ["sp", "rue", "l"], bp3_per2_after
        assert bp3_per2_after["units"] == [
            ["Speaking part 1", "Speaking part 2"],
            ["Reading part 3", "Reading part 4"],
            ["Listening part 3", "Listening part 4"],
        ], bp3_per2_after["units"]

        out["1_by_part_3_days"] = {
            "empty": bp3_empty["skills"],
            "after_3": bp3_after["skills"],
            "per2_after_3": bp3_per2_after["units"],
        }

        # 2. full-section, 3 days: empty -> ['ue','l','w']; 3 done -> ['sp','ue','l']
        fs3_empty = await seed_plan(page, three_days, mode="full-section", log=[])
        assert fs3_empty["types"] == ["ue", "l", "w"], (
            f"full-section 3 days empty log wrong: {fs3_empty}"
        )
        assert fs3_empty["mins"] == [75, 40, 80], fs3_empty["mins"]

        fs3_log = [
            {"date": "2026-10-01", "type": "rue", "correct": 38, "total": 52, "min": 75},
            {"date": "2026-10-03", "type": "l", "correct": 22, "total": 30, "min": 40},
            {"date": "2026-10-05", "type": "fw", "s1": 14, "s2": 15, "min": 80},
        ]
        fs3_after3 = await seed_plan(page, three_days, mode="full-section", log=fs3_log)
        assert fs3_after3["types"] == ["sp", "ue", "l"], (
            f"full-section 3 days after 3 sessions wrong: {fs3_after3}"
        )
        assert fs3_after3["mins"] == [14, 75, 40], fs3_after3["mins"]

        # After 4 full sessions (including Full Speaking), wraps cleanly back to Full R&UE
        fs4_log = fs3_log + [
            {"date": "2026-10-08", "type": "sp", "part": 0, "full": True, "parts": [1, 2, 3, 4], "min": 14},
        ]
        fs3_after4 = await seed_plan(page, three_days, mode="full-section", log=fs4_log)
        assert fs3_after4["types"] == ["ue", "l", "w"], (
            f"full-section 3 days after 4 sessions wrong: {fs3_after4}"
        )

        # sessionOffset and resetSessionOffset work in full-section too
        fs3_off1 = await seed_plan(page, three_days, mode="full-section", log=[], offset=1)
        assert fs3_off1["types"] == ["l", "w", "sp"], (
            f"full-section offset=1 did not reach Speaking: {fs3_off1}"
        )
        await page.evaluate("resetSessionOffset()")
        await page.wait_for_timeout(150)
        fs3_reset = await page.evaluate(READ_PLAN_JS)
        assert fs3_reset["types"] == ["ue", "l", "w"], (
            f"resetSessionOffset did not restore full-section: {fs3_reset}"
        )

        out["2_full_section_3_days"] = {
            "empty": fs3_empty["types"],
            "after_3": fs3_after3["types"],
            "after_4": fs3_after4["types"],
            "offset_1": fs3_off1["types"],
        }

        # 3. by-part, 2 days: empty -> ['rue','l']; 2 done -> ['w','sp']
        bp2_empty = await seed_plan(page, two_days, mode="by-part", log=[], per=1)
        assert bp2_empty["skills"] == ["rue", "l"], (
            f"by-part 2 days empty log wrong: {bp2_empty}"
        )
        bp2_log = [
            {"date": "2026-10-01", "type": "ue", "part": 1, "min": 8},
            {"date": "2026-10-05", "type": "lp", "part": 1, "min": 10},
        ]
        bp2_after = await seed_plan(page, two_days, mode="by-part", log=bp2_log, per=1)
        assert bp2_after["skills"] == ["w", "sp"], (
            f"by-part 2 days after 2 sessions wrong: {bp2_after}"
        )
        out["3_by_part_2_days"] = {
            "empty": bp2_empty["skills"],
            "after_2": bp2_after["skills"],
        }

        # 4. "What comes next" matches the plan's next 3 types in both modes
        #    and both before and after 3 logged sessions.
        bp_next_empty = [r["skill"] for r in bp3_empty["upcoming"][:3]]
        bp_next_after = [r["skill"] for r in bp3_after["upcoming"][:3]]
        assert bp_next_empty == bp3_empty["skills"] == ["rue", "l", "w"], (
            f"What comes next (by-part empty) drifted from plan: {bp_next_empty} vs {bp3_empty['skills']}"
        )
        assert bp_next_after == bp3_after["skills"] == ["sp", "rue", "l"], (
            f"What comes next (by-part after 3) drifted from plan: {bp_next_after} vs {bp3_after['skills']}"
        )
        # 4th upcoming row in empty 3-day by-part is Speaking
        assert bp3_empty["upcoming"][3]["skill"] == "sp", bp3_empty["upcoming"]

        fs_next_empty = [r["skill"] for r in fs3_empty["upcoming"][:3]]
        fs_next_after = [r["skill"] for r in fs3_after3["upcoming"][:3]]
        assert fs_next_empty == fs3_empty["types"] == ["ue", "l", "w"], (
            f"What comes next (full-section empty) drifted from plan: {fs_next_empty} vs {fs3_empty['types']}"
        )
        assert fs_next_after == fs3_after3["types"] == ["sp", "ue", "l"], (
            f"What comes next (full-section after 3) drifted from plan: {fs_next_after} vs {fs3_after3['types']}"
        )
        # 4th upcoming row in empty 3-day full-section is Speaking
        assert fs3_empty["upcoming"][3]["skill"] == "sp", fs3_empty["upcoming"]

        out["4_what_comes_next_matches_plan"] = {
            "by_part_empty_3": bp_next_empty,
            "by_part_after3_3": bp_next_after,
            "full_section_empty_3": fs_next_empty,
            "full_section_after3_3": fs_next_after,
        }

        # 5. Mobile 390x844 without horizontal overflow on Plan view
        await page.set_viewport_size({"width": 390, "height": 844})
        await seed_plan(page, three_days, mode="by-part", log=bp3_log, per=1)
        await page.wait_for_timeout(150)
        ov_bp = await page.evaluate(
            "() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})"
        )
        assert ov_bp["sw"] <= ov_bp["iw"], f"Mobile 390x844 overflow in by-part: {ov_bp}"

        await seed_plan(page, three_days, mode="full-section", log=fs3_log)
        await page.wait_for_timeout(150)
        ov_fs = await page.evaluate(
            "() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})"
        )
        assert ov_fs["sw"] <= ov_fs["iw"], f"Mobile 390x844 overflow in full-section: {ov_fs}"
        out["5_mobile_390x844"] = {"by_part": ov_bp, "full_section": ov_fs}

        # Clean up isolated test user
        await page.evaluate(
            "localStorage.removeItem('b2first_tracker_v1_test_rot_cont_ci');"
            " localStorage.removeItem('b2first_user');"
        )
        assert errs == [], f"JS errors: {errs}"
        out["6_js_errors"] = errs
        await browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
