"""Phase 127: mobile topbar & bottom bar geometry across 320-430px in EN and ES.

Verifies at 320, 360, 390, and 430px in both English and Spanish across all
8 views:
  * document.documentElement.scrollWidth == innerWidth
  * .topbar <= 64px, single row, .brand unclipped with visible logo, all
    controls inside viewport with >= 8px gaps, >= 44x44 touch area, no overlap
  * #sideNav full width, fixed at bottom, 6 visible items >= 44px tall, uniform
    width, icon >= 18px, labels visible (offsetWidth > 0, font-size >= 10px,
    no ellipsis/clip)
  * #sideNav.more-open shows the 3 extra items + 6 primary items inside viewport
    with unclipped labels
  * body padding-bottom in [navH + 4, navH + 24] (safe-area = 0), and last
    element of <main> is not occluded by #sideNav when scrolled to bottom.

Run with: uv run --with playwright python tests/test_bars.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
NAME = "bars-suite"
PASS = "bars-suite-pass-9"

WIDTHS = [(320, 568), (360, 740), (390, 844), (430, 932)]
VIEWS = ["hoy", "plan", "practice", "exam", "prog", "err", "resources", "ia"]
LANGS = ["en", "es"]


MEASURE_BARS_JS = r"""
() => {
  const doc = document.documentElement;
  const r = el => {
    const b = el.getBoundingClientRect();
    return {
      left: +b.left.toFixed(1),
      top: +b.top.toFixed(1),
      right: +b.right.toFixed(1),
      bottom: +b.bottom.toFixed(1),
      w: +b.width.toFixed(1),
      h: +b.height.toFixed(1),
    };
  };
  const textWidth = el => {
    const range = document.createRange();
    range.selectNodeContents(el);
    return +range.getBoundingClientRect().width.toFixed(1);
  };

  const tb = document.querySelector('.topbar');
  const brand = tb ? tb.querySelector('.brand') : null;
  const brandImg = brand ? brand.querySelector('img') : null;
  const brandSpan = brand ? brand.querySelector('span') : null;
  const actions = tb ? tb.querySelector('.top-actions') : null;
  const actionKids = actions
    ? [...actions.children].filter(el => getComputedStyle(el).display !== 'none')
    : [];

  const gaps = [];
  for (let i = 1; i < actionKids.length; i++) {
    const prev = actionKids[i - 1].getBoundingClientRect();
    const cur = actionKids[i].getBoundingClientRect();
    gaps.push(+(cur.left - prev.right).toFixed(1));
  }

  const topbarData = {
    rect: tb ? r(tb) : null,
    flexWrap: tb ? getComputedStyle(tb).flexWrap : null,
    brand: brand ? {
      ...r(brand),
      sw: brand.scrollWidth,
      cw: brand.clientWidth,
      imgW: brandImg ? brandImg.offsetWidth : 0,
      spanSw: brandSpan ? brandSpan.scrollWidth : 0,
      spanCw: brandSpan ? brandSpan.clientWidth : 0,
      spanTw: brandSpan ? textWidth(brandSpan) : 0,
    } : null,
    actionsRect: actions ? r(actions) : null,
    allControlsPresent: ['streakTopPill', 'syncBadge', 'settingsBtn', 'userChip', 'themeToggle']
      .every(id => !!document.getElementById(id)),
    visibleActionKids: actionKids.map(el => ({
      id: el.id || el.className,
      ...r(el),
    })),
    gaps,
    brandToActionsGap: (brand && actions)
      ? +(actions.getBoundingClientRect().left - brand.getBoundingClientRect().right).toFixed(1)
      : null,
  };

  const nav = document.getElementById('sideNav');
  const navRect = nav ? r(nav) : null;
  const navItems = nav
    ? [...nav.querySelectorAll('button[data-view], #navMoreBtn')].filter(
        el => getComputedStyle(el).display !== 'none'
      )
    : [];

  const itemsData = navItems.map(el => {
    const lab = el.querySelector('.nav-label');
    const ico = el.querySelector('.nav-ico');
    const lcs = lab ? getComputedStyle(lab) : null;
    const ecs = getComputedStyle(el);
    return {
      view: el.dataset.view || 'more',
      extra: el.classList.contains('extra'),
      ...r(el),
      overflow: ecs.overflow,
      icoW: ico ? +ico.getBoundingClientRect().width.toFixed(1) : 0,
      icoH: ico ? +ico.getBoundingClientRect().height.toFixed(1) : 0,
      labOffsetW: lab ? lab.offsetWidth : 0,
      labSw: lab ? lab.scrollWidth : 0,
      labCw: lab ? lab.clientWidth : 0,
      labTw: lab ? textWidth(lab) : 0,
      labFontSize: lcs ? parseFloat(lcs.fontSize) : 0,
      labLineHeight: lcs ? parseFloat(lcs.lineHeight) : 0,
      labLines: (lab && lcs && parseFloat(lcs.lineHeight) > 0)
        ? Math.round(lab.getBoundingClientRect().height / parseFloat(lcs.lineHeight))
        : 0,
    };
  });

  const padB = parseFloat(getComputedStyle(document.body).paddingBottom);

  return {
    vw: innerWidth,
    vh: innerHeight,
    scrollWidth: doc.scrollWidth,
    topbar: topbarData,
    nav: navRect,
    navPos: nav ? getComputedStyle(nav).position : null,
    navItems: itemsData,
    padB,
  };
}
"""


CHECK_OCCLUSION_JS = r"""
() => {
  window.scrollTo(0, document.documentElement.scrollHeight);
  const nav = document.getElementById('sideNav');
  const navTop = nav.getBoundingClientRect().top;
  const activeView = document.querySelector('.view.active') || document.querySelector('main');
  const candidates = [...activeView.querySelectorAll('.card, .panel, .empty, h1, h2, p, button, table')]
    .filter(el => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      const b = el.getBoundingClientRect();
      return b.width > 0.5 && b.height > 0.5;
    });
  let maxBottom = 0;
  for (const el of candidates) {
    const b = el.getBoundingClientRect();
    if (b.bottom > maxBottom) maxBottom = b.bottom;
  }
  return { maxBottom: +maxBottom.toFixed(1), navTop: +navTop.toFixed(1) };
}
"""


def assert_bars(m, tag, check_more=False):
    assert m["scrollWidth"] == m["vw"], (
        f"{tag}: horizontal scroll {m['scrollWidth']} != {m['vw']}"
    )

    tb = m["topbar"]
    assert tb["rect"]["h"] <= 64, f"{tag}: topbar height {tb['rect']['h']} > 64"
    assert tb["flexWrap"] == "nowrap", f"{tag}: topbar flexWrap={tb['flexWrap']}"
    assert tb["allControlsPresent"], f"{tag}: missing topbar controls"

    br = tb["brand"]
    assert br["imgW"] > 0, f"{tag}: brand logo width is 0"
    assert br["sw"] <= br["cw"] + 1, f"{tag}: brand truncated sw={br['sw']} cw={br['cw']}"
    assert br["spanSw"] <= br["spanCw"] + 1, (
        f"{tag}: brand text truncated sw={br['spanSw']} cw={br['spanCw']}"
    )
    assert br["spanTw"] <= br["cw"] + 1, (
        f"{tag}: brand text overflows brand tw={br['spanTw']} cw={br['cw']}"
    )
    assert br["left"] >= -0.5 and br["right"] <= m["vw"] + 0.5, (
        f"{tag}: brand outside viewport: {br}"
    )
    assert tb["brandToActionsGap"] >= 4, (
        f"{tag}: brand overlaps or touches top-actions: gap={tb['brandToActionsGap']}"
    )

    for g in tb["gaps"]:
        assert g >= 7.5, f"{tag}: gap between topbar controls {g} < 8px"

    box_heights = set()
    for kid in tb["visibleActionKids"]:
        assert kid["left"] >= -0.5 and kid["right"] <= m["vw"] + 0.5, (
            f"{tag}: topbar child {kid['id']} outside viewport: {kid}"
        )
        if kid["id"] != "syncBadge":
            assert kid["w"] >= 43.5 and kid["h"] >= 43.5, (
                f"{tag}: topbar control {kid['id']} smaller than 44x44: {kid['w']}x{kid['h']}"
            )
            box_heights.add(round(kid["h"]))
    assert len(box_heights) == 1, f"{tag}: topbar control heights differ: {box_heights}"

    nav = m["nav"]
    assert m["navPos"] == "fixed", f"{tag}: sideNav not fixed: {m['navPos']}"
    assert abs(nav["w"] - m["vw"]) <= 1, f"{tag}: sideNav width {nav['w']} != {m['vw']}"
    assert abs(nav["bottom"] - m["vh"]) <= 1, (
        f"{tag}: sideNav bottom {nav['bottom']} != {m['vh']}"
    )

    if not check_more:
        assert len(m["navItems"]) == 6, f"{tag}: expected 6 primary nav items, got {len(m['navItems'])}"
        widths = [it["w"] for it in m["navItems"]]
        assert max(widths) - min(widths) <= 2, f"{tag}: non-uniform nav item widths: {widths}"
        assert nav["h"] + 4 <= m["padB"] <= nav["h"] + 24, (
            f"{tag}: body padding-bottom {m['padB']} not in [{nav['h'] + 4}, {nav['h'] + 24}]"
        )
    else:
        assert len(m["navItems"]) == 9, f"{tag}: expected 9 nav items in more-open, got {len(m['navItems'])}"

    for it in m["navItems"]:
        assert it["left"] >= -0.5 and it["right"] <= m["vw"] + 0.5, (
            f"{tag}: nav item {it['view']} outside viewport: {it}"
        )
        assert it["h"] >= 43.5, f"{tag}: nav item {it['view']} height {it['h']} < 44"
        assert it["icoW"] >= 17.5 and it["icoH"] >= 17.5, (
            f"{tag}: nav item {it['view']} icon < 18px: {it['icoW']}x{it['icoH']}"
        )
        assert it["labOffsetW"] > 0, f"{tag}: nav item {it['view']} label hidden (offsetWidth=0)"
        assert it["labFontSize"] >= 10, (
            f"{tag}: nav item {it['view']} label fontSize {it['labFontSize']} < 10"
        )
        assert it["labLineHeight"] >= it["labFontSize"] * 1.1 - 0.1, (
            f"{tag}: nav item {it['view']} line-height too tight: {it['labLineHeight']}"
        )
        assert it["labSw"] <= it["labCw"] + 1, (
            f"{tag}: nav item {it['view']} label clipped sw={it['labSw']} cw={it['labCw']}"
        )
        assert it["labTw"] <= it["w"] + 1, (
            f"{tag}: nav item {it['view']} label text wider than item tw={it['labTw']} w={it['w']}"
        )
        if not it["extra"]:
            assert it["overflow"] != "hidden", (
                f"{tag}: nav item {it['view']} has overflow:hidden"
            )
            assert it["labLines"] <= 1, (
                f"{tag}: primary nav item {it['view']} wrapped to {it['labLines']} lines"
            )
        else:
            assert it["labLines"] <= 2, (
                f"{tag}: extra nav item {it['view']} wrapped to {it['labLines']} lines"
            )


def main():
    summary = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for w, h in WIDTHS:
            ctx = browser.new_context(
                viewport={"width": w, "height": h},
                is_mobile=True,
                has_touch=True,
                device_scale_factor=1,
            )
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(URL + "app", wait_until="networkidle")
            login_user(pg, URL, NAME, PASS)

            for lang in LANGS:
                pg.evaluate(f"setLang('{lang}')")
                pg.wait_for_timeout(150)

                for v in VIEWS:
                    pg.evaluate(f"showView('{v}'); window.scrollTo(0, 0);")
                    pg.wait_for_timeout(120)
                    m = pg.evaluate(MEASURE_BARS_JS)
                    tag = f"{lang} {w}px {v}"
                    assert_bars(m, tag, check_more=False)

                    occ = pg.evaluate(CHECK_OCCLUSION_JS)
                    assert occ["maxBottom"] <= occ["navTop"] + 1, (
                        f"{tag}: last content occluded by bottom nav: {occ}"
                    )
                    summary.append({
                        "lang": lang, "w": w, "view": v,
                        "tbH": m["topbar"]["rect"]["h"],
                        "brandW": m["topbar"]["brand"]["w"],
                        "navH": m["nav"]["h"],
                        "padB": m["padB"],
                    })

                # Also check More panel open on hoy
                pg.evaluate("showView('hoy'); document.getElementById('navMoreBtn').click();")
                pg.wait_for_timeout(120)
                m_more = pg.evaluate(MEASURE_BARS_JS)
                assert_bars(m_more, f"{lang} {w}px more-open", check_more=True)
                pg.evaluate("document.getElementById('navMoreBtn').click();")
                pg.wait_for_timeout(80)

                # Also check offline syncBadge (state-off) still fits cleanly at 320px
                if w == 320:
                    pg.evaluate("syncStatus('off')")
                    pg.wait_for_timeout(80)
                    m_off = pg.evaluate(MEASURE_BARS_JS)
                    assert_bars(m_off, f"{lang} 320px sync-off", check_more=False)
                    pg.evaluate("syncStatus('ok')")

            assert not errors, f"{w}px page errors: {errors}"
            ctx.close()
        browser.close()

    print(f"BARS_OK: {len(summary)} checks passed across {len(WIDTHS)} widths x {len(VIEWS)} views x {len(LANGS)} langs")
    print(json.dumps(summary[:8], indent=1))


if __name__ == "__main__":
    main()
