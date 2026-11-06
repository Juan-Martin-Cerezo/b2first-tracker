"""Phase 95: Language and Subscription moved into Settings.

Both cards keep their ids and all their behaviour, but they no longer live in
PLAN. Switching language from the Settings panel still translates the UI, the
activation code still redeems from there and the subscription button still
opens the same checkout.
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_owner

URL = isolated_server() + "/"
OUT = {}


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors = []
    pg.on("pageerror", lambda e: page_errors.append(str(e)))
    pg.goto(URL + "app", wait_until="networkidle")
    login_owner(pg, URL)
    pg.evaluate("setLang('en')")
    pg.wait_for_timeout(400)

    # 1. Both cards live in #settingsModal, never in #v-plan, exactly once.
    placement = pg.evaluate(
        """() => {
            const ids = ['byoCard', 'languageCard', 'planStatusCard'];
            const modal = document.getElementById('settingsModal');
            const plan = document.getElementById('v-plan');
            return ids.map(id => ({
                id,
                in_modal: modal.contains(document.getElementById(id)),
                in_plan: plan.contains(document.getElementById(id)),
                count: document.querySelectorAll('#' + id).length,
            }));
        }"""
    )
    for card in placement:
        assert card["in_modal"], f"#{card['id']} is not inside #settingsModal"
        assert not card["in_plan"], f"#{card['id']} is still inside #v-plan"
        assert card["count"] == 1, f"#{card['id']} is duplicated: {card}"
    OUT["1_placement"] = placement

    # 2. PLAN no longer mentions either card.
    pg.click("nav button[data-view='plan']")
    pg.wait_for_timeout(250)
    plan_text = pg.evaluate("document.getElementById('v-plan').innerText").lower()
    assert "language" not in plan_text, f"PLAN still shows Language: {plan_text[:120]}"
    assert "subscription" not in plan_text, f"PLAN still shows Subscription: {plan_text[:120]}"
    OUT["2_plan_text"] = plan_text[:120]

    # 3. Open Settings: the language switch translates the UI as before.
    pg.click("#settingsBtn")
    pg.wait_for_timeout(200)
    assert pg.is_visible("#languageCard"), "the language card is not visible in Settings"
    pg.click("#langEsBtn")
    pg.wait_for_function("document.documentElement.lang === 'es'")
    pg.wait_for_timeout(300)
    assert pg.evaluate("document.documentElement.lang") == "es"
    assert pg.evaluate("D.settings.lang") == "es", "the language was not saved"
    assert pg.eval_on_selector("#sideNav", "el => el.textContent").count("Hoy") >= 1
    assert pg.get_attribute("#langEsBtn", "aria-pressed") == "true"
    assert pg.get_attribute("#langEnBtn", "aria-pressed") == "false"

    pg.click("#langEnBtn")
    pg.wait_for_function("document.documentElement.lang === 'en'")
    pg.wait_for_timeout(300)
    assert pg.evaluate("D.settings.lang") == "en", "could not switch back to English"
    assert pg.eval_on_selector("#sideNav", "el => el.textContent").count("Today") >= 1
    OUT["3_language"] = "en<->es from Settings"

    # 4. Redeeming a code answers from the Subscription card in Settings.
    pg.route(
        "**/api/plan/redeem",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"plan": {"tier": "pro", "until": "2026-12-31"}}),
        ),
    )
    pg.fill("#planCode", "FT-PRO-TEST-CODE")
    pg.click("#planRedeemBtn")
    pg.wait_for_timeout(600)
    status = pg.inner_text("#planRedeemStatus")
    assert "Activated" in status, f"redeem did not answer from Settings: {status!r}"
    pg.unroute("**/api/plan/redeem")
    OUT["4_redeem"] = status

    # 5. The subscribe button opens the same checkout from Settings.
    seen = {"called": False}

    def checkout(route):
        seen["called"] = True
        route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"error": "billing_not_configured"}),
        )

    pg.route("**/api/billing/checkout", checkout)
    pg.click("#planSubscribeBtn")
    pg.wait_for_timeout(600)
    billing = pg.inner_text("#planBillingStatus")
    assert seen["called"], "the subscribe button did not call the checkout endpoint"
    assert "not configured" in billing.lower(), f"no checkout answer in Settings: {billing!r}"
    pg.unroute("**/api/billing/checkout")
    OUT["5_checkout"] = billing

    # 6. The panel still shows all three cards together after using them.
    still = pg.evaluate(
        """() => ['byoCard', 'languageCard', 'planStatusCard'].every(id =>
            document.getElementById('settingsModal').contains(document.getElementById(id)))"""
    )
    assert still, "a card left the Settings panel after being used"
    OUT["6_cards_together"] = True

    assert page_errors == [], f"page errors: {page_errors}"
    OUT["errors"] = page_errors
    browser.close()

print(json.dumps(OUT, ensure_ascii=False, indent=1))
