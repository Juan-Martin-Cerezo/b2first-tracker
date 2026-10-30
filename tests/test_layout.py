"""Phase 27 acceptance: no broken screens, no misaligned grids.

Standalone Playwright suite. It logs in through helpers.py, walks every view at
three viewports (360x740 phone, 768x1024 tablet, 1440x900 desktop) in English
and Spanish, and checks:

  * document.scrollWidth <= innerWidth + 1 (no sideways scrolling);
  * no two sibling cards/tiles in the same grid/flex container overlap;
  * every button is at least 40x40 px;
  * no visible element is painted past innerWidth;
  * zero console errors.

Run with:  uv run --with playwright python test_layout.py
"""
import json
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from helpers import login_owner, login_user

URL = "http://127.0.0.1:8088/"
NAME = "layout-suite"
PASS = "layout-suite-pass-9"

VIEWPORTS = [
    ("phone", 360, 740, True),
    ("tablet", 768, 1024, True),
    ("desktop", 1440, 900, False),
]

# English labels are shorter than Spanish: several checks only fail in one of
# the two, so every page view is measured twice.
PAGE_VIEWS = [
    "today", "plan", "log", "stats", "errors", "books",
    "material", "speaking", "exam", "diagnostic", "practice",
]
OVERLAY_VIEWS = ["onboarding", "auth"]


def api(path, payload=None, token=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method or ("POST" if data is not None else "GET"),
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req) as r:
        body = r.read().decode()
        try:
            return json.loads(body)
        except ValueError:
            return body


def seed_progress(user):
    """Deterministic content so tables, cards and the material grid are full."""
    logs = [
        {"type": "ue", "part": 1, "date": "2026-10-29", "correct": 6, "total": 8, "min": 8,
         "note": "Practice Tests Plus — Test 3, Part 1"},
        {"type": "ue", "part": 4, "date": "2026-10-28", "correct": 4, "total": 6, "min": 12},
        {"type": "ue", "part": 6, "date": "2026-10-27", "correct": 3, "total": 6, "min": 20},
        {"type": "lp", "part": 2, "date": "2026-10-26", "correct": 7, "total": 10, "min": 10},
        {"type": "w", "kind": "Essay", "date": "2026-10-25", "score": 16, "min": 42},
        {"type": "l", "date": "2026-10-24", "correct": 24, "total": 30, "p2": 2, "min": 40,
         "ref": "Practice Tests Plus B2 First Vol 1 — Test 2"},
        {"type": "sp", "part": 2, "date": "2026-10-23", "score": 4, "min": 15},
        {"type": "rue", "date": "2026-10-22", "correct": 41, "total": 52, "min": 70},
        {"type": "fw", "date": "2026-10-21", "s1": 16, "s2": 15, "min": 79},
        {"type": "sf", "date": "2026-10-19", "ok": True},
    ]
    errs = [
        {"date": "2026-10-29", "code": "L-GAP",
         "desc": "Did not know 'out of the blue' and picked a plausible collocation.",
         "fix": "Review idioms with 'blue' in the vocabulary notebook."},
        {"date": "2026-10-28", "code": "G-ERR",
         "desc": "Inversion after 'Seldom' with the auxiliary in the wrong position.",
         "fix": "Write five inversion sentences."},
        {"date": "2026-10-27", "code": "T-MIS",
         "desc": "Fell for the date distractor in Listening Part 3.",
         "fix": "Underline the second mention before answering."},
    ]
    diag = {
        "date": "2026-10-18", "correct": 8, "total": 12,
        "byPart": {
            "1": {"ok": 2, "n": 2}, "2": {"ok": 1, "n": 2}, "3": {"ok": 2, "n": 2},
            "4": {"ok": 1, "n": 2}, "5": {"ok": 1, "n": 1}, "6": {"ok": 0, "n": 2},
            "7": {"ok": 1, "n": 1},
        },
        "weakest": [6, 4, 7],
    }
    doc = {
        "log": logs, "errs": errs, "examDates": [], "stage": 1,
        "settings": {"lang": "en"},
        "overrides": {}, "weekOverrides": {}, "mat": {},
        "diag": diag,
        "profile": {
            "examDate": "2026-11-15", "targetGrade": "A",
            "skills": {"rue": 4, "w": 3, "l": 4, "sp": 3}, "hoursWeek": 4,
            "days": ["mon", "fri"], "struggles": ["L-GAP"],
            "strugglesDeclared": ["Lexical gap"], "declaredAt": "2026-10-01",
        },
        "onboarded": True, "sessionOffset": 0,
    }
    api("api/progress?user=" + user["id"], doc, token=user["token"], method="PUT")


