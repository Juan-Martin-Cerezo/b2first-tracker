#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find visible strings that are not translated (or are in the wrong language).

What counts as an offender:

* a visible text node with letters that is **not** inside an element carrying
  ``data-i18n`` / ``data-i18n-html``, does **not** match any value of the active
  language dictionary (``{placeholder}`` treated as a wildcard), and is not on
  the explicit allow-list;
* Spanish text left on screen in English mode, and English text left on screen
  in Spanish mode, minus the same allow-list.

The allow-list is deliberately explicit: proper nouns (B2 First, Cambridge,
Cloudflare, Google, DeepSeek, Azure, Microsoft, Owner), book/site titles, and
Part/P exercise labels. Numbers, dates, times and the throwaway user's own name
are ignored as dynamic values.

    cd tests && uv run --with playwright python ../tools/scan_texts.py

Exit 0 when there are zero offenders; exits 1 and prints them otherwise.
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

URL = os.environ.get("B2_URL", "http://127.0.0.1:8088").rstrip("/")
NAME = "text-scan-user"
PASS = "text-scan-pass-9!"

ALLOW = [
    r"\bB2 First\b", r"\bCambridge\b", r"\bPart(?:s)? [1-7]\b", r"\bP[1-7]\b",
    r"\b(?:FCE|CAE|UoE|PDF|MP3|ZIP|FAQ)\b",
    r"\b(?:Google|Cloudflare|DeepSeek|Azure|Microsoft|Gemini|Owner)\b",
    r"Practice Tests Plus", r"Flo-Joe", r"ExamEnglish", r"Test-English",
    r"Grammar & Vocabulary", r"\bUnit \d+\b", r"\bTest \d+\b",
    r"^B2 First Tracker", r"^Owner$", r"^B2FIRST$",
]
ALLOW_RE = [re.compile(p, re.I) for p in ALLOW]

ES_MARKERS = re.compile(
    r"[áéíóúñ¿¡]|\b(?:el|la|los|las|de|del|para|con|una|tus|tu|por|más|sin|"
    r"como|estudio|etapa|hoy|plan|semana|sesión|puertas|avanzar)\b", re.I)
EN_MARKERS = re.compile(
    r"\b(?:the|your|you|and|with|this|that|from|study|practice|exam|"
    r"stage|today|week|session|plan|gates|advance)\b", re.I)


