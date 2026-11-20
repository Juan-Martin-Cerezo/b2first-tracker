"""Acceptance test for writing-progress: progress bar, steps, timer and states."""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

from helpers import OWNER_NAME, OWNER_PASS, _api, _ensure_account, isolated_server

URL = isolated_server() + "/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

DRAFT = (
    "Technology has dramatically changed how people communicate with one another in daily life. "
    "While some observers argue that smartphones make us feel more isolated, the real picture is more balanced. "
    "Firstly, messaging apps allow families who live far apart to stay in regular contact and share everyday moments. "
    "Moreover, online study groups help students collaborate across different cities without wasting travel time. "
    "Nevertheless, excessive screen use can reduce face-to-face conversation if people neglect local friendships. "
    "Therefore, setting sensible boundaries around phone use is widely considered the healthiest approach."
)

MOCK_RESULT = {
    "bands": {
        "content": 4,
        "communicative_achievement": 4,
        "organisation": 4,
        "language": 4,
    },
    "total": 16,
    "feedback": {
        "content": "All content points are addressed clearly.",
        "communicative_achievement": "Appropriate formal essay register.",
        "organisation": "Logical paragraphing with clear linkers.",
        "language": "Good range of B2 grammar and vocabulary.",
    },
    "weaknesses": {
        "content": [],
        "communicative_achievement": [],
        "organisation": [],
        "language": [],
    },
    "quotes": {},
    "rewrite": [
        "Setting sensible boundaries around phone use helps protect real conversation."
    ],
}


async def login_and_open_writing(pg):
    _ensure_account(URL, OWNER_NAME, OWNER_PASS)
    user = _api(URL, "api/login", {"name": OWNER_NAME, "password": OWNER_PASS})
    await pg.goto(URL + "app", wait_until="networkidle")
    await pg.evaluate(
        "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
    )
    await pg.reload(wait_until="networkidle")
    await pg.wait_for_timeout(300)
    await pg.evaluate("""() => {
        try { D.onboarded = true; if (typeof save === 'function') save(); } catch (e) {}
        for (const id of ['onboardingOverlay', 'tourOverlay', 'obOverlay']) {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        }
        document.body.classList.remove('ob-open', 'tour-open');
        setLang('en');
        showView('ia');
    }""")
    await pg.wait_for_timeout(250)


