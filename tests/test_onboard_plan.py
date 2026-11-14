"""Acceptance tests for the account-plan step inside onboarding.

Runs an isolated server.py on a temporary DATA_DIR with B2_LICENSE_SECRET
and drives the onboarding wizard in Playwright against real server responses.

Cases:
1. Free account: renders real server limits (3/day writing, 1 mock 5 min/week,
   preview pronunciation, no card / no ads) + single Pro upgrade block with
   Subscribe and code redemption.
2. Pro account (redeemed FT-PRO code via issue("pro", "30D")): renders 60 and 6
   (90 min, full pronunciation, reset date) with no upsell block.
3. BYO account (provider key in localStorage): renders "Unlimited" copy and
   opens the existing BYO Settings panel, with no upsell.
4. Degraded /api/plan (HTTP 500): renders neutral copy ("Settings -> Plan")
   without invented numbers or zeros, and Continue reaches the tour.
5. Resumption / migration: onboardStep=5 && !onboarded enters the new step;
   onboarded=true does not show the wizard.
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import helpers  # noqa: E402

PASS = "onboard-plan-pass-9"


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def wait_health(base, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def request(base, path, body=None, token=None, headers=None, method="POST"):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


SECRET = secrets.token_urlsafe(32)
DATA_DIR = tempfile.mkdtemp(prefix="b2obplan-")
PORT = free_port()
APP_URL = "http://127.0.0.1:%d" % PORT
stdout_path = os.path.join(DATA_DIR, "server-stdout.log")
stderr_path = os.path.join(DATA_DIR, "server-stderr.log")

env = dict(os.environ)
env.pop("B2_AI_DAILY_PER_USER", None)
env.update({
    "DATA_DIR": DATA_DIR,
    "PORT": str(PORT),
    "B2_HOST": "127.0.0.1",
    "B2_DEMO": "0",
    "B2_REGISTER": "open",
    "B2_LICENSE_SECRET": SECRET,
})
stdout_file = open(stdout_path, "w", encoding="utf-8")
stderr_file = open(stderr_path, "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, os.path.join(REPO, "server.py")],
    cwd=REPO,
    env=env,
    stdout=stdout_file,
    stderr=stderr_file,
)


def issue(plan, days):
    """Run tools/issue_license.py (accepts '30' or '30D') and return the code."""
    d = str(days).strip()
    if d.upper().endswith("D"):
        d = d[:-1]
    run = subprocess.run(
        [sys.executable, os.path.join(REPO, "tools", "issue_license.py"), plan, d],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, "issue_license failed: %s %s" % (run.returncode, run.stderr)
    return run.stdout.strip().splitlines()[-1]


def account(name):
    helpers._ensure_account(APP_URL + "/", name, PASS)
    login = helpers._api(APP_URL + "/", "api/login", {"name": name, "password": PASS})
    return login["id"], login["token"], login


def get_plan(token):
    st, body, _ = request(APP_URL, "/api/plan", token=token, method="GET")
    assert st == 200, "GET /api/plan failed: %s %s" % (st, body[:200])
    return json.loads(body)


def redeem(token, code):
    return request(APP_URL, "/api/plan/redeem", {"code": code}, token=token)


def walk_to_plan_step(pg, login_obj):
    """Sign in cleanly on a fresh context and walk steps 1 -> 4 -> accept -> 5/5."""
    pg.goto(APP_URL + "/app", wait_until="networkidle")
    pg.evaluate(
        "u => { localStorage.clear(); localStorage.setItem('b2first_user', JSON.stringify(u)); }",
        login_obj,
    )
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector("#onboardingOverlay", state="visible", timeout=5000)
    pg.fill("#obExamDate", "2027-06-12")
    pg.click("#obNextBtn")  # 1 -> 2
    pg.click("#obNextBtn")  # 2 -> 3
    pg.evaluate(
        """() => {
        D.diag = {date: today(), correct: 8, total: 12,
                  byPart: {1:{ok:2,n:2},2:{ok:1,n:2},3:{ok:2,n:2},4:{ok:1,n:2},
                           5:{ok:1,n:1},6:{ok:0,n:1},7:{ok:1,n:2}},
                  weakest: [6, 4, 7]};
        obRender();
    }"""
    )
    pg.click("#obStepBody .btn.ok")  # 3 -> 4
    pg.wait_for_selector("#obAcceptBtn", state="visible", timeout=5000)
    pg.click("#obAcceptBtn")  # 4 -> 5/5 (account plan)
    pg.wait_for_selector("#obAccountPlanBody .ob-acct-card, #obAccountPlanBody .ob-diag-box",
                         state="visible", timeout=5000)


out = {}
try:
    assert wait_health(APP_URL), "test server did not start"

    with sync_playwright() as p:
        b = p.chromium.launch()
        errs = []

        # ------------------------------------------------------------------
        # 1. Free account: server limits (3/day, 1 mock 5 min/week) + upgrade
        # ------------------------------------------------------------------
        _uid1, tok1, user1 = account("obplan-free")
        srv_free = get_plan(tok1)
        assert srv_free["plan"] == "free", srv_free
        ctx1 = b.new_context(viewport={"width": 1440, "height": 900})
        pg1 = ctx1.new_page()
        pg1.on("pageerror", lambda e: errs.append(str(e)))
        walk_to_plan_step(pg1, user1)

        step_cnt = pg1.inner_text("#obStepCount").strip()
        assert step_cnt == "5/5", f"Expected 5/5, got {step_cnt!r}"
        body1 = pg1.inner_text("#obStepBody")
        w_lim = srv_free["limits"]["writing"]
        s_lim = srv_free["limits"]["speaking"]
        assert str(w_lim["limit"]) in body1 and "day" in body1.lower(), body1
        assert str(s_lim["mocks"]) in body1 and "week" in body1.lower(), body1
        assert str(s_lim["minutes"]) in body1, body1
        assert "preview" in body1.lower(), body1
        assert "no card" in body1.lower() and "no ads" in body1.lower(), body1
        assert pg1.is_visible("#obPlanSubscribeBtn"), "Missing Subscribe button on free plan"
        assert pg1.is_visible("#obHaveCodeBtn"), "Missing 'I have a code' button on free plan"

        # Back returns to step 4/5, accepting again returns to 5/5
        pg1.click("#obBackBtn")
        pg1.wait_for_selector("#obAcceptBtn", state="visible", timeout=3000)
        assert pg1.inner_text("#obStepCount").strip() == "4/5"
        pg1.click("#obAcceptBtn")
        pg1.wait_for_selector("#obAccountPlanBody .ob-acct-card", state="visible", timeout=5000)

        # Clicking "I have a code" opens the redeem input (reused handler)
        pg1.click("#obHaveCodeBtn")
        assert pg1.is_visible("#obPlanCode"), "Code input did not open"
        assert pg1.is_visible("#obPlanRedeemBtn"), "Redeem button did not open"
        out["1_free"] = {
            "step": step_cnt,
            "writing": w_lim["limit"],
            "speaking": s_lim["mocks"],
            "upgrade_visible": True,
        }
        ctx1.close()

        # ------------------------------------------------------------------
        # 2. Pro code redeemed: shows 60 and 6, no upsell block
        # ------------------------------------------------------------------
        _uid2, tok2, user2 = account("obplan-pro")
        code_pro = issue("pro", "30D")
        st_r, body_r, _ = redeem(tok2, code_pro)
        assert st_r == 200, f"Redeem failed: {st_r} {body_r}"
        srv_pro = get_plan(tok2)
        assert srv_pro["plan"] == "pro", srv_pro

        ctx2 = b.new_context(viewport={"width": 1440, "height": 900})
        pg2 = ctx2.new_page()
        pg2.on("pageerror", lambda e: errs.append(str(e)))
        walk_to_plan_step(pg2, user2)
        body2 = pg2.inner_text("#obStepBody")
        assert str(srv_pro["limits"]["writing"]["limit"]) in body2, body2  # 60
        assert str(srv_pro["limits"]["speaking"]["mocks"]) in body2, body2  # 6
        assert str(srv_pro["limits"]["speaking"]["minutes"]) in body2, body2  # 90
        assert "full" in body2.lower(), body2
        assert "reset" in body2.lower(), body2
        assert not pg2.locator("#obPlanSubscribeBtn").count(), "Upsell shown on Pro"
        assert not pg2.locator("#obHaveCodeBtn").count(), "Code upsell shown on Pro"
        assert "subscribe" not in body2.lower(), body2
        out["2_pro"] = {
            "writing": srv_pro["limits"]["writing"]["limit"],
            "speaking": srv_pro["limits"]["speaking"]["mocks"],
            "upsell": False,
        }
        ctx2.close()

        # ------------------------------------------------------------------
        # 3. BYO key in localStorage: "Unlimited" copy, opens BYO Settings, no upsell
        # ------------------------------------------------------------------
        uid3, _tok3, user3 = account("obplan-byo")
        ctx3 = b.new_context(viewport={"width": 1440, "height": 900})
        pg3 = ctx3.new_page()
        pg3.on("pageerror", lambda e: errs.append(str(e)))
        pg3.goto(APP_URL + "/app", wait_until="networkidle")
        pg3.evaluate(
            """([u, uid]) => {
            localStorage.clear();
            localStorage.setItem('b2first_user', JSON.stringify(u));
            localStorage.setItem('b2first_byo_' + uid, JSON.stringify({
                provider: 'deepseek', key: 'sk-test-byo-999', base: '', model: ''
            }));
        }""",
            [user3, uid3],
        )
        pg3.reload(wait_until="networkidle")
        pg3.wait_for_selector("#onboardingOverlay", state="visible", timeout=5000)
        pg3.fill("#obExamDate", "2027-06-12")
        pg3.click("#obNextBtn")
        pg3.click("#obNextBtn")
        pg3.evaluate(
            """() => {
            D.diag = {date: today(), correct: 8, total: 12,
                      byPart: {1:{ok:2,n:2},2:{ok:1,n:2},3:{ok:2,n:2},4:{ok:1,n:2},
                               5:{ok:1,n:1},6:{ok:0,n:1},7:{ok:1,n:2}},
                      weakest: [6, 4, 7]};
            obRender();
        }"""
        )
        pg3.click("#obStepBody .btn.ok")
        pg3.wait_for_selector("#obAcceptBtn", state="visible", timeout=5000)
        pg3.click("#obAcceptBtn")
        pg3.wait_for_selector("#obAccountPlanBody .ob-acct-card", state="visible", timeout=5000)

        body3 = pg3.inner_text("#obStepBody")
        assert "unlimited" in body3.lower(), body3
        assert pg3.is_visible("#obByoManageBtn"), "Missing BYO manage button"
        assert not pg3.locator("#obPlanSubscribeBtn").count(), "Upsell shown on BYO"
        pg3.click("#obByoManageBtn")
        pg3.wait_for_selector("#settingsModal", state="visible", timeout=3000)
        assert pg3.is_visible("#byoCard"), "BYO Settings card did not open"
        out["3_byo"] = {"unlimited": True, "byo_panel_opened": True, "upsell": False}
        ctx3.close()

        # ------------------------------------------------------------------
        # 4. /api/plan 500 -> neutral copy, no numbers, Continue reaches tour
        # ------------------------------------------------------------------
        _uid4, _tok4, user4 = account("obplan-err")
        ctx4 = b.new_context(viewport={"width": 1440, "height": 900})
        pg4 = ctx4.new_page()
        pg4.on("pageerror", lambda e: errs.append(str(e)))
        pg4.route("**/api/plan", lambda route: route.fulfill(status=500, body="{}"))
        walk_to_plan_step(pg4, user4)

        body4 = pg4.inner_text("#obAccountPlanBody")
        assert "Settings → Plan" in body4, body4
        for forbidden in ("3 ", "60", "90", "0 ", "subscribe"):
            assert forbidden not in body4.lower(), f"Number/upsell leaked on 500: {body4!r}"
        pg4.click("#obNextBtn")
        pg4.wait_for_selector("#tourCard", state="visible", timeout=5000)
        out["4_degrade_500"] = {"neutral": True, "tour_started": True}
        ctx4.close()

        # ------------------------------------------------------------------
        # 5. Migration: onboardStep=5 && !onboarded -> shows new step;
        #               onboarded=true -> does NOT show wizard
        # ------------------------------------------------------------------
        _uid5, _tok5, user5 = account("obplan-mig")
        ctx5 = b.new_context(viewport={"width": 1440, "height": 900})
        pg5 = ctx5.new_page()
        pg5.on("pageerror", lambda e: errs.append(str(e)))
        pg5.goto(APP_URL + "/app", wait_until="networkidle")
        pg5.evaluate(
            """u => {
            localStorage.clear();
            localStorage.setItem('b2first_user', JSON.stringify(u));
            const key = 'b2first_tracker_v1_' + u.id;
            localStorage.setItem(key, JSON.stringify({
                log: [], errs: [], examDates: [], stage: 0, settings: {},
                overrides: {}, weekOverrides: {}, mat: {}, diag: null,
                profile: {examDate: '2027-06-12', targetGrade: 'B',
                          skills: {rue:3,w:3,l:3,sp:3}, hoursWeek: 6,
                          days: ['mon','wed'], struggles: [], strugglesDeclared: [],
                          declaredAt: '2026-10-30T00:00:00Z'},
                onboarded: false, onboardStep: 5, sessionOffset: 0
            }));
        }""",
            user5,
        )
        pg5.reload(wait_until="networkidle")
        pg5.wait_for_selector("#onboardingOverlay", state="visible", timeout=5000)
        pg5.wait_for_selector("#obAccountPlanBody .ob-acct-card", state="visible", timeout=5000)
        assert pg5.inner_text("#obStepCount").strip() == "5/5"
        assert "Your plan" in pg5.inner_text("#obStepBody")

        # Now onboarded=true -> wizard does NOT appear after reload
        pg5.evaluate(
            """() => {
            D.onboarded = true;
            D.onboardStep = 5;
            localStorage.setItem('b2first_tracker_v1_' + USER.id, JSON.stringify(D));
        }"""
        )
        pg5.reload(wait_until="networkidle")
        pg5.wait_for_timeout(400)
        assert not pg5.is_visible("#onboardingOverlay"), "Wizard appeared for onboarded=true"
        out["5_migration"] = {"step5_not_onboarded_shown": True, "onboarded_hidden": True}
        ctx5.close()

        assert errs == [], f"JS pageerrors: {errs}"
        out["errores_js"] = errs
        b.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    stdout_file.close()
    stderr_file.close()
