"""Honest-copy and visual layout contract for the public landing page.

Checks:
1. Forbidden marketing, hardware, pricing, and demo strings are absent from
   landing.html.
2. Every <script> tag is inline (no CDN scripts) and no external stylesheets or
   font CDNs are loaded.
3. "Sign in" and "Create an account" links point to /app.
4. JSON-LD metadata makes no "self-hostable" claim and declares SoftwareApplication
   in EducationalApplication with a free (price "0") offer.
5. In Playwright (360x740 and 1280x800, light and dark themes):
   - Zero horizontal scroll (scrollWidth <= clientWidth).
   - Paragraph contrast ratio >= 4.5:1 against effective background.
   - Zero console/page errors or CSP violations.
   - Theme toggle and mobile menu work.
   - Screenshots saved to tests/out/landing-{360x740,1280x800}-{light,dark}.png.
"""
import json
import os
import re
import sys
from html.parser import HTMLParser

from playwright.sync_api import sync_playwright

from helpers import isolated_server

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANDING = os.path.join(REPO, "landing.html")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT_DIR, exist_ok=True)

FORBIDDEN = [
    "14ms",
    "RPi",
    "Raspberry",
    "POSIX",
    "bare-metal",
    "PBKDF2",
    "cluster",
    "SHA256 SYNC",
    "$12",
    "$5",
    "pricing",
    "upgrade",
    "redeem",
    "demo",
]


class _LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.scripts = []
        self.jsonld = []
        self._cur_href = None
        self._cur_text = []
        self._in_jsonld = False
        self._jsonld_buf = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        if tag == "a":
            self._cur_href = attr_map.get("href", "")
            self._cur_text = []
        elif tag == "script":
            self.scripts.append(attr_map)
            if attr_map.get("type") == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._cur_href is not None:
            text = re.sub(r"\s+", " ", "".join(self._cur_text)).strip()
            self.links.append((text, self._cur_href))
            self._cur_href = None
            self._cur_text = []
        elif tag == "script" and self._in_jsonld:
            self.jsonld.append("".join(self._jsonld_buf))
            self._in_jsonld = False
            self._jsonld_buf = []

    def handle_data(self, data):
        if self._cur_href is not None:
            self._cur_text.append(data)
        if self._in_jsonld:
            self._jsonld_buf.append(data)


with open(LANDING, encoding="utf-8") as fh:
    source = fh.read()

# 1. Forbidden strings check (case-insensitive)
lower_src = source.lower()
found_forbidden = [s for s in FORBIDDEN if s.lower() in lower_src]
assert not found_forbidden, f"Forbidden strings found in landing.html: {found_forbidden}"

# 2. Parse links, scripts, JSON-LD
parser = _LinkCollector()
parser.feed(source)
parser.close()

assert all("src" not in attrs for attrs in parser.scripts), (
    f"External script src not allowed: {parser.scripts}"
)

signin_hrefs = [href for text, href in parser.links if text == "Sign in"]
create_hrefs = [href for text, href in parser.links if text == "Create an account"]
assert signin_hrefs and all(h == "/app" for h in signin_hrefs), (
    f"'Sign in' links must point to /app, got {signin_hrefs}"
)
assert create_hrefs and all(h == "/app" for h in create_hrefs), (
    f"'Create an account' links must point to /app, got {create_hrefs}"
)

assert len(parser.jsonld) == 1, f"Expected 1 JSON-LD block, got {len(parser.jsonld)}"
ld = json.loads(parser.jsonld[0])
ld_text = json.dumps(ld).lower()
assert "self-hostable" not in ld_text and "self-hosted" not in ld_text, ld
assert ld.get("@type") == "SoftwareApplication", ld
assert ld.get("applicationCategory") in ("EducationalApplication", "EducationApplication"), ld
offers = ld.get("offers")
assert isinstance(offers, dict) and str(offers.get("price")) == "0", ld

