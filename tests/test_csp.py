#!/usr/bin/env python3
"""CSP enforcement test (fase G): the tracker must run with zero violations.

The server emits ``script-src 'self' 'sha256-…' https://static.cloudflareinsights.com``
for /app, with one hash per inline <script> body, no ``'strict-dynamic'`` (so the
Cloudflare Web Analytics beacon host allowlist is honoured), and no ``'unsafe-hashes'``:
the document has no inline on* handler attributes left, because every control is wired
through data-* attributes and one delegated listener. If tools/csp_hashes.py
missed a script block, the browser reports a ``securitypolicyviolation`` event
(and a console error) as soon as it runs.

This suite loads the real app on an isolated server, walks every view (today,
plan, log, stats, books/resources, speaking, exam, diagnostics, onboarding and
the auth overlay) and fails on the first violation.

Run:  cd tests && uv run --with playwright python test_csp.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
NAME = "csp-suite"
PASS = "csp-suite-pass-9"

VIOLATIONS = []
CONSOLE = []

INIT_SCRIPT = """
window.addEventListener('securitypolicyviolation', (e) => {
  try {
    window.__cspViolation({
      directive: e.effectiveDirective || e.violatedDirective || '',
      blocked: e.blockedURI || '',
      sample: (e.sample || '').slice(0, 200),
      source: (e.sourceFile || '').slice(0, 200),
      line: e.lineNumber || 0
    });
  } catch (_) {}
});
"""

VIEWS = ["hoy", "plan", "prog", "practice", "resources", "ia", "exam", "diag"]


def header_check():
    """The served /app CSP must be small and free of 'unsafe-hashes'.

    Without inline handlers the directive only carries the two <script> hashes,
    so it stays far below the proxy buffer that used to pressure the header.
    """
    import urllib.request

    with urllib.request.urlopen(URL + "app") as r:
        csp = r.headers.get("Content-Security-Policy", "")
    script_src = csp.split("script-src", 1)[1].split(";", 1)[0] if "script-src" in csp else ""
    connect_src = csp.split("connect-src", 1)[1].split(";", 1)[0] if "connect-src" in csp else ""
    return {
        "bytes": len(csp),
        "unsafe_hashes": "'unsafe-hashes'" in csp,
        "strict_dynamic": "'strict-dynamic'" in script_src,
        "hashes": csp.count("'sha256-"),
        "script_src": script_src.strip(),
        "connect_src": connect_src.strip(),
        "ok": (len(csp) < 1024
               and "'unsafe-hashes'" not in csp
               and "'unsafe-inline'" not in script_src
               and "'strict-dynamic'" not in script_src
               and "'self'" in script_src
               and "'sha256-" in script_src
               and "https://static.cloudflareinsights.com" in script_src
               and "https://cloudflareinsights.com" in connect_src
               and "https://static.cloudflareinsights.com" in connect_src),
    }


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.expose_function("__cspViolation", lambda v: VIOLATIONS.append(v))
        page.add_init_script(INIT_SCRIPT)
        page.on("console", lambda msg: CONSOLE.append(msg.text))

        page.goto(URL + "app", wait_until="networkidle")
        login_user(page, URL, NAME, PASS)
        page.wait_for_timeout(300)

        # Every top-level view the nav exposes (books is folded into resources).
        for view in VIEWS:
            page.evaluate("(v) => { try { showView(v); } catch (e) {} }", view)
            page.wait_for_timeout(120)

        # Log modal, onboarding wizard and auth overlay build extra markup.
        page.evaluate("""() => {
            for (const fn of ['openSoloModal', 'showOnboarding', 'hideOnboarding',
                              'showAuthOverlay']) {
                try { window[fn](); } catch (e) {}
            }
            try { showView('hoy'); } catch (e) {}
        }""")
        page.wait_for_timeout(300)
        browser.close()

    banner = [m for m in CONSOLE
              if "Content Security Policy" in m or "Refused to" in m]
    payload = {
        "violations": VIOLATIONS,
        "console_csp": banner[:10],
        "views": VIEWS,
        "header": header_check(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    ok = (not VIOLATIONS and not banner
          and payload["header"]["ok"])
    print("CSP_EXIT", 0 if ok else 1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
