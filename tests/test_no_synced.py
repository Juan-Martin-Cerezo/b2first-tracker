import json
from playwright.sync_api import sync_playwright
from helpers import login_owner

URL = "http://127.0.0.1:8088/"

out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="networkidle")
    login_owner(pg, URL)
    pg.wait_for_timeout(400)

    # 1. The word "synced" must not appear anywhere in the rendered page.
    content = pg.content()
    assert "synced" not in content.lower(), "rendered page still contains the word 'synced'"
    out["1_no_synced_word"] = True

    # 2. The badge exists, is focusable, and carries an accessible label + title.
    badge = pg.evaluate(
        """() => {
        const el = document.getElementById('syncBadge');
        if (!el) return null;
        return {
            aria: el.getAttribute('aria-label') || '',
            title: el.getAttribute('title') || '',
            tabindex: el.getAttribute('tabindex'),
            text: (el.textContent || '').trim()
        };
    }"""
    )
    assert badge, "syncBadge is missing"
    assert badge["aria"], f"syncBadge has no aria-label: {badge}"
    assert badge["title"], f"syncBadge has no title: {badge}"
    assert badge["tabindex"] == "0", f"syncBadge is not focusable: {badge}"
    assert badge["text"] == "", f"syncBadge still renders text: {badge}"

    foot = pg.evaluate(
        """() => {
        const el = document.getElementById('syncBadgeFoot');
        if (!el) return null;
        return {
            aria: el.getAttribute('aria-label') || '',
            title: el.getAttribute('title') || '',
            tabindex: el.getAttribute('tabindex'),
            text: (el.textContent || '').trim()
        };
    }"""
    )
    assert foot, "syncBadgeFoot is missing"
    assert foot["aria"], f"syncBadgeFoot has no aria-label: {foot}"
    assert foot["title"], f"syncBadgeFoot has no title: {foot}"
    assert foot["tabindex"] == "0", f"syncBadgeFoot is not focusable: {foot}"
    assert foot["text"] == "", f"syncBadgeFoot still renders text: {foot}"
    out["2_badge"] = badge
    out["2_badge_foot"] = foot

    # 3. A save must change the badge's colour class at least once.
    pg.evaluate(
        """() => {
        window.__syncClasses = [document.getElementById('syncBadge').className];
        new MutationObserver(() => {
            window.__syncClasses.push(document.getElementById('syncBadge').className);
        }).observe(document.getElementById('syncBadge'), {attributes: true, attributeFilter: ['class']});
    }"""
    )
    pg.evaluate("save()")
    pg.wait_for_timeout(1500)
    classes = pg.evaluate("window.__syncClasses")
    assert len(set(classes)) >= 2, f"badge colour class never changed during a save: {classes}"
    out["3_class_changes"] = classes

    # 4. The sync badge is still queryable by id.
    sync_nodes = pg.evaluate("document.querySelectorAll('[id*=sync]').length")
    assert sync_nodes >= 1, f"no [id*=sync] element found: {sync_nodes}"
    out["4_sync_nodes"] = sync_nodes

    assert errs == [], f"JS errors while checking the badge: {errs}"
    b.close()

print(json.dumps(out, ensure_ascii=False, indent=1))