CHECK_JS = r"""
() => {
  const W = window.innerWidth, out = {
    scrollWidth: document.documentElement.scrollWidth, innerWidth: W,
    overlap: [], small: [], beyond: [], checked: 0
  };
  const rect = el => el.getBoundingClientRect();
  const isVisible = el => {
    if (!el || !el.isConnected) return false;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false;
    const r = rect(el);
    return r.width > 0.5 && r.height > 0.5;
  };
  const desc = el => {
    const id = el.id ? '#' + el.id : '';
    const cls = (typeof el.className === 'string' && el.className.trim())
      ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    const txt = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 32);
    return el.tagName.toLowerCase() + id + cls + (txt ? ' "' + txt + '"' : '');
  };
  const insideScroller = el => {
    let p = el.parentElement;
    while (p && p !== document.documentElement) {
      if (/auto|scroll|hidden|clip/.test(getComputedStyle(p).overflowX)) return true;
      p = p.parentElement;
    }
    return false;
  };

  // 1. card/tile siblings must not overlap inside the same grid/flex container
  const SEL = '.card,.tile,.stat,.stat-card';
  const groups = new Map();
  document.querySelectorAll(SEL).forEach(el => {
    if (!isVisible(el)) return;
    const p = el.parentElement;
    if (!p) return;
    if (!/grid|flex/.test(getComputedStyle(p).display)) return;
    if (!groups.has(p)) groups.set(p, []);
    groups.get(p).push(el);
  });
  for (const [p, els] of groups) {
    for (let i = 0; i < els.length; i++) {
      for (let j = i + 1; j < els.length; j++) {
        const a = els[i], b = els[j];
        const sa = getComputedStyle(a).position, sb = getComputedStyle(b).position;
        if (sa === 'absolute' || sa === 'fixed' || sb === 'absolute' || sb === 'fixed') continue;
        const ra = rect(a), rb = rect(b);
        const ox = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
        const oy = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
        if (ox > 1 && oy > 1) {
          out.overlap.push({parent: desc(p), a: desc(a), b: desc(b),
                            px: [Math.round(ox), Math.round(oy)]});
        }
      }
    }
  }

  // 2. every button is at least 40x40
  document.querySelectorAll('button').forEach(el => {
    if (!isVisible(el)) return;
    const r = rect(el);
    if (r.width < 39.5 || r.height < 39.5) {
      out.small.push({el: desc(el), w: Math.round(r.width * 10) / 10,
                      h: Math.round(r.height * 10) / 10});
    }
  });

  // 3. nothing painted past the viewport edge (content inside a table's own
  //    horizontal scroller is clipped, not painted outside)
  document.querySelectorAll('body *').forEach(el => {
    if (['SCRIPT', 'STYLE', 'LINK', 'HEAD', 'META', 'TITLE'].includes(el.tagName)) return;
    if (!isVisible(el)) return;
    out.checked++;
    if (insideScroller(el)) return;
    const r = rect(el);
    if (r.right > W + 1 || r.left < -1) {
      out.beyond.push({el: desc(el), left: Math.round(r.left), right: Math.round(r.right)});
    }
  });
  return out;
}
"""


SPEAKING_JS = """
() => {
  selectSessionStudio('fri-b');
  document.getElementById('spkPanel').style.display = 'block';
  document.getElementById('livePanel').style.display = 'block';
  renderSpeakingReport({
    bands: {grammar_vocabulary: 4, discourse_management: 3, pronunciation: null,
            interactive_communication: null},
    derived: {pronunciation_source: 'none'},
    metrics: {wpm: 132, fillers: 7, longest_silence: 2.4, speech_ratio: 0.71},
    proxies: {initiations: 4, response_latency_ms_p50: 820, question_ratio: 0.3,
              overlap_ms: 400},
    worst: [{w: 'thoroughly', score: 42, phoneme: 'θ', phoneme_score: 35},
            {w: 'entrepreneur', score: 51}],
    evidence: [{quote: 'Whereas the former illustrates a clear benefit, the latter seems to convey the opposite.',
                note: 'Good contrast'}],
    fixes: ['Stress the first syllable in photography.',
            'Use a fuller range of discourse markers.',
            'Reduce filler sounds between ideas.']
  });
}
"""


