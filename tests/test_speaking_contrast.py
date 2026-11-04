"""Phase 57: the Speaking overlay stays readable in both themes.

The exam is a full-screen overlay with body copy, task text and buttons drawn
from the theme's OKLCH tokens. This suite reads the colours the browser really
resolved (not the CSS source), composites each element's background through its
ancestors (transparent surfaces included), and computes the WCAG contrast ratio
in plain JavaScript: no node modules, no colour library, no hard-coded palette
values.

Checked on every screen (choose, brief, exam, feedback, report), in light and
dark theme:

  1. The main copy — the panel's inherited text, the screen sentence, the task
     text, prompts, comments, tips and saved notices.
  2. Every visible button of the overlay, including the part cards and the
     full-exam card.
  3. The ratio must reach 4.5:1. A theme token that drifts below that fails
     here with the element, its resolved foreground, its composited background
     and the measured ratio.

The ratio maths is checked against two known anchors (black on white is 21:1,
a colour against itself is 1:1) so a parser that silently produced NaN or a
constant could not pass the rest.

Run:  uv run --with playwright python test_speaking_contrast.py
"""
import json
import math
import os
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
sys.path.insert(0, REPO)
sys.path.insert(0, TESTS)

os.environ.pop("B2_AI_KEY", None)

import helpers  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

URL = helpers.isolated_server() + "/"
THRESHOLD = 4.5
THEMES = ("light", "dark")
SCREENS = ("choose", "brief", "exam", "feedback", "report")

# Body copy the candidate actually reads. The panel itself is included because
# it carries the inherited text colour on the panel surface.
MAIN_TEXT = (
    "#spxPanel",
    ".spx-sentence",
    ".spx-brief li",
    ".spx-rule",
    ".spx-task h4",
    ".spx-task p",
    ".spx-prompts li",
    ".spx-decision",
    ".spx-part-comment",
    ".spx-tip p",
    ".spx-next p",
    ".spx-saved",
    ".spx-full .n",
    ".spx-part .n",
)

# Real content for every screen, rendered through the app's own functions so
# the colours are measured on the markup the candidate sees.
RENDER = {
    "choose": "spxRenderChoose()",
    "brief": "spxRenderBrief()",
    "exam": ("spxRenderTask(); spxRenderPartnerHeader();"
             "spxPhaseHeader(); spxRenderTurn()"),
    "feedback": "spxRenderFeedback()",
    "report": "spxRenderReportScreen()",
}

