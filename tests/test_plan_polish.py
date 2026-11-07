"""Phase 123: Plan polish — exam date row, top action grid, and Week plan summary.

Verifies at 320, 768, and 1280 px on #v-plan:
1. Exam countdown card (#examCountdown):
   - Exactly one primary action (button with brand background); 'Set your exam date'
     (onclick="openIntake()") is conserved as a tertiary text button (transparent background).
   - EXAM DATE label sits above #examDateInput and is left-aligned with its left edge.
   - #examDateInput and the primary action ('Save date') share the same height (±1 px)
     and, at >= 480 px, the same baseline (±2 px).
   - At <= 480 px (320 px), the row stacks with #examDateInput on top at full width and
     'Save date' below at full width.
2. Top action grid (.plan-actions):
   - All four buttons ('Edit my intake', 'Replay the app tour', 'Export JSON', 'Import Backup')
     have the exact same width (±1 px) and uniform height (48 px).
   - Uniform gap from the spacing scale (--s3 = 12 px), 2 columns at >= 640 px and full width on mobile.
   - Icon on the left and label text aligned to the same horizontal offset across all four buttons.
3. Week plan summary (#wpSummary, #wpWeekBlock, #wpRegenBtn):
   - #wpSummary has font-weight <= 500 and font-size equal to --t-body; only its figures are 600.
   - #wpRegenBtn ('Regenerate') is a tertiary button aligned to the right of the header with a
     scale gap (--s3) from the title.
4. Zero horizontal scroll and zero control/card overlaps at every width.
5. Screenshots saved to tests/out/plan_polish_320.png, plan_polish_768.png, plan_polish_1280.png.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from helpers import isolated_server, login_owner

OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WIDTHS = (320, 768, 1280)

SEED_JS = """
() => {
    const wd = new Date().getDay();
    const nextWd = (wd + 3) % 7;
    D.profile = {
        examDate: null,
        targetGrade: 'B',
        skills: {rue: 3, w: 3, l: 3, sp: 3},
        hoursWeek: 4,
        days: [wd, nextWd],
        struggles: [],
        strugglesDeclared: [],
    };
    D.examDates = [];
    D.diag = null;
    D.sessionOffset = 0;
    D.weekOverrides = {};
    D.settings.rotationMode = 'by-part';
    D.settings.itemsPerSession = 2;
    D.settings.schedule = [{day: wd, time: '15:30'}, {day: nextWd, time: '13:00'}];
    D.settings.sessions = D.settings.schedule.slice();
    save();
    refreshAll();
}
"""

MEASURE_JS = """
() => {
    const doc = document.documentElement;
    const root = document.getElementById('v-plan');
    const isVisible = el => {
        if (!el) return false;
        let cur = el;
        while (cur && cur !== doc) {
            const cs = getComputedStyle(cur);
            if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
            cur = cur.parentElement;
        }
        const r = el.getBoundingClientRect();
        return r.width > 0.5 && r.height > 0.5;
    };

    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d');
    const toRgba = color => {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 1, 1);
        const d = ctx.getImageData(0, 0, 1, 1).data;
        return [d[0], d[1], d[2], Math.round((d[3] / 255) * 100) / 100];
    };

    // Resolve --t-body in pixels
    const probe = document.createElement('span');
    probe.style.cssText = 'position:absolute;visibility:hidden;font-size:var(--t-body)';
    document.body.appendChild(probe);
    const tBodyPx = Math.round(parseFloat(getComputedStyle(probe).fontSize) * 100) / 100;
    probe.remove();

    // A. Exam countdown card
    const examCard = document.getElementById('examCountdown');
    const examRow = examCard.querySelector('.exam-date-row');
    const examRowRect = examRow.getBoundingClientRect();
    const examInput = document.getElementById('examDateInput');
    const examLabel = examCard.querySelector('label[for="examDateInput"]');
    const examInputRect = examInput.getBoundingClientRect();
    const examLabelRect = examLabel.getBoundingClientRect();
    const examLabelCS = getComputedStyle(examLabel);

    const examBtns = Array.from(examCard.querySelectorAll('button')).filter(isVisible).map(b => {
        const r = b.getBoundingClientRect();
        const cs = getComputedStyle(b);
        const bg = toRgba(cs.backgroundColor);
        const isPrimary = bg[3] > 0.1;
        return {
            text: (b.innerText || '').trim(),
            onclick: b.getAttribute('onclick') || '',
            cls: b.className,
            isPrimary,
            bgAlpha: bg[3],
            left: r.left,
            right: r.right,
            top: r.top,
            bottom: r.bottom,
            width: r.width,
            height: r.height,
            centerY: (r.top + r.bottom) / 2,
        };
    });

    // B. Top action grid
    const actionsGrid = root.querySelector('.plan-actions');
    const actionsGridRect = actionsGrid.getBoundingClientRect();
    const actionsGridCS = getComputedStyle(actionsGrid);
    const actionBtns = Array.from(actionsGrid.querySelectorAll('button')).filter(isVisible).map(b => {
        const r = b.getBoundingClientRect();
        const ico = b.querySelector('.btn-ico');
        const lbl = b.querySelector('.btn-label');
        const ir = ico ? ico.getBoundingClientRect() : null;
        const lr = lbl ? lbl.getBoundingClientRect() : null;
        return {
            text: (b.innerText || '').trim(),
            left: r.left,
            right: r.right,
            top: r.top,
            bottom: r.bottom,
            width: r.width,
            height: r.height,
            icoOffset: ir ? (ir.left - r.left) : null,
            lblOffset: lr ? (lr.left - r.left) : null,
            icoBeforeLbl: (ir && lr) ? (ir.right <= lr.left + 1) : false,
        };
    });

    // C. Week plan summary & header
    const wpCard = document.getElementById('weeklyPlanCard');
    const wpHead = wpCard.querySelector('.plan-card-head');
    const wpHeadRect = wpHead.getBoundingClientRect();
    const wpHeadCS = getComputedStyle(wpHead);
    const wpTitle = wpHead.querySelector('h2');
    const wpTitleRect = wpTitle.getBoundingClientRect();
    const wpRegen = document.getElementById('wpRegenBtn');
    const wpRegenRect = wpRegen.getBoundingClientRect();
    const wpRegenCS = getComputedStyle(wpRegen);
    const wpRegenBg = toRgba(wpRegenCS.backgroundColor);

    const wpSummary = document.getElementById('wpSummary');
    const wpSummaryCS = getComputedStyle(wpSummary);
    const wpSummaryFigures = Array.from(wpSummary.querySelectorAll('b, strong')).map(el => ({
        text: el.textContent.trim(),
        fontWeight: parseInt(getComputedStyle(el).fontWeight, 10),
    }));

    const wpWeekBlock = document.getElementById('wpWeekBlock');
    const wpWeekBlockCS = getComputedStyle(wpWeekBlock);

    // D. Overlap check among interactive controls in #v-plan
    const controls = Array.from(root.querySelectorAll('button, input, select')).filter(isVisible);
    const overlaps = [];
    for (let i = 0; i < controls.length; i++) {
        for (let j = i + 1; j < controls.length; j++) {
            const a = controls[i], b = controls[j];
            if (a.contains(b) || b.contains(a)) continue;
            const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
            const ox = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
            const oy = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
            if (ox > 1 && oy > 1) {
                overlaps.push({
                    a: a.id || a.textContent.trim().slice(0, 25),
                    b: b.id || b.textContent.trim().slice(0, 25),
                    ox: Math.round(ox),
                    oy: Math.round(oy),
                });
            }
        }
    }

    return {
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        tBodyPx,
        exam: {
            rowWidth: examRowRect.width,
            input: {
                left: examInputRect.left,
                right: examInputRect.right,
                top: examInputRect.top,
                bottom: examInputRect.bottom,
                width: examInputRect.width,
                height: examInputRect.height,
                centerY: (examInputRect.top + examInputRect.bottom) / 2,
            },
            label: {
                left: examLabelRect.left,
                bottom: examLabelRect.bottom,
                textAlign: examLabelCS.textAlign,
            },
            buttons: examBtns,
        },
        actions: {
            gridWidth: actionsGridRect.width,
            rowGap: Math.round(parseFloat(actionsGridCS.rowGap) || 0),
            colGap: Math.round(parseFloat(actionsGridCS.columnGap) || 0),
            buttons: actionBtns,
        },
        weekPlan: {
            headGap: Math.round(parseFloat(wpHeadCS.columnGap) || parseFloat(wpHeadCS.gap) || 0),
            headRight: wpHeadRect.right,
            titleRight: wpTitleRect.right,
            regen: {
                left: wpRegenRect.left,
                right: wpRegenRect.right,
                height: Math.round(wpRegenRect.height),
                bgAlpha: wpRegenBg[3],
            },
            summary: {
                text: wpSummary.textContent.trim(),
                fontSize: Math.round(parseFloat(wpSummaryCS.fontSize) * 100) / 100,
                fontWeight: parseInt(wpSummaryCS.fontWeight, 10),
                figures: wpSummaryFigures,
            },
            weekBlock: {
                fontSize: Math.round(parseFloat(wpWeekBlockCS.fontSize) * 100) / 100,
                fontWeight: parseInt(wpWeekBlockCS.fontWeight, 10),
            },
        },
        overlaps,
    };
}
"""


def main():
    url = isolated_server() + "/"
    report = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url + "app", wait_until="networkidle")
        login_owner(page, url)
        page.evaluate("setLang('en')")
        page.wait_for_timeout(200)
        page.evaluate(SEED_JS)
        page.evaluate("showView('plan')")
        page.wait_for_timeout(250)

        for vw in WIDTHS:
            vh = 900 if vw >= 768 else 720
            page.set_viewport_size({"width": vw, "height": vh})
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(200)

            m = page.evaluate(MEASURE_JS)
            report[str(vw)] = m

            # 1. Zero horizontal scroll & zero overlaps
            assert m["scrollWidth"] <= m["clientWidth"], (
                f"{vw}px: horizontal scroll {m['scrollWidth']} > {m['clientWidth']}"
            )
            assert not m["overlaps"], f"{vw}px: overlapping controls in #v-plan: {m['overlaps']}"

            # 2. Exam countdown card
            ex = m["exam"]
            inp = ex["input"]
            lbl = ex["label"]
            primaries = [b for b in ex["buttons"] if b["isPrimary"]]
            tertiaries = [b for b in ex["buttons"] if not b["isPrimary"]]
            assert len(primaries) == 1, (
                f"{vw}px: expected exactly 1 primary button in #examCountdown, got {ex['buttons']}"
            )
            primary = primaries[0]
            assert primary["text"] == "Save date", (
                f"{vw}px: primary button in #examCountdown should be 'Save date', got {primary}"
            )
            assert len(tertiaries) == 1 and tertiaries[0]["onclick"] == "openIntake()", (
                f"{vw}px: expected 'Set your exam date' as tertiary button (openIntake()), got {tertiaries}"
            )

            # Label above input and aligned to its left edge
            assert lbl["bottom"] <= inp["top"] + 1, (
                f"{vw}px: EXAM DATE label not above input: label.bottom={lbl['bottom']}, input.top={inp['top']}"
            )
            assert abs(lbl["left"] - inp["left"]) <= 1 and lbl["textAlign"] == "left", (
                f"{vw}px: EXAM DATE label not left-aligned with input: label={lbl}, input={inp}"
            )

            # Input and primary button share height (±1 px)
            assert abs(inp["height"] - primary["height"]) <= 1, (
                f"{vw}px: input height {inp['height']} != primary button height {primary['height']}"
            )

            if vw >= 480:
                # Share baseline (±2 px) and tertiary is to the left of input
                assert abs(inp["bottom"] - primary["bottom"]) <= 2, (
                    f"{vw}px: input bottom {inp['bottom']} != primary bottom {primary['bottom']}"
                )
                assert abs(inp["centerY"] - primary["centerY"]) <= 2, (
                    f"{vw}px: input centerY {inp['centerY']} != primary centerY {primary['centerY']}"
                )
                assert tertiaries[0]["right"] <= inp["left"] + 1, (
                    f"{vw}px: tertiary button not to the left of input: {tertiaries[0]} vs {inp}"
                )
            else:
                # Stacked at <= 480 px: input on top at full width, Save date below at full width
                assert inp["bottom"] <= primary["top"] + 1, (
                    f"{vw}px: input not stacked above Save date at <= 480px: {inp} vs {primary}"
                )
                assert abs(inp["width"] - ex["rowWidth"]) <= 1, (
                    f"{vw}px: input not full width ({inp['width']} vs {ex['rowWidth']})"
                )
                assert abs(primary["width"] - ex["rowWidth"]) <= 1, (
                    f"{vw}px: Save date not full width ({primary['width']} vs {ex['rowWidth']})"
                )

            # 3. Top action grid: 4 buttons with exact same width (±1 px) and height
            act = m["actions"]
            btns = act["buttons"]
            assert len(btns) == 4, f"{vw}px: expected 4 action buttons, got {len(btns)}"
            widths = [b["width"] for b in btns]
            heights = [round(b["height"]) for b in btns]
            assert max(widths) - min(widths) <= 1, (
                f"{vw}px: action buttons do not share exact width: {widths}"
            )
            assert len(set(heights)) == 1 and heights[0] == 48, (
                f"{vw}px: action buttons do not share uniform height 48: {heights}"
            )
            assert act["rowGap"] == 12 and act["colGap"] == 12, (
                f"{vw}px: action grid gap is not --s3 (12px): {act}"
            )
            if vw >= 640:
                expected_w = (act["gridWidth"] - act["colGap"]) / 2
                assert abs(widths[0] - expected_w) <= 1, (
                    f"{vw}px: action button width {widths[0]} != half container {expected_w}"
                )
            else:
                assert abs(widths[0] - act["gridWidth"]) <= 1, (
                    f"{vw}px: mobile action button width {widths[0]} != container {act['gridWidth']}"
                )
            lbl_offsets = [b["lblOffset"] for b in btns]
            assert all(b["icoBeforeLbl"] for b in btns), (
                f"{vw}px: icon not to the left of label in action buttons: {btns}"
            )
            assert max(lbl_offsets) - min(lbl_offsets) <= 1, (
                f"{vw}px: action button labels not aligned to same point: {lbl_offsets}"
            )

            # 4. Week plan summary & Regenerate header
            wp = m["weekPlan"]
            assert wp["summary"]["fontWeight"] <= 500, (
                f"{vw}px: #wpSummary font-weight {wp['summary']['fontWeight']} > 500"
            )
            assert abs(wp["summary"]["fontSize"] - m["tBodyPx"]) <= 0.5, (
                f"{vw}px: #wpSummary font-size {wp['summary']['fontSize']} != --t-body ({m['tBodyPx']})"
            )
            assert wp["summary"]["figures"] and all(f["fontWeight"] == 600 for f in wp["summary"]["figures"]), (
                f"{vw}px: #wpSummary figures do not have font-weight 600: {wp['summary']['figures']}"
            )
            assert wp["weekBlock"]["fontWeight"] <= 500, (
                f"{vw}px: #wpWeekBlock font-weight {wp['weekBlock']['fontWeight']} > 500"
            )
            assert abs(wp["weekBlock"]["fontSize"] - m["tBodyPx"]) <= 0.5, (
                f"{vw}px: #wpWeekBlock font-size {wp['weekBlock']['fontSize']} != --t-body ({m['tBodyPx']})"
            )
            assert wp["regen"]["height"] == 44 and wp["regen"]["bgAlpha"] == 0, (
                f"{vw}px: #wpRegenBtn is not a 44px tertiary button: {wp['regen']}"
            )
            assert abs(wp["regen"]["right"] - wp["headRight"]) <= 1, (
                f"{vw}px: #wpRegenBtn not right-aligned in header: {wp['regen']} vs {wp['headRight']}"
            )
            assert wp["headGap"] == 12, (
                f"{vw}px: .plan-card-head gap {wp['headGap']} != --s3 (12px)"
            )

            # 5. Screenshot
            shot = OUT_DIR / f"plan_polish_{vw}.png"
            page.screenshot(path=str(shot), full_page=False)
            assert shot.exists() and shot.stat().st_size > 1000

        assert not errors, f"page errors: {errors}"
        browser.close()

    print(json.dumps(report, indent=2))
    print("PLAN_POLISH_OK")


if __name__ == "__main__":
    main()