async def run():
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # 1-5: Mobile 390x844 light mode with ~6s network stub
        ctx = await browser.new_context(viewport={"width": 390, "height": 844})
        pg = await ctx.new_page()
        page_errors = []
        pg.on("pageerror", lambda e: page_errors.append(str(e)))

        await login_and_open_writing(pg)

        async def slow_ai_route(route):
            await asyncio.sleep(6.0)
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_RESULT),
            )

        await pg.route("**/api/ai/writing", slow_ai_route)
        await pg.fill("#iaText", DRAFT)
        await pg.click("#iaSubmitBtn")

        # Immediately visible loading panel, disabled busy button, progressbar at initial step 0
        await pg.wait_for_selector("#iaLoading", state="visible", timeout=2000)
        init_state = await pg.evaluate("""() => {
            const btn = document.getElementById('iaSubmitBtn');
            const load = document.getElementById('iaLoading');
            const bar = document.getElementById('iaProgressBar');
            const steps = [...document.querySelectorAll('#iaLoadingSteps .ia-step')];
            const el = document.getElementById('iaElapsed');
            return {
                loadVisible: getComputedStyle(load).display !== 'none',
                skeletonCount: load.querySelectorAll('.sk').length,
                btnDisabled: btn.disabled,
                btnBusy: btn.getAttribute('aria-busy'),
                barRole: bar ? bar.getAttribute('role') : null,
                barMin: bar ? bar.getAttribute('aria-valuemin') : null,
                barMax: bar ? bar.getAttribute('aria-valuemax') : null,
                barNow: bar ? Number(bar.getAttribute('aria-valuenow')) : null,
                elapsed: el ? el.textContent.trim() : '',
                activeIdx: steps.findIndex(s => s.getAttribute('aria-current') === 'step'),
                stepCount: steps.length,
                stepTexts: steps.map(s => s.textContent.trim()),
                overflow: document.documentElement.scrollWidth > window.innerWidth,
            };
        }""")
        assert init_state["loadVisible"] is True
        assert init_state["skeletonCount"] >= 3, f"skeleton missing: {init_state}"
        assert init_state["btnDisabled"] is True
        assert init_state["btnBusy"] == "true"
        assert init_state["barRole"] == "progressbar"
        assert init_state["barMin"] == "0" and init_state["barMax"] == "100"
        assert init_state["barNow"] is not None and 0 < init_state["barNow"] < 100
        assert init_state["activeIdx"] == 0, f"expected step 0 active: {init_state}"
        assert init_state["stepCount"] == 4
        assert init_state["overflow"] is False, "horizontal overflow at 390px on start"

        # Sample 1 at ~0.5s, Sample 2 at ~2.5s (2s apart), Sample 3 at ~3.6s (step 1 active + screenshot)
        await pg.wait_for_timeout(500)
        sample1 = await pg.evaluate("""() => ({
            now: Number(document.getElementById('iaProgressBar').getAttribute('aria-valuenow')),
            elapsed: document.getElementById('iaElapsed').textContent.trim(),
        })""")

        await pg.wait_for_timeout(2000)
        sample2 = await pg.evaluate("""() => ({
            now: Number(document.getElementById('iaProgressBar').getAttribute('aria-valuenow')),
            elapsed: document.getElementById('iaElapsed').textContent.trim(),
        })""")
        assert sample2["now"] > sample1["now"], f"progressbar did not grow over 2s: {sample1} -> {sample2}"
        assert sample2["elapsed"] != sample1["elapsed"], f"elapsed timer did not advance: {sample1} -> {sample2}"

        # Wait past 3s so step 1 becomes active and step 0 has checkmark
        await pg.wait_for_timeout(1100)
        mid_state = await pg.evaluate("""() => {
            const steps = [...document.querySelectorAll('#iaLoadingSteps .ia-step')];
            return {
                now: Number(document.getElementById('iaProgressBar').getAttribute('aria-valuenow')),
                elapsed: document.getElementById('iaElapsed').textContent.trim(),
                activeIdx: steps.findIndex(s => s.getAttribute('aria-current') === 'step'),
                step0Mark: steps[0].querySelector('.ia-step-mark').textContent.trim(),
                step2Current: steps[2].getAttribute('aria-current'),
                step3Current: steps[3].getAttribute('aria-current'),
                overflow: document.documentElement.scrollWidth > window.innerWidth,
            };
        }""")
        assert mid_state["activeIdx"] == 1, f"expected step 1 active after 3s: {mid_state}"
        assert mid_state["step0Mark"] == "✓", f"expected checkmark on completed step 0: {mid_state}"
        assert mid_state["step2Current"] is None and mid_state["step3Current"] is None
        assert mid_state["overflow"] is False, "horizontal overflow at 390px mid-load"

        await pg.locator("#iaLoadingSteps").scroll_into_view_if_needed()
        await pg.wait_for_timeout(150)
        await pg.screenshot(path=os.path.join(OUT, "writing_progress_390_light.png"))

        # Wait for the 6s stubbed response to arrive
        await pg.wait_for_selector("#iaCard[data-state='ok']", timeout=10000)
        done_state = await pg.evaluate("""() => {
            const btn = document.getElementById('iaSubmitBtn');
            const load = document.getElementById('iaLoading');
            const steps = [...document.querySelectorAll('#iaLoadingSteps .ia-step')];
            return {
                loadDisplay: getComputedStyle(load).display,
                btnDisabled: btn.disabled,
                btnBusy: btn.getAttribute('aria-busy'),
                anyStepCurrent: steps.some(s => s.hasAttribute('aria-current')),
                doneMarks: steps.map(s => s.querySelector('.ia-step-mark').textContent.trim()),
                resultDisplay: getComputedStyle(document.getElementById('iaResult')).display,
            };
        }""")
        assert done_state["loadDisplay"] == "none", f"iaLoading not hidden after completion: {done_state}"
        assert done_state["btnDisabled"] is False, "submit button stayed disabled"
        assert done_state["btnBusy"] is None, "submit button still has aria-busy"
        assert done_state["anyStepCurrent"] is False
        assert done_state["resultDisplay"] != "none"

        # Verify error response also hides #iaLoading and releases button
        await pg.unroute("**/api/ai/writing")

        async def error_ai_route(route):
            await asyncio.sleep(0.3)
            await route.fulfill(status=500, content_type="application/json", body='{"error":"boom"}')

        await pg.route("**/api/ai/writing", error_ai_route)
        await pg.click("#iaSubmitBtn")
        await pg.wait_for_selector("#iaCard[data-state='error']", timeout=12000)
        err_state = await pg.evaluate("""() => ({
            loadDisplay: getComputedStyle(document.getElementById('iaLoading')).display,
            btnDisabled: document.getElementById('iaSubmitBtn').disabled,
            btnBusy: document.getElementById('iaSubmitBtn').getAttribute('aria-busy'),
        })""")
        assert err_state["loadDisplay"] == "none", f"iaLoading remained visible on error: {err_state}"
        assert err_state["btnDisabled"] is False
        assert err_state["btnBusy"] is None

        # Verify EN/ES symmetry and 20s/45s reassuring messages + no overflow at 390x844
        i18n_check = await pg.evaluate("""() => {
            setLang('en');
            const enSteps = [...document.querySelectorAll('#iaLoadingSteps .ia-step span[data-i18n]')].map(s => s.textContent.trim());
            const enNote20 = t('ai_wait_long');
            const enNote45 = t('ai_wait_still');
            setLang('es');
            const esSteps = [...document.querySelectorAll('#iaLoadingSteps .ia-step span[data-i18n]')].map(s => s.textContent.trim());
            const esNote20 = t('ai_wait_long');
            const esNote45 = t('ai_wait_still');
            setLang('en');
            return {
                enSteps, esSteps,
                enNote20, esNote20,
                enNote45, esNote45,
                curve: [0, 3000, 8000, 15000, 30000, 60000].map(ms => calcIaProgress(ms)),
                overflowEs: document.documentElement.scrollWidth > window.innerWidth,
            };
        }""")
        assert i18n_check["enSteps"] == [
            "Reading your text",
            "Checking the task and content points",
            "Scoring each band",
            "Writing the feedback",
        ]
        assert i18n_check["esSteps"] == [
            "Leyendo tu texto",
            "Revisando la consigna y los puntos",
            "Puntuando cada criterio",
            "Escribiendo el feedback",
        ]
        assert i18n_check["enNote20"] == "Long texts can take up to a minute — your draft is safe."
        assert i18n_check["esNote20"] == "Los textos largos pueden tardar hasta un minuto — tu borrador está a salvo."
        assert i18n_check["enNote45"] == "Still working…"
        assert i18n_check["esNote45"] == "Sigue trabajando…"
        assert i18n_check["curve"] == [5, 35, 60, 80, 92, 92], f"unexpected curve: {i18n_check['curve']}"
        assert i18n_check["overflowEs"] is False

        # Verify 20s and 45s note thresholds appear in DOM when elapsed >= 20s / 45s, and dark mode contrast
        dom_thresholds = await pg.evaluate("""() => {
            document.documentElement.setAttribute('data-theme', 'dark');
            setIaState('loading');
            _iaLoadStart = Date.now() - 21000;
            updateIaLoadingProgress();
            const n20 = document.getElementById('iaLoadingNote').textContent.trim();
            const n20Vis = getComputedStyle(document.getElementById('iaLoadingNote')).display !== 'none';
            _iaLoadStart = Date.now() - 46000;
            updateIaLoadingProgress();
            const n45 = document.getElementById('iaLoadingNote').textContent.trim();
            const step3Cur = document.querySelectorAll('#iaLoadingSteps .ia-step')[3].getAttribute('aria-current');
            const pct46 = Number(document.getElementById('iaProgressBar').getAttribute('aria-valuenow'));
            const overflowDark = document.documentElement.scrollWidth > window.innerWidth;
            setIaState('idle');
            document.documentElement.removeAttribute('data-theme');
            return {n20, n20Vis, n45, step3Cur, pct46, overflowDark};
        }""")
        assert dom_thresholds["n20Vis"] is True
        assert dom_thresholds["n20"] == "Long texts can take up to a minute — your draft is safe."
        assert dom_thresholds["n45"] == "Still working…"
        assert dom_thresholds["step3Cur"] == "step"
        assert dom_thresholds["pct46"] == 92
        assert dom_thresholds["overflowDark"] is False

        assert page_errors == [], f"page errors: {page_errors}"
        await ctx.close()

        # Verify prefers-reduced-motion disables progress bar animation/transition
        rm_ctx = await browser.new_context(
            viewport={"width": 390, "height": 844},
            reduced_motion="reduce",
        )
        rm_pg = await rm_ctx.new_page()
        await login_and_open_writing(rm_pg)
        rm_style = await rm_pg.evaluate("""() => {
            setIaState('loading');
            const fill = document.getElementById('iaProgressFill');
            const cs = getComputedStyle(fill);
            const res = {
                transitionProperty: cs.transitionProperty,
                transitionDuration: cs.transitionDuration,
                animationName: cs.animationName,
            };
            setIaState('idle');
            return res;
        }""")
        assert rm_style["transitionProperty"] == "none" or rm_style["transitionDuration"] in ("0s", "0ms"), (
            f"reduced-motion still transitions progress bar: {rm_style}"
        )
        await rm_ctx.close()
        await browser.close()

        out["init"] = init_state
        out["sample1"] = sample1
        out["sample2"] = sample2
        out["mid"] = mid_state
        out["done"] = done_state
        out["err"] = err_state
        out["reduced_motion"] = rm_style
        out["thresholds"] = dom_thresholds

    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(run())
    sys.exit(0)
