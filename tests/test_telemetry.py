"""Telemetry + privacy tests (fase 15): POST /api/events, GET /api/metrics,
GET /privacy, the 7-day retention, the IP hash and the Do Not Track contract.

Boots its own server with a temporary DATA_DIR, so nothing touches the real
data/. Playwright covers the footer link and the DNT behaviour (12-13).

Rule under test everywhere: EVENTS, NEVER CONTENT — no free text, no
passwords, no raw IPs land in data/events/.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server as S  # noqa: E402
import store  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="b2telemetry-")
S.DATA_DIR = _tmp
store.DATA_DIR = _tmp
S.PROG_FILE = os.path.join(_tmp, "progress.json")
S.BK_DIR = os.path.join(_tmp, "backups")
S.USERS_FILE = os.path.join(_tmp, "users.json")
S.TOKENS_FILE = os.path.join(_tmp, "tokens.json")
S.USERS_DIR = os.path.join(_tmp, "users")
os.environ["B2_DEMO"] = "0"
os.environ["B2_REGISTER"] = "open"
S.B2_DEMO = False
S.B2_REGISTER = "open"

srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
S.PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{S.PORT}"

out = {}
failed = []


def check(name, cond, detail=""):
    if cond:
        out[name] = {"assert": f"OK {name}"}
    else:
        out[name] = {"assert": f"FALLO {name}" + (f" -- {detail}" if detail else "")}
        failed.append(name)


def req(method, path, body=None, token=None, raw=None):
    """HTTP helper: returns (status, body_text, response_headers)."""
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = None
    hdrs = {}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = "Bearer " + token
    r = urllib.request.Request(URL + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), dict(e.headers)


def events_file(day=None):
    return os.path.join(_tmp, "events", (day or time.strftime("%Y-%m-%d")) + ".jsonl")


def file_lines():
    try:
        with open(events_file(), "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return []


def lines_for(sid):
    return [ln for ln in file_lines() if json.loads(ln).get("sid") == sid]


def batch(sid, events):
    return {"sid": sid, "events": events}


def ev(n, p=None, t=1700000000000):
    return {"n": n, "t": t, "p": p or {}}


# ---------------------------------------------------------------------------
# 1. Valid batch of 5 events -> 200 and 5 JSONL lines for that sid
# ---------------------------------------------------------------------------
st, body, _ = req("POST", "/api/events", batch("tel-t1", [
    ev("app_open", {"ver": "1.0.0"}),
    ev("view_change", {"view": "hoy", "ms": 12}),
    ev("quicklog_save", {"kind": "ue", "part": 3}),
    ev("js_error", {"message_trunc": "Boom test error", "stack_hash": "h123", "view": "hoy"}),
    ev("diag_finish", {"ok": True, "count": 9}),
]))
lines_t1 = lines_for("tel-t1")
check("T1_valid_batch_5_lines",
      st == 200 and json.loads(body).get("accepted") == 5 and len(lines_t1) == 5
      and all(json.loads(ln)["n"] in S.EVENT_NAMES for ln in lines_t1),
      f"st={st} body={body} lines={len(lines_t1)}")

# ---------------------------------------------------------------------------
# 2. Event name outside the whitelist -> discarded, never written
# ---------------------------------------------------------------------------
st, body, _ = req("POST", "/api/events", batch("tel-t2", [
    ev("evil_event", {"view": "x"}),
    ev("__proto__"),
    ev("constructor"),
    {"n": "app_open; DROP TABLE", "t": 1, "p": {}},
]))
check("T2_whitelist_drops_bad_names",
      st == 200 and json.loads(body).get("accepted") == 0 and len(lines_for("tel-t2")) == 0,
      f"st={st} body={body} lines={len(lines_for('tel-t2'))}")

# ---------------------------------------------------------------------------
# 3. Prop with 500 chars of text -> truncated (never stored complete)
# ---------------------------------------------------------------------------
long_text = "A" * 500
st, body, _ = req("POST", "/api/events", batch("tel-t3", [
    ev("view_change", {"view": long_text}),
]))
content = "\n".join(file_lines())
stored_view = ""
for ln in lines_for("tel-t3"):
    stored_view = json.loads(ln)["p"].get("view", "")
check("T3_long_prop_truncated",
      st == 200 and long_text not in content and len(stored_view) <= 64 and len(stored_view) == 64,
      f"st={st} stored_len={len(stored_view)}")

# ---------------------------------------------------------------------------
# 4. {"password": "x"} in an event -> that field is never stored
# ---------------------------------------------------------------------------
st, body, _ = req("POST", "/api/events", batch("tel-t4", [
    ev("app_open", {"password": "x", "view": "hoy"}),
]))
lines_t4 = lines_for("tel-t4")
check("T4_password_field_dropped",
      st == 200 and len(lines_t4) == 1 and "password" not in lines_t4[0] and '"x"' not in lines_t4[0],
      f"line={lines_t4[0] if lines_t4 else '<none>'}")

# ---------------------------------------------------------------------------
# 5. The JSONL never contains the IP in clear (127.0.0.1 absent)
# ---------------------------------------------------------------------------
content = "\n".join(file_lines())
check("T5_no_clear_ip_in_jsonl", "127.0.0.1" not in content,
      "clear IP found in the event log")

# ---------------------------------------------------------------------------
# 6. Batch of 51 events -> 413
# ---------------------------------------------------------------------------
st, body, _ = req("POST", "/api/events", batch("tel-t6", [ev("app_open") for _ in range(51)]))
check("T6_batch_51_events_413", st == 413, f"st={st} body={body}")

# ---------------------------------------------------------------------------
# 7. Batch of 40 KB -> 413
# ---------------------------------------------------------------------------
raw_40k = json.dumps(batch("tel-t7", [ev("view_change", {"view": "B" * 40000})])).encode("utf-8")
st, body, _ = req("POST", "/api/events", raw=raw_40k)
check("T7_batch_40kb_413", st == 413 and len(raw_40k) > 32 * 1024, f"st={st} size={len(raw_40k)}")

# ---------------------------------------------------------------------------
# 8. 61 batches in an hour -> 429 (60 batches/hour/IP)
# ---------------------------------------------------------------------------
S._RATE.clear()
codes = []
for i in range(61):
    st, body, _ = req("POST", "/api/events", batch("tel-t8", [ev("app_open", {"count": i})]))
    codes.append(st)
check("T8_rate_limit_61_batches_429",
      codes.count(200) == 60 and codes[-1] == 429,
      f"codes={codes[:3]}...{codes[-3:]} 200s={codes.count(200)}")

# ---------------------------------------------------------------------------
# 9. GET /api/metrics: 401 / 403 / owner 200 with events/errors/ai/users_active
# ---------------------------------------------------------------------------
S._RATE.clear()
S.migrate_legacy()
st_n, body_n, _ = req("GET", "/api/metrics")
st_r, body_r, _ = req("POST", "/api/register", {"name": "tel-user", "password": "telemetry-pass-1"})
user_tok = json.loads(body_r).get("token") if st_r == 200 else None
st_u, body_u, _ = req("GET", "/api/metrics", token=user_tok)
st_l, body_l, _ = req("POST", "/api/login", {"name": "owner", "password": S.OWNER_PASSWORD})
owner_tok = json.loads(body_l).get("token") if st_l == 200 else None
st_o, body_o, _ = req("GET", "/api/metrics", token=owner_tok)
m = json.loads(body_o) if st_o == 200 else {}
check("T9_metrics_auth_401_403_owner200",
      st_n == 401 and st_u == 403 and st_o == 200
      and all(k in m for k in ("events", "errors", "ai", "users_active")),
      f"st_n={st_n} st_u={st_u} st_o={st_o} keys={sorted(m)}")
check("T9b_metrics_aggregates_no_stacks",
      m.get("events", {}).get("app_open", 0) >= 1
      and any(e.get("n") == "js_error" and e.get("last_message_trunc") == "Boom test error"
              for e in m.get("errors", []))
      and "stack" not in json.dumps(m.get("errors", [])).lower(),
      f"events={m.get('events')} errors={m.get('errors')}")

# ---------------------------------------------------------------------------
# 10. Retention: an event file from 8 days ago is deleted on write
# ---------------------------------------------------------------------------
old_day = (date.today() - timedelta(days=8)).isoformat()
old_path = events_file(old_day)
os.makedirs(os.path.dirname(old_path), exist_ok=True)
with open(old_path, "w", encoding="utf-8") as f:
    f.write(json.dumps({"ts": old_day + "T00:00:00Z", "sid": "old", "uid": None,
                        "n": "app_open", "p": {}, "ip_hash": "0" * 16}) + "\n")
S._RATE.clear()
st, body, _ = req("POST", "/api/events", batch("tel-t10", [ev("app_open")]))
check("T10_retention_8_days_deleted",
      st == 200 and not os.path.exists(old_path) and len(lines_for("tel-t10")) == 1,
      f"st={st} old_exists={os.path.exists(old_path)}")

# ---------------------------------------------------------------------------
# 11. GET /privacy -> 200 text/html with "Privacy Policy" and "Ley 25.326"
# ---------------------------------------------------------------------------
st, body, hdrs = req("GET", "/privacy")
ctype = hdrs.get("Content-Type", "")
check("T11_privacy_page",
      st == 200 and "text/html" in ctype and "Privacy Policy" in body and "Ley 25.326" in body
      and "security/advisories/new" in body and "TODO_OWNER_EMAIL" not in body,
      f"st={st} ctype={ctype}")

# ---------------------------------------------------------------------------
# Extra contract from B: a valid token associates uid, an invalid one is
# ignored with uid:null (never 401), and the raw IP is still not stored.
# ---------------------------------------------------------------------------
S._RATE.clear()
st, body, _ = req("POST", "/api/events", batch("tel-uid", [ev("app_open")]), token=owner_tok or "")
st2, body2, _ = req("POST", "/api/events", batch("tel-uid-bad", [ev("app_open")]), token="not-a-real-token")
uid_lines = lines_for("tel-uid") + lines_for("tel-uid-bad")
uids = [json.loads(ln).get("uid") for ln in uid_lines]
content = "\n".join(file_lines())
check("T12_uid_association_no_401",
      st == 200 and st2 == 200 and uids == ["owner", None] and "127.0.0.1" not in content,
      f"st={st} st2={st2} uids={uids}")

# ---------------------------------------------------------------------------
# 12. (Playwright) the footer links to /privacy and errores_js is empty
# 13. (Playwright) with navigator.doNotTrack='1' nothing hits /api/events
# ---------------------------------------------------------------------------
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    b = p.chromium.launch()

    # 12. footer link + no JS errors
    pg = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    errores_js = []
    pg.on("pageerror", lambda e: errores_js.append(str(e)))
    pg.goto(URL + "/", wait_until="networkidle")
    pg.wait_for_timeout(500)
    link = pg.evaluate(
        """() => {
        const a = document.querySelector('footer a[href="/privacy"]');
        return a ? {href: a.getAttribute('href'), text: a.textContent.trim()} : null;
    }"""
    )
    reg_note = pg.evaluate(
        """() => {
        const box = document.getElementById('authRegister');
        return box ? box.textContent.includes('By creating an account you accept the') &&
                     !!box.querySelector('a[href="/privacy"]') &&
                     !!box.querySelector('a[href="/terms"]') : false;
    }"""
    )
    check("T13_footer_privacy_link",
          link is not None and link.get("href") == "/privacy" and reg_note and errores_js == [],
          f"link={link} reg_note={reg_note} errores_js={errores_js}")
    out["errores_js"] = errores_js
    pg.close()

    # 13. Do Not Track: no request ever reaches /api/events
    ctx = b.new_context()
    ctx.add_init_script(
        """Object.defineProperty(navigator, 'doNotTrack', {get: function(){return '1'}});
Object.defineProperty(window, 'doNotTrack', {get: function(){return '1'}});"""
    )
    pg2 = ctx.new_page()
    event_requests = []
    pg2.on("request", lambda r: event_requests.append(r.url) if "/api/events" in r.url else None)
    pg2.goto(URL + "/", wait_until="networkidle")
    pg2.wait_for_timeout(400)
    pg2.evaluate("track('app_open');track('view_change',{view:'plan'});tevFlush();")
    pg2.evaluate("showView('plan')")
    pg2.wait_for_timeout(400)
    pg2.evaluate("tevFlush();")
    pg2.wait_for_timeout(300)
    dnt_ok = pg2.evaluate("navigator.doNotTrack")
    check("T14_dnt_sends_nothing",
          dnt_ok == "1" and event_requests == [],
          f"dnt={dnt_ok!r} requests={event_requests}")
    ctx.close()
    b.close()

srv.shutdown()
print(json.dumps(out, ensure_ascii=False, indent=1))
print("TELEMETRY_EXIT", 1 if failed else 0)
sys.exit(1 if failed else 0)