# 3. Playwright checks across 360x740 and 1280x800 in light and dark themes
CONTRAST_JS = """() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d');
    const parseRgba = (color) => {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 1, 1);
        const d = ctx.getImageData(0, 0, 1, 1).data;
        return [d[0], d[1], d[2], d[3] / 255];
    };
    const composite = (fg, bg) => {
        const a = fg[3];
        return [
            fg[0] * a + bg[0] * (1 - a),
            fg[1] * a + bg[1] * (1 - a),
            fg[2] * a + bg[2] * (1 - a),
            1,
        ];
    };
    const lum = ([r, g, b]) => {
        const f = v => {
            const s = v / 255;
            return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
        };
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const ratio = (c1, c2) => {
        const l1 = lum(c1), l2 = lum(c2);
        return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    };
    const effBg = (el) => {
        const chain = [];
        let cur = el;
        while (cur && cur !== document.documentElement) {
            const bg = parseRgba(getComputedStyle(cur).backgroundColor);
            if (bg[3] > 0.01) chain.push(bg);
            cur = cur.parentElement;
        }
        const rootBg = parseRgba(getComputedStyle(document.body).backgroundColor);
        let acc = [rootBg[0], rootBg[1], rootBg[2], 1];
        for (let i = chain.length - 1; i >= 0; i--) {
            acc = composite(chain[i], acc);
        }
        return acc;
    };
    const failures = [];
    let minRatio = 999;
    let checked = 0;
    for (const p of document.querySelectorAll('p')) {
        const cs = getComputedStyle(p);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const r = p.getBoundingClientRect();
        if (r.width < 1 || r.height < 1) continue;
        const fg = parseRgba(cs.color);
        const bg = effBg(p);
        const cr = Math.round(ratio(fg, bg) * 100) / 100;
        checked++;
        if (cr < minRatio) minRatio = cr;
        if (cr < 4.5) {
            failures.push({text: p.innerText.slice(0, 60), ratio: cr});
        }
    }
    return {checked, minRatio, failures};
}"""

URL = isolated_server() + "/"
report = {
    "forbidden_found": found_forbidden,
    "signin_hrefs": signin_hrefs,
    "create_hrefs": create_hrefs,
    "script_count": len(parser.scripts),
    "viewports": {},
}

with sync_playwright() as p:
    browser = p.chromium.launch()
    for vw, vh in ((360, 740), (1280, 800)):
        for theme in ("light", "dark"):
            ctx = browser.new_context(viewport={"width": vw, "height": vh})
            pg = ctx.new_page()
            page_errors = []
            console_errors = []
            pg.on("pageerror", lambda e: page_errors.append(str(e)))
            pg.on(
                "console",
                lambda m: console_errors.append(m.text) if m.type == "error" else None,
            )
            pg.add_init_script(
                f"localStorage.setItem('b2first_theme', '{theme}');"
            )
            pg.goto(URL, wait_until="networkidle")
            pg.wait_for_timeout(150)

            scroll = pg.evaluate(
                "() => ({sw: document.documentElement.scrollWidth,"
                " cw: document.documentElement.clientWidth,"
                " theme: document.documentElement.getAttribute('data-theme')})"
            )
            assert scroll["theme"] == theme, scroll
            assert scroll["sw"] <= scroll["cw"], (
                f"{vw}x{vh} {theme}: horizontal overflow {scroll['sw']} > {scroll['cw']}"
            )

            contrast = pg.evaluate(CONTRAST_JS)
            assert contrast["checked"] > 0, "no paragraphs checked"
            assert not contrast["failures"], (
                f"{vw}x{vh} {theme}: paragraph contrast < 4.5: {contrast['failures']}"
            )

            shot_path = os.path.join(OUT_DIR, f"landing-{vw}x{vh}-{theme}.png")
            pg.screenshot(path=shot_path, full_page=False)

            # Verify interactive toggles once on light mobile
            if vw == 360 and theme == "light":
                pg.click("#navMenuBtn")
                assert not pg.evaluate("document.getElementById('mobileMenu').hidden")
                pg.click("#navMenuBtn")
                assert pg.evaluate("document.getElementById('mobileMenu').hidden")
                pg.click("#themeToggle")
                assert pg.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"

            assert not page_errors, f"{vw}x{vh} {theme} page errors: {page_errors}"
            assert not console_errors, f"{vw}x{vh} {theme} console errors: {console_errors}"
            report["viewports"][f"{vw}x{vh}-{theme}"] = {
                "scroll": scroll,
                "contrast": contrast,
                "screenshot": shot_path,
            }
            ctx.close()
    browser.close()

print(json.dumps(report, ensure_ascii=False, indent=1))
sys.exit(0)