CONTRAST_JS = r"""
window.__spxContrast = (function () {
  const MAIN = %s;

  function parseColor(input) {
    const s = String(input || '').trim().toLowerCase();
    if (!s || s === 'transparent' || s === 'rgba(0, 0, 0, 0)') return [0, 0, 0, 0];
    let m = s.match(/^#([0-9a-f]{3,8})$/);
    if (m) {
      let h = m[1];
      if (h.length === 3 || h.length === 4) {
        h = h.split('').map(function (c) { return c + c; }).join('');
      }
      const n = function (i) { return parseInt(h.slice(i, i + 2), 16) / 255; };
      return [n(0), n(2), n(4), h.length >= 8 ? n(6) : 1];
    }
    m = s.match(/^rgba?\(([^)]+)\)$/);
    if (m) {
      const p = m[1].split(/[\s,\/]+/).filter(Boolean);
      const val = function (part, scale) {
        return part.indexOf('%%') >= 0
          ? parseFloat(part) / 100 * scale
          : parseFloat(part);
      };
      return [val(p[0], 255) / 255, val(p[1], 255) / 255,
              val(p[2], 255) / 255,
              p[3] === undefined ? 1 : val(p[3], 1)];
    }
    m = s.match(/^color\(srgb\s+([^)]+)\)$/);
    if (m) {
      const p = m[1].split(/[\s\/]+/).filter(Boolean);
      return [parseFloat(p[0]), parseFloat(p[1]), parseFloat(p[2]),
              p[3] === undefined ? 1 : parseFloat(p[3])];
    }
    m = s.match(/^oklch\(\s*([^)]+)\)$/);
    if (m) {
      const p = m[1].split(/[\s\/]+/).filter(Boolean);
      const L = p[0].indexOf('%%') >= 0 ? parseFloat(p[0]) / 100 : parseFloat(p[0]);
      const C = p[1].indexOf('%%') >= 0 ? parseFloat(p[1]) / 100 * 0.4 : parseFloat(p[1]);
      return fromLinear(oklchToLinear(L, C, parseFloat(p[2])), p[3]);
    }
    m = s.match(/^oklab\(\s*([^)]+)\)$/);
    if (m) {
      const p = m[1].split(/[\s\/]+/).filter(Boolean);
      const L = p[0].indexOf('%%') >= 0 ? parseFloat(p[0]) / 100 : parseFloat(p[0]);
      return fromLinear(oklabToLinear(L, parseFloat(p[1]), parseFloat(p[2])), p[3]);
    }
    throw new Error('unsupported CSS colour: ' + input);
  }

  function oklchToLinear(L, C, hDeg) {
    const h = hDeg * Math.PI / 180;
    return oklabToLinear(L, C * Math.cos(h), C * Math.sin(h));
  }

  /* CSS Color 4: OKLab -> LMS -> linear sRGB. */
  function oklabToLinear(L, a, b) {
    const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
    const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
    const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
    const l = l_ * l_ * l_, m = m_ * m_ * m_, s = s_ * s_ * s_;
    return [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    ];
  }

  function encode(x) {
    x = Math.max(0, Math.min(1, x));
    return x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055;
  }

  function fromLinear(lin, alpha) {
    return [encode(lin[0]), encode(lin[1]), encode(lin[2]),
            alpha === undefined ? 1 : (String(alpha).indexOf('%%') >= 0
              ? parseFloat(alpha) / 100 : parseFloat(alpha))];
  }

  function over(top, bottom) {
    const a = top[3];
    if (a >= 1) return [top[0], top[1], top[2], 1];
    return [top[0] * a + bottom[0] * (1 - a),
            top[1] * a + bottom[1] * (1 - a),
            top[2] * a + bottom[2] * (1 - a), 1];
  }

  /* Paint the ancestor chain from the canvas up, so a transparent surface
     shows the one behind it instead of being treated as white. */
  function backgroundOf(el) {
    const chain = [];
    for (let n = el; n; n = n.parentElement) chain.push(n);
    let bg = [1, 1, 1, 1];
    for (let i = chain.length - 1; i >= 0; i--) {
      bg = over(parseColor(getComputedStyle(chain[i]).backgroundColor), bg);
    }
    return bg;
  }

  function toLinear(c) {
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }

  function luminance(rgb) {
    return 0.2126 * toLinear(rgb[0]) + 0.7152 * toLinear(rgb[1]) +
           0.0722 * toLinear(rgb[2]);
  }

  function ratio(fg, bg) {
    const a = luminance(fg), b = luminance(bg);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  }

  function visible(el) {
    if (!el.isConnected || !el.getClientRects().length) return false;
    const cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  }

  function css(rgb) {
    return 'rgb(' + rgb.slice(0, 3).map(function (c) {
      return Math.round(c * 255);
    }).join(', ') + ')';
  }

  function sample(el, kind) {
    const fg = parseColor(getComputedStyle(el).color);
    const bg = backgroundOf(el);
    return {
      kind: kind,
      id: el.id || '',
      cls: String(el.getAttribute('class') || ''),
      text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60),
      fg: css(over(fg, bg)),
      bg: css(bg),
      ratio: ratio(over(fg, bg), bg)
    };
  }

  return {
    /* Two anchors the WCAG formula must reproduce. */
    anchors: function () {
      return {
        blackOnWhite: ratio([0, 0, 0, 1], [1, 1, 1, 1]),
        whiteOnWhite: ratio([1, 1, 1, 1], [1, 1, 1, 1])
      };
    },
    measure: function () {
      const out = [];
      const seen = new Set();
      function add(el, kind) {
        if (!el || seen.has(el) || !visible(el)) return;
        if (!(el.textContent || '').trim()) return;
        seen.add(el);
        out.push(sample(el, kind));
      }
      MAIN.forEach(function (sel) {
        document.querySelectorAll('#spxOverlay ' + sel).forEach(function (el) {
          add(el, 'text');
        });
      });
      document.querySelectorAll('#spxOverlay button').forEach(function (el) {
        add(el, 'button');
      });
      return out;
    }
  };
})();
""" % json.dumps(list(MAIN_TEXT))