def api(path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        URL + "/" + path.lstrip("/"), data=data, method=method or ("POST" if data is not None else "GET"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else None


def session():
    """Register/login the throwaway scanner account and reset its document."""
    try:
        user = api("api/login", {"name": NAME, "password": PASS})
    except urllib.error.HTTPError:
        api("api/register", {"name": NAME, "password": PASS})
        user = api("api/login", {"name": NAME, "password": PASS})
    doc = {"log": [], "errs": [], "stage": 0, "settings": {}, "overrides": {},
           "weekOverrides": {}, "mat": {}, "diag": None, "profile": None,
           "onboarded": True, "sessionOffset": 0}
    req = urllib.request.Request(
        URL + "/api/progress?user=" + user["id"], data=json.dumps(doc).encode(),
        method="PUT", headers={"Content-Type": "application/json",
                              "Authorization": "Bearer " + user["token"]})
    urllib.request.urlopen(req, timeout=20).read()
    return user


COLLECT_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const roots = [document.getElementById('sideNav'),
                 document.getElementById('userChip'),
                 document.querySelector('#v-hoy .page-head'),
                 document.querySelector('footer'),
                 document.getElementById('demoBanner'),
                 document.getElementById('onboardingOverlay'),
                 document.getElementById('authOverlay')];
  for (const root of roots) {
    if (!root) continue;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const raw = (node.nodeValue || '').replace(/\s+/g, ' ').trim();
      if (!raw) continue;
      const el = node.parentElement;
      if (!el) continue;
      if (el.closest('script,style')) continue;
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (rect.width === 0 || rect.height === 0 || style.visibility === 'hidden') continue;
      let covered = false;
      let a = el;
      while (a && a !== document.body) {
        if (a.hasAttribute('data-i18n') || a.hasAttribute('data-i18n-html')) { covered = true; break; }
        a = a.parentElement;
      }
      const key = raw + '\u0000' + covered;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({text: raw, covered: covered,
                where: (el.id || el.className || el.tagName || '').toString().slice(0, 60)});
    }
  }
  const dict = (I18N[LANG] || {});
  return {items: out, dict: Object.values(dict), lang: LANG};
}
"""


def strip_tags(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def dict_patterns(values):
    patterns = []
    for value in values:
        plain = strip_tags(value)
        if not plain:
            continue
        parts = re.split(r"\{[^}]+\}", plain)
        regex = ".*?".join(re.escape(p) for p in parts)
        patterns.append(re.compile("^" + regex + "$", re.S))
    return patterns


def allowed(text, user_name):
    if user_name and user_name.lower() in text.lower():
        return True
    if re.fullmatch(r"[\W\d_]+", text):
        return True
    if re.fullmatch(r"\d{1,2}:\d{2}(?:\s*[AP]M)?", text, re.I):
        return True
    if re.fullmatch(r"[A-Z]{1,4}", text):
        return True
    return any(rx.search(text) for rx in ALLOW_RE)


def collect(pg):
    return pg.evaluate(COLLECT_JS)


def scan_language(pg, lang, user_name, view=None):
    pg.evaluate(
        "(l) => { LANG = l; applyI18n(); if (typeof refreshAll === 'function') refreshAll();"
        " if (typeof OB !== 'undefined' && OB.active && typeof obRender === 'function') obRender(); }",
        lang)
    pg.wait_for_timeout(350)
    if view:
        pg.evaluate("(v) => showView(v)", view)
        pg.wait_for_timeout(350)
    data = collect(pg)
    patterns = dict_patterns(data["dict"])
    offenders = []
    for item in data["items"]:
        text = item["text"]
        if len(re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]", "", text)) < 3:
            continue
        if item["covered"] or allowed(text, user_name):
            continue
        if any(rx.match(text) for rx in patterns):
            continue
        if lang == "en" and ES_MARKERS.search(text):
            offenders.append((text, "spanish-in-en", item.get("where", "")))
        elif lang == "es" and EN_MARKERS.search(text):
            offenders.append((text, "english-in-es", item.get("where", "")))
        else:
            offenders.append((text, "no-i18n", item.get("where", "")))
    return offenders, data["items"]


def main():
    user = session()
    all_offenders = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 390, "height": 844},
                              is_mobile=True, has_touch=True)
        pg.goto(URL, wait_until="networkidle")

        # Auth screen: show it (logged out) in both languages.
        pg.evaluate("localStorage.removeItem('b2first_user')")
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(400)
        pg.evaluate("document.getElementById('authOverlay').style.display='flex'")
        for lang in ("en", "es"):
            found, _ = scan_language(pg, lang, user["name"])
            all_offenders += [(lang, "auth", t, why, where) for t, why, where in found]
        pg.evaluate("localStorage.setItem('b2first_user', %s)" % json.dumps(json.dumps(user)))
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(500)
        pg.evaluate(
            "if (typeof finishOnboarding==='function') finishOnboarding();"
        )

        # Onboarding step 1 in both languages.
        pg.evaluate("if (typeof showOnboarding==='function') { showOnboarding(false); OB.step=1; obRender(); }")
        pg.wait_for_timeout(300)
        for lang in ("en", "es"):
            found, _ = scan_language(pg, lang, user["name"])
            all_offenders += [(lang, "onboarding", t, why, where) for t, why, where in found]
        pg.evaluate("hideOnboarding()")

        # The main shell and the two views that show stage names.
        for view in ("hoy", "plan", "progreso"):
            pg.evaluate("(v) => showView(v)", view)
            pg.wait_for_timeout(300)
            for lang in ("en", "es"):
                found, _ = scan_language(pg, lang, user["name"], view)
                all_offenders += [(lang, view, t, why, where) for t, why, where in found]

        browser.close()

    # Deduplicate identical complaints.
    unique = sorted(set(all_offenders))
    if unique:
        print(f"FAIL {len(unique)} untranslated visible string(s):")
        for lang, where, text, why, parent in unique:
            print(f"  [{lang}/{where}] {why} ({parent}): {text!r}")
        return 1
    print("OK 0 untranslated visible strings (en + es, auth + onboarding + today/plan/progress)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