def goto_view(pg, name):
    hidden = {"graf", "err", "libros", "ia", "diag"}
    if name in hidden:
        if pg.evaluate("getComputedStyle(document.getElementById('navMoreBtn')).display") != "none":
            pg.evaluate("document.getElementById('navMoreBtn').click()")
            pg.wait_for_timeout(60)
    pg.click(f"nav button[data-view='{name}']")
    pg.wait_for_timeout(250)


def show(pg, view, lang):
    """Put the app in the requested view (and language for page views)."""
    if view == "today":
        goto_view(pg, "hoy")
    elif view == "plan":
        goto_view(pg, "plan")
    elif view in ("log", "stats"):
        goto_view(pg, "prog")
        table = "logTable" if view == "log" else "statsTable"
        pg.evaluate("document.getElementById('%s').scrollIntoView({block:'center'})" % table)
        pg.wait_for_timeout(150)
    elif view == "errors":
        goto_view(pg, "err")
    elif view in ("books", "material"):
        goto_view(pg, "libros")
        pg.wait_for_timeout(700)
        target = "bookList" if view == "books" else "matList"
        pg.evaluate("document.getElementById('%s').scrollIntoView({block:'start'})" % target)
        pg.wait_for_timeout(200)
    elif view == "speaking":
        goto_view(pg, "hoy")
        pg.evaluate(SPEAKING_JS)
        pg.wait_for_timeout(200)
        pg.evaluate("document.getElementById('spkReportPanel').scrollIntoView({block:'center'})")
        pg.wait_for_timeout(150)
    elif view == "exam":
        goto_view(pg, "exam")
    elif view == "diagnostic":
        goto_view(pg, "diag")
    elif view == "practice":
        goto_view(pg, "practice")
    elif view == "onboarding":
        pg.evaluate("showOnboarding()")
        pg.wait_for_timeout(200)
    elif view == "auth":
        pass
    if lang == "es" and view not in OVERLAY_VIEWS:
        pg.evaluate("setLang('es')")
        pg.wait_for_timeout(200)
    elif lang == "en" and view not in OVERLAY_VIEWS:
        pg.evaluate("if (LANG !== 'en') setLang('en')")
        pg.wait_for_timeout(120)


def measure(pg, rows, lang, viewport, view):
    data = pg.evaluate(CHECK_JS)
    row = {
        "lang": lang, "viewport": viewport, "view": view,
        "scroll": data["scrollWidth"] <= data["innerWidth"] + 1,
        "scrollWidth": data["scrollWidth"], "innerWidth": data["innerWidth"],
        "overlap": data["overlap"], "small": data["small"], "beyond": data["beyond"],
        "checked": data["checked"],
    }
    rows.append(row)
    flag = "" if (row["scroll"] and not row["overlap"] and not row["small"] and not row["beyond"]) else "  <-- FAIL"
    print(
        f"{lang.upper():2} {viewport:7} {view:12} scroll={row['scrollWidth']}/{row['innerWidth']} "
        f"overlap={len(row['overlap'])} small={len(row['small'])} beyond={len(row['beyond'])}{flag}"
    )
    return row


