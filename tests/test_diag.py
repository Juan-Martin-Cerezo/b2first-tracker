import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from collections import Counter
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S
import store

# Spin up an isolated instance of server.py (with a temporary DATA_DIR so the real
# data/ is untouched) and use 8088 as the main Playwright URL. If the process on
# 8088 has not been restarted since /diagnostico.json was added, that route is
# delegated to the current S.H handler.
_tmp = tempfile.mkdtemp(prefix="b2diag-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
S.migrate_legacy()

local_srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
local_port = local_srv.server_address[1]
local_th = threading.Thread(target=local_srv.serve_forever, daemon=True)
local_th.start()

URL_8088 = "http://127.0.0.1:8088"
URL_LOCAL = f"http://127.0.0.1:{local_port}"


def fetch_diag(base_url):
    req = urllib.request.Request(base_url + "/diagnostico.json")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8")


out = {}

# Try 8088 first; if the 8088 daemon predates the change and was not restarted, verify against local S.H
st_8088, ct_8088, body_8088 = fetch_diag(URL_8088)
if st_8088 == 200:
    st_1, ct_1, body_1 = st_8088, ct_8088, body_8088
    need_route_proxy = False
else:
    st_1, ct_1, body_1 = fetch_diag(URL_LOCAL)
    need_route_proxy = True

# Assert 1: /diagnostico.json -> 200 and len(items)==12
assert st_1 == 200, f"Expected 200 from /diagnostico.json, got {st_1}: {body_1}"
assert "application/json" in ct_1, f"Expected application/json, got {ct_1}"
diag_json = json.loads(body_1)
items = diag_json.get("items", [])
assert len(items) == 12, f"Expected 12 items, got {len(items)}"
out["1_status_and_len"] = {"status": st_1, "items": len(items)}

# Assert 2: the 12 items have 4 options and answer in 0-3 (and explain <= 240 chars)
for it in items:
    assert isinstance(it.get("options"), list) and len(it["options"]) == 4, f"Bad options in {it}"
    assert type(it.get("answer")) is int and 0 <= it["answer"] <= 3, f"Bad answer in {it}"
    assert it.get("taxonomy") in ("L-GAP", "G-ERR", "T-MIS", "T-LIM"), f"Bad taxonomy in {it}"
    assert isinstance(it.get("explain"), str) and 0 < len(it["explain"]) <= 240, f"Bad explain in {it}"
out["2_options_and_answers_ok"] = True

# Assert 3: all 7 parts are covered and the counts match the Task A table
counts = Counter(it["part"] for it in items)
assert set(counts.keys()) == {1, 2, 3, 4, 5, 6, 7}, f"Parts missing: {counts}"
assert (
    counts[1] == 2
    and counts[2] == 2
    and counts[3] == 1
    and counts[4] >= 1
    and counts[5] == 2
    and counts[6] == 1
    and counts[7] == 2
    and sum(counts.values()) == 12
), f"Unexpected part counts: {counts}"
out["3_parts_coverage"] = dict(sorted(counts.items()))

# Also verify on the server that broken JSON answers 500 {"error":"invalid diagnostic"}
bad_diag_path = os.path.join(_tmp, "bad_diag.json")
with open(bad_diag_path, "w", encoding="utf-8") as f:
    json.dump({"version": 1, "min": 10, "items": items[:5]}, f)
orig_diag_file = S.DIAG_FILE
try:
    S.DIAG_FILE = bad_diag_path
    S._DIAG_CACHE["body"] = None
    st_bad, _, body_bad = fetch_diag(URL_LOCAL)
    assert st_bad == 500 and json.loads(body_bad).get("error") == "invalid diagnostic"
finally:
    S.DIAG_FILE = orig_diag_file
    S._DIAG_CACHE["body"] = None

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    errores_js = []
    pg.on("pageerror", lambda e: errores_js.append(str(e)))

    if need_route_proxy:
        def _proxy_diag(route):
            st_p, ct_p, body_p = fetch_diag(URL_LOCAL)
            route.fulfill(status=st_p, content_type=ct_p or "application/json", body=body_p)
        pg.route("**/diagnostico.json", _proxy_diag)

    pg.goto(URL_8088 + "/", wait_until="networkidle")

    # Clear localStorage on start and set up an isolated user without touching real data/
    pg.evaluate(
        """() => {
        localStorage.clear();
        syncPush = () => {};
        syncPull = async () => null;
        const u = {id: 'test_diag_user', name: 'TestDiag', color: '#1e3a8a', token: ''};
        localStorage.setItem('b2first_user', JSON.stringify(u));
        localStorage.setItem('ob_test_diag_user', '1');
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

    # Check that the banner is visible on TODAY at the start (no diag in D.log)
    banner_before = pg.evaluate("getComputedStyle(document.getElementById('diagBanner')).display !== 'none'")
    assert banner_before is True, "Expected diagBanner to be visible before completing diagnostic"

    # Start the diagnostic from the TODAY banner
    pg.click("#diagBannerBtn")
    pg.wait_for_selector("#diagQuestionCard", timeout=5000)

    # Assert 4: an explain does NOT appear in the DOM before finishing
    sample_explain = items[0]["explain"]
    dom_during = pg.evaluate("document.documentElement.innerHTML")
    for it in items:
        assert it["explain"] not in dom_during, f"Explain leaked in DOM before finishing: {it['id']}"
        assert it["explain"][:60] not in dom_during, f"Explain prefix leaked in DOM before finishing: {it['id']}"
    out["4_no_explain_before_finish"] = True

    # Assert 5: answer everything correctly (using answer from the JSON) -> D.log has type:'diag' with correct===12 and D.errs empty
    for idx, it in enumerate(items):
        ans = it["answer"]
        pg.click(f"#diagOptions button[data-opt='{ans}']")
    pg.wait_for_selector("#diagResultCard", timeout=5000)

    res_all_ok = pg.evaluate(
        """() => ({
        diagLogs: D.log.filter(x => x.type === 'diag'),
        errs: D.errs,
        diag: D.diag,
        bannerVisible: getComputedStyle(document.getElementById('diagBanner')).display !== 'none',
        scoreText: document.getElementById('diagTotalScore').textContent.trim()
    })"""
    )
    assert len(res_all_ok["diagLogs"]) == 1, f"Expected 1 diag log, got {res_all_ok['diagLogs']}"
    assert res_all_ok["diagLogs"][0]["correct"] == 12, f"Expected correct===12, got {res_all_ok['diagLogs'][0]}"
    assert res_all_ok["diagLogs"][0]["total"] == 12
    assert res_all_ok["errs"] == [], f"Expected D.errs empty on 12/12, got {res_all_ok['errs']}"
    assert res_all_ok["scoreText"] == "12/12"
    out["5_all_correct_12"] = {
        "correct": res_all_ok["diagLogs"][0]["correct"],
        "errs_len": len(res_all_ok["errs"]),
    }

    # Assert 8: the diagnostic banner disappears from TODAY after completing it
    pg.click("nav button[data-view='hoy']")
    banner_after = pg.evaluate("getComputedStyle(document.getElementById('diagBanner')).display")
    assert banner_after == "none", f"Expected diagBanner display 'none' after completion, got {banner_after}"
    out["8_banner_disappears"] = banner_after == "none"

    # Assert 6: answer everything wrong -> 12 new entries in D.errs with valid tax and src:'diag'
    pg.click("nav button[data-view='diag']")
    pg.wait_for_selector("#diagRepeatBtn", timeout=5000)
    pg.click("#diagRepeatBtn")
    pg.wait_for_selector("#diagQuestionCard", timeout=5000)

    for idx, it in enumerate(items):
        wrong_ans = (it["answer"] + 1) % 4
        pg.click(f"#diagOptions button[data-opt='{wrong_ans}']")
    pg.wait_for_selector("#diagResultCard", timeout=5000)

    res_all_wrong = pg.evaluate(
        """() => ({
        errs: D.errs,
        diag: D.diag,
        weakCards: document.querySelectorAll('#diagWeakList .diag-weak-card').length
    })"""
    )
    assert len(res_all_wrong["errs"]) == 12, f"Expected 12 errors in D.errs, got {len(res_all_wrong['errs'])}"
    valid_taxes = {"L-GAP", "G-ERR", "T-MIS", "T-LIM"}
    for e in res_all_wrong["errs"]:
        assert e.get("tax") in valid_taxes, f"Invalid tax in error: {e}"
        assert e.get("src") == "diag", f"Expected src:'diag', got {e}"
        assert 1 <= int(e.get("part", 0)) <= 7, f"Invalid part in error: {e}"
        assert isinstance(e.get("note"), str) and 0 < len(e["note"]) <= 120, f"Invalid note in error: {e}"
    out["6_all_wrong_12_errs"] = len(res_all_wrong["errs"])

    # Assert 7: D.diag.byPart has 7 keys and weakest.length===3
    by_part = res_all_wrong["diag"]["byPart"]
    weakest = res_all_wrong["diag"]["weakest"]
    assert len(by_part) == 7 and set(map(int, by_part.keys())) == {1, 2, 3, 4, 5, 6, 7}, f"Bad byPart: {by_part}"
    assert isinstance(weakest, list) and len(weakest) == 3, f"Bad weakest: {weakest}"
    assert res_all_wrong["weakCards"] == 3
    out["7_byPart_and_weakest"] = {"byPart_keys": len(by_part), "weakest": weakest}

    # Also check that the weakness button goes to PARTS with that filter applied
    first_weak_part = weakest[0]
    pg.click(f"#diagWeakList .diag-go-part[data-part='{first_weak_part}']")
    parts_filtered = pg.evaluate(
        """() => ({
        activeView: document.querySelector('.view.active')?.id,
        filterVal: PARTS_FILTER,
        stepsCount: document.querySelectorAll('#partsList .step').length
    })"""
    )
    assert parts_filtered["activeView"] == "v-partes"
    assert parts_filtered["filterVal"] == first_weak_part
    assert parts_filtered["stepsCount"] == 1

    # Clear localStorage when done
    pg.evaluate("localStorage.clear()")

    # Assert 9: errores_js empty at the end
    assert errores_js == [], f"JS errors found: {errores_js}"
    out["errores_js"] = errores_js
    b.close()

local_srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