def labels(sample):
    if sample["id"]:
        return "#" + sample["id"]
    return (sample["cls"].split(" ")[0] or sample["kind"])


def fail(samples):
    return [s for s in samples
            if not (isinstance(s["ratio"], (int, float)) and
                    math.isfinite(s["ratio"]) and s["ratio"] >= THRESHOLD)]


def check(samples, where, out):
    bad = fail(samples)
    assert not bad, "%s is below %.1f:1: %s" % (where, THRESHOLD,
                                                json.dumps(bad, indent=1))
    out[where] = {
        "samples": len(samples),
        "min": min(s["ratio"] for s in samples),
        "lowest": labels(min(samples, key=lambda s: s["ratio"]))
        if samples else None,
    }


def main():
    out = {"threshold": THRESHOLD, "themes": {}, "anchors": None}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        page.goto(URL + "app?spx_test=1", wait_until="networkidle")
        helpers.login_owner(page, URL)
        page.evaluate("localStorage.setItem('spx_test','1')")
        page.goto(URL + "app?spx_test=1", wait_until="networkidle")
        page.wait_for_timeout(400)
        helpers.dismiss_onboarding(page)
        page.evaluate("setLang('en')")
        assert page.evaluate("!!window.SPX_TEST"), "SPX_TEST was not exposed"

        page.evaluate(CONTRAST_JS)
        anchors = page.evaluate("window.__spxContrast.anchors()")
        assert abs(anchors["blackOnWhite"] - 21) < 0.05, anchors
        assert abs(anchors["whiteOnWhite"] - 1) < 0.001, anchors
        out["anchors"] = anchors

        page.evaluate("async () => { await SP_EXAM.open(); }")
        assert page.evaluate("SP_EXAM.screen") == "choose"

        # A real Part 2 task so the exam screen carries the task panel and the
        # two photographs, not an empty shell.
        page.evaluate("""() => {
            const bank = SP_EXAM.bank;
            const task = spxTaskById(bank, 2, spxPool(bank, 2)[0]) ||
                         spxDefaultTask(2);
            SP_EXAM.part = 2;
            SP_EXAM.full = false;
            SP_EXAM.task = task;
            SP_EXAM.phases = spxPhasesFor(2, task, 7);
        }""")

        for theme in THEMES:
            page.evaluate("(t) => applyTheme(t)", theme)
            assert page.evaluate("currentTheme()") == theme
            # The theme swap animates background-colour; measure the settled
            # palette, not a frame halfway between the two.
            page.wait_for_timeout(500)
            out["themes"][theme] = {}
            for screen in SCREENS:
                page.evaluate("(s) => spxSetScreen(s)", screen)
                page.evaluate("() => { %s; }" % RENDER[screen])
                page.wait_for_timeout(80)
                assert page.evaluate("SP_EXAM.screen") == screen
                samples = page.evaluate("window.__spxContrast.measure()")
                assert samples, (theme, screen)
                kinds = {s["kind"] for s in samples}
                assert kinds == {"text", "button"}, (theme, screen, kinds)
                check(samples, "%s/%s" % (theme, screen), out["themes"][theme])

        page.evaluate("SP_EXAM.close()")
        assert errors == [], errors
        browser.close()

    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