def main():
    rows = []
    console_errors = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- one login through helpers, reused by every context -----------
        boot = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = boot.new_page()
        pg.goto(URL, wait_until="networkidle")
        try:
            user = login_user(pg, URL, NAME, PASS)
        except urllib.error.HTTPError:
            user = login_owner(pg, URL)
        boot.close()
        seed_progress(user)

        for label, w, h, mobile in VIEWPORTS:
            ctx = browser.new_context(
                viewport={"width": w, "height": h},
                is_mobile=mobile, has_touch=mobile, device_scale_factor=1,
            )
            pg = ctx.new_page()
            pg.add_init_script(
                "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(user))
            )
            pg.on("pageerror", lambda e: page_errors.append(str(e)))
            pg.on(
                "console",
                lambda m: console_errors.append(m.text)
                if m.type == "error" and "Failed to load resource" not in m.text else None,
            )
            pg.goto(URL, wait_until="networkidle")
            pg.wait_for_timeout(500)
            if pg.evaluate(
                "typeof finishOnboarding==='function' && document.getElementById('onboardingOverlay')"
                " && document.getElementById('onboardingOverlay').style.display==='flex'"
            ):
                pg.evaluate("finishOnboarding()")
                pg.wait_for_timeout(200)

            for lang in ("en", "es"):
                for view in PAGE_VIEWS:
                    show(pg, view, lang)
                    measure(pg, rows, lang, label, view)

            # overlays have no language switch of their own (auth is shown
            # before a document exists; onboarding copy is English in both)
            pg.evaluate("hideOnboarding()")
            pg.evaluate("if (LANG !== 'en') setLang('en')")
            pg.wait_for_timeout(150)
            show(pg, "onboarding", "en")
            measure(pg, rows, "en", label, "onboarding")
            pg.evaluate("obNext(); obNext();")
            pg.wait_for_timeout(250)
            measure(pg, rows, "en", label, "onboarding-step3")
            pg.evaluate("hideOnboarding()")
            pg.evaluate("if (LANG !== 'en') setLang('en')")
            ctx.close()

            # auth overlay needs a context with no session
            actx = browser.new_context(
                viewport={"width": w, "height": h},
                is_mobile=mobile, has_touch=mobile, device_scale_factor=1,
            )
            apg = actx.new_page()
            apg.on("pageerror", lambda e: page_errors.append(str(e)))
            apg.on(
                "console",
                lambda m: console_errors.append(m.text)
                if m.type == "error" and "Failed to load resource" not in m.text else None,
            )
            apg.goto(URL, wait_until="networkidle")
            apg.wait_for_timeout(500)
            measure(apg, rows, "en", label, "auth")
            actx.close()

        browser.close()

    # --- summary ---------------------------------------------------------
    print()
    print("=" * 78)
    print(f"{'viewport':8} {'view':18} {'scroll':>10} {'overlap':>8} {'small':>7} {'beyond':>7}")
    print("-" * 78)
    total = {"scroll": 0, "overlap": 0, "small": 0, "beyond": 0, "checked": 0}
    for row in rows:
        total["overlap"] += len(row["overlap"])
        total["small"] += len(row["small"])
        total["beyond"] += len(row["beyond"])
        total["checked"] += row["checked"]
        if row["scroll"]:
            total["scroll"] += 1
        print(
            f"{row['viewport']:8} {row['lang'] + ' ' + row['view']:18} "
            f"{(str(row['scrollWidth']) + '/' + str(row['innerWidth'])):>10} "
            f"{len(row['overlap']):>8} {len(row['small']):>7} {len(row['beyond']):>7}"
        )
    print("-" * 78)
    print(
        f"TOTAL    {len(rows):3d} snapshots        "
        f"scroll_ok={total['scroll']}/{len(rows)} overlap={total['overlap']} "
        f"small={total['small']} beyond={total['beyond']} "
        f"elements_checked={total['checked']}"
    )
    print("=" * 78)

    failures = []
    for row in rows:
        tag = f"{row['lang']} {row['viewport']} {row['view']}"
        if not row["scroll"]:
            failures.append(f"{tag}: horizontal scroll {row['scrollWidth']}>{row['innerWidth']}")
        if row["overlap"]:
            failures.append(f"{tag}: {len(row['overlap'])} overlapping sibling cards: {row['overlap'][:2]}")
        if row["small"]:
            failures.append(f"{tag}: {len(row['small'])} buttons under 40x40: {row['small'][:3]}")
        if row["beyond"]:
            failures.append(f"{tag}: {len(row['beyond'])} elements past the viewport: {row['beyond'][:3]}")
    if page_errors:
        failures.append(f"page errors: {page_errors}")
    if console_errors:
        failures.append(f"console errors: {console_errors}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        print("VERDICT: FAIL")
        sys.exit(1)
    print("\nVERDICT: ok")


if __name__ == "__main__":
    main()
