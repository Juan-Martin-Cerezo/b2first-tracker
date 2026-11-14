"""Phase 129: 3-zone minimalist topbar, Account sheet/popover, 3 layout tiers (phone/tablet/desktop) & bottom bar across EN and ES.

Verifies at 320, 360, 390, 430, 768, 1024, and 1440px across all 8 views:
  * document.documentElement.scrollWidth == innerWidth (0 overflow)
  * .topbar exact 48px (<=767) / 56px (>=768), constant height on scroll, no box-shadow,
    border-bottom 1px, strictly 3 controls (brand, streak, avatar), unclipped
  * Brand: 24px logo only at <=767 with aria-label, logo + wordmark at >=768
  * Streak: 12px tabular-nums text + 12px flame SVG, transparent bg, >=4.5:1 contrast light/dark
  * #userChip >= 44x44 opens #accountSheet (bottom sheet <=767, popover >=768),
    focus trap, Escape/backdrop close, theme (light/dark/system), EN/ES switch, settings
  * Phone (<=599) & Tablet (600-1023): 5-tab fixed bottom bar, #moreSheet, sticky view bar & FAB
  * Tablet (768): Today, Progress, Plan 2 independent columns (width > 300)
  * Desktop (>=1024): inline #sideNav in topbar, main max-width <= 1240 centered at 1440px

Run with: uv run --with playwright python tests/test_bars.py
"""
import json

from playwright.sync_api import sync_playwright

from helpers import isolated_server, login_user

URL = isolated_server() + "/"
NAME = "bars-suite"
PASS = "bars-suite-pass-9"

WIDTHS = [
    (320, 568),
    (360, 740),
    (390, 844),
    (430, 932),
    (768, 1024),
    (1024, 900),
    (1440, 900),
]
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
  const _c = document.createElement('canvas');
  _c.width = 1; _c.height = 1;
  const _cx = _c.getContext('2d', {willReadFrequently: true});
  const parseRgb = s => {
    if (!s || s === 'transparent') return null;
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (m) {
      const p = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
      if (p.length >= 3) return [p[0], p[1], p[2], p.length >= 4 ? p[3] : 1];
    }
    _cx.clearRect(0, 0, 1, 1);
    _cx.fillStyle = s;
    _cx.fillRect(0, 0, 1, 1);
    const d = _cx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  const relLum = rgb => {
    const lin = c => {
      c /= 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
  };
  const contrastRatio = (fgStr, bgStr) => {
    const fg = parseRgb(fgStr), bg = parseRgb(bgStr);
    if (!fg || !bg) return null;
    const l1 = relLum(fg), l2 = relLum(bg);
    return +((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)).toFixed(2);
  };
  const resolveBg = el => {
    let cur = el;
    while (cur && cur !== document.documentElement) {
      const bg = getComputedStyle(cur).backgroundColor;
      const p = parseRgb(bg);
      if (p && p[3] > 0.2) return bg;
      cur = cur.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor || 'rgb(255, 255, 255)';
  };

  const chrome = document.getElementById('topChrome');
  const tb = document.querySelector('.topbar');
  const brand = tb ? tb.querySelector('.brand') : null;
  const brandImg = brand ? brand.querySelector('img') : null;
  const brandSpan = brand ? brand.querySelector('span') : null;
  const brandSpanVisible = !!brandSpan && getComputedStyle(brandSpan).display !== 'none';
  const streakPill = document.getElementById('streakTopPill');
  const streakNum = document.getElementById('streakTopNum');
  const streakSvg = streakPill ? streakPill.querySelector('svg') : null;
  const userChip = document.getElementById('userChip');
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

  const tbContainer = innerWidth >= 1024 ? chrome : tb;
  const tbContainerCs = tbContainer ? getComputedStyle(tbContainer) : null;
  const tbCs = tb ? getComputedStyle(tb) : null;
  const streakCs = streakNum ? getComputedStyle(streakNum) : null;
  const streakPillCs = streakPill ? getComputedStyle(streakPill) : null;

  const topbarData = {
    rect: tb ? r(tb) : null,
    chromeRect: chrome ? r(chrome) : null,
    flexWrap: tbCs ? tbCs.flexWrap : null,
    boxShadow: tbContainerCs ? tbContainerCs.boxShadow : null,
    borderBottomWidth: tbContainerCs ? parseFloat(tbContainerCs.borderBottomWidth) : 0,
    legacyRemoved: !document.getElementById('settingsBtn') && !document.getElementById('themeToggle'),
    brand: brand ? {
      ...r(brand),
      ariaLabel: brand.getAttribute('aria-label') || '',
      sw: brand.scrollWidth,
      cw: brand.clientWidth,
      imgW: brandImg ? brandImg.offsetWidth : 0,
      imgH: brandImg ? brandImg.offsetHeight : 0,
      spanVisible: brandSpanVisible,
      spanSw: brandSpanVisible ? brandSpan.scrollWidth : 0,
      spanCw: brandSpanVisible ? brandSpan.clientWidth : 0,
      spanTw: brandSpanVisible ? textWidth(brandSpan) : 0,
    } : null,
    streak: streakPill ? {
      ...r(streakPill),
      bg: streakPillCs ? streakPillCs.backgroundColor : null,
      fontSize: streakCs ? parseFloat(streakCs.fontSize) : 0,
      fontVariantNumeric: streakCs ? streakCs.fontVariantNumeric : null,
      svgW: streakSvg ? +streakSvg.getBoundingClientRect().width.toFixed(1) : 0,
      svgH: streakSvg ? +streakSvg.getBoundingClientRect().height.toFixed(1) : 0,
      hasEmoji: /\p{Extended_Pictographic}/u.test(streakPill.textContent || ''),
      contrast: streakNum ? contrastRatio(streakCs.color, resolveBg(tbContainer || tb)) : null,
    } : null,
    chip: userChip ? {
      ...r(userChip),
      tag: userChip.tagName,
      ariaExpanded: userChip.getAttribute('aria-expanded'),
    } : null,
    actionsRect: actions ? r(actions) : null,
    allControlsPresent: ['topbarBrand', 'streakTopPill', 'userChip']
      .every(id => !!document.getElementById(id)),
    visibleControlCount: (brand && getComputedStyle(brand).display !== 'none' ? 1 : 0) + actionKids.length,
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
  const mainEl = document.querySelector('main');
  const mainRect = mainEl ? r(mainEl) : null;

  const sheet = document.getElementById('moreSheet');
  const moreBtn = document.getElementById('navMoreBtn');
  const closeBtn = document.getElementById('moreSheetClose');
  const sheetOpen = !!sheet && getComputedStyle(sheet).display !== 'none';
  const sheetItems = sheetOpen
    ? [...sheet.querySelectorAll('.more-sheet-item[data-view]')].map(el => {
        const lab = el.querySelector('.more-sheet-label');
        const desc = el.querySelector('.more-sheet-desc');
        const ico = el.querySelector('.nav-ico');
        return {
          view: el.dataset.view,
          ...r(el),
          icoW: ico ? +ico.getBoundingClientRect().width.toFixed(1) : 0,
          icoH: ico ? +ico.getBoundingClientRect().height.toFixed(1) : 0,
          labText: lab ? lab.textContent.trim() : '',
          labOffsetW: lab ? lab.offsetWidth : 0,
          labSw: lab ? lab.scrollWidth : 0,
          labCw: lab ? lab.clientWidth : 0,
          descText: desc ? desc.textContent.trim() : '',
          descOffsetW: desc ? desc.offsetWidth : 0,
        };
      })
    : [];
  const sheetData = {
    open: sheetOpen,
    role: sheet ? sheet.getAttribute('role') : null,
    ariaModal: sheet ? sheet.getAttribute('aria-modal') : null,
    moreExpanded: moreBtn ? moreBtn.getAttribute('aria-expanded') : null,
    bodyOverflow: getComputedStyle(document.body).overflow,
    htmlOverflow: getComputedStyle(document.documentElement).overflow,
    closeRect: (sheetOpen && closeBtn) ? r(closeBtn) : null,
    panelRect: (sheetOpen && sheet.querySelector('.more-sheet-panel'))
      ? r(sheet.querySelector('.more-sheet-panel'))
      : null,
    items: sheetItems,
  };

  return {
    vw: innerWidth,
    vh: innerHeight,
    scrollWidth: doc.scrollWidth,
    mainRect,
    topbar: topbarData,
    nav: navRect,
    navPos: nav ? getComputedStyle(nav).position : null,
    navItems: itemsData,
    padB,
    sheet: sheetData,
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
    expected_h = 48 if m["vw"] <= 767 else 56
    assert abs(tb["rect"]["h"] - expected_h) <= 0.5, (
        f"{tag}: topbar height {tb['rect']['h']} != {expected_h}"
    )
    assert tb["flexWrap"] == "nowrap", f"{tag}: topbar flexWrap={tb['flexWrap']}"
    assert tb["boxShadow"] == "none", f"{tag}: topbar has box-shadow={tb['boxShadow']}"
    assert abs(tb["borderBottomWidth"] - 1.0) <= 0.2, (
        f"{tag}: topbar border-bottom={tb['borderBottomWidth']}"
    )
    assert tb["legacyRemoved"], f"{tag}: legacy settingsBtn or themeToggle still in DOM"
    assert tb["allControlsPresent"], f"{tag}: missing topbar controls"
    assert tb["visibleControlCount"] == 3, (
        f"{tag}: expected 3 visible topbar controls, got {tb['visibleControlCount']}"
    )

    br = tb["brand"]
    assert abs(br["imgW"] - 24) <= 1 and abs(br["imgH"] - 24) <= 1, (
        f"{tag}: brand logo expected ~24x24, got {br['imgW']}x{br['imgH']}"
    )
    assert br["ariaLabel"].startswith("B2 First Tracker · "), (
        f"{tag}: brand aria-label missing view name: {br['ariaLabel']!r}"
    )
    if m["vw"] <= 767:
        assert not br["spanVisible"], f"{tag}: wordmark should be hidden at <=767px"
    else:
        assert br["spanVisible"], f"{tag}: wordmark should be visible at >=768px"
        assert br["spanSw"] <= br["spanCw"] + 1, (
            f"{tag}: brand text truncated sw={br['spanSw']} cw={br['spanCw']}"
        )
        assert br["spanTw"] <= br["cw"] + 1, (
            f"{tag}: brand text overflows brand tw={br['spanTw']} cw={br['cw']}"
        )
    assert br["sw"] <= br["cw"] + 1, f"{tag}: brand truncated sw={br['sw']} cw={br['cw']}"
    assert br["left"] >= -0.5 and br["right"] <= m["vw"] + 0.5, (
        f"{tag}: brand outside viewport: {br}"
    )
    assert tb["brandToActionsGap"] >= 4, (
        f"{tag}: brand overlaps or touches top-actions: gap={tb['brandToActionsGap']}"
    )

    st = tb["streak"]
    assert st["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), (
        f"{tag}: streak pill should have no background, got {st['bg']}"
    )
    assert not st["hasEmoji"], f"{tag}: streak pill still contains emoji"
    assert abs(st["fontSize"] - 12.0) <= 0.5, f"{tag}: streak fontSize={st['fontSize']}"
    assert "tabular-nums" in (st["fontVariantNumeric"] or ""), (
        f"{tag}: streak fontVariantNumeric={st['fontVariantNumeric']}"
    )
    assert abs(st["svgW"] - 12.0) <= 0.5 and abs(st["svgH"] - 12.0) <= 0.5, (
        f"{tag}: streak flame SVG {st['svgW']}x{st['svgH']} != 12x12"
    )
    assert st["contrast"] is not None and st["contrast"] >= 4.5, (
        f"{tag}: streak contrast {st['contrast']} < 4.5"
    )

    ch = tb["chip"]
    assert ch["tag"] == "BUTTON", f"{tag}: userChip should be <button>, got {ch['tag']}"
    assert ch["w"] >= 43.5 and ch["h"] >= 43.5, (
        f"{tag}: userChip touch target {ch['w']}x{ch['h']} < 44x44"
    )

    for g in tb["gaps"]:
        assert g >= 7.5, f"{tag}: gap between topbar controls {g} < 8px"
    for kid in tb["visibleActionKids"]:
        assert kid["left"] >= -0.5 and kid["right"] <= m["vw"] + 0.5, (
            f"{tag}: topbar child {kid['id']} outside viewport: {kid}"
        )

    nav = m["nav"]
    if m["vw"] <= 1023:
        assert m["navPos"] == "fixed", f"{tag}: sideNav not fixed: {m['navPos']}"
        assert abs(nav["w"] - m["vw"]) <= 1, f"{tag}: sideNav width {nav['w']} != {m['vw']}"
        assert abs(nav["bottom"] - m["vh"]) <= 1, (
            f"{tag}: sideNav bottom {nav['bottom']} != {m['vh']}"
        )

        assert len(m["navItems"]) == 5, f"{tag}: expected 5 primary nav items, got {len(m['navItems'])}"
        expected_order = ["hoy", "exam", "practice", "prog", "more"]
        actual_order = [it["view"] for it in sorted(m["navItems"], key=lambda x: x["left"])]
        assert actual_order == expected_order, f"{tag}: unexpected nav order {actual_order}"
        widths = [it["w"] for it in m["navItems"]]
        assert max(widths) - min(widths) <= 2, f"{tag}: non-uniform nav item widths: {widths}"
        assert nav["h"] + 4 <= m["padB"] <= nav["h"] + 24, (
            f"{tag}: body padding-bottom {m['padB']} not in [{nav['h'] + 4}, {nav['h'] + 24}]"
        )

        sh = m["sheet"]
        if not check_more:
            assert not sh["open"], f"{tag}: More sheet unexpectedly open"
            assert sh["moreExpanded"] == "false", f"{tag}: aria-expanded={sh['moreExpanded']} when closed"
        else:
            assert sh["open"], f"{tag}: More sheet did not open"
            assert sh["role"] == "dialog" and sh["ariaModal"] == "true", f"{tag}: bad dialog attrs {sh}"
            assert sh["moreExpanded"] == "true", f"{tag}: aria-expanded={sh['moreExpanded']} when open"
            assert sh["bodyOverflow"] == "hidden" or sh["htmlOverflow"] == "hidden", (
                f"{tag}: body scroll not locked while sheet open: body={sh['bodyOverflow']} html={sh['htmlOverflow']}"
            )
            assert sh["closeRect"]["w"] >= 43.5 and sh["closeRect"]["h"] >= 43.5, (
                f"{tag}: More sheet close btn < 44x44: {sh['closeRect']}"
            )
            assert sh["panelRect"]["bottom"] <= m["vh"] + 1 and sh["panelRect"]["top"] >= 0, (
                f"{tag}: More sheet panel outside viewport: {sh['panelRect']}"
            )
            assert len(sh["items"]) == 4, f"{tag}: expected 4 More destinations, got {len(sh['items'])}"
            assert [it["view"] for it in sh["items"]] == ["plan", "resources", "err", "ia"], (
                f"{tag}: unexpected More destinations {[it['view'] for it in sh['items']]}"
            )
            row_tops = sorted({round(it["top"]) for it in sh["items"]})
            assert len(row_tops) == 2, f"{tag}: expected 2-column x 2-row grid, got row tops {row_tops}"
            for it in sh["items"]:
                assert it["left"] >= -0.5 and it["right"] <= m["vw"] + 0.5, (
                    f"{tag}: More item {it['view']} outside viewport: {it}"
                )
                assert it["h"] >= 44, f"{tag}: More item {it['view']} height {it['h']} < 44"
                assert it["icoW"] >= 17.5 and it["icoH"] >= 17.5, (
                    f"{tag}: More item {it['view']} icon < 18px"
                )
                assert it["labOffsetW"] > 0 and len(it["labText"]) > 0, (
                    f"{tag}: More item {it['view']} empty/hidden label"
                )
                assert it["labSw"] <= it["labCw"] + 1, (
                    f"{tag}: More item {it['view']} label clipped sw={it['labSw']} cw={it['labCw']}"
                )
                assert it["descOffsetW"] > 0 and len(it["descText"]) > 0, (
                    f"{tag}: More item {it['view']} missing description"
                )

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
    else:
        assert m["navPos"] != "fixed", f"{tag}: desktop sideNav should be inline, got {m['navPos']}"
        assert len(m["navItems"]) == 8, f"{tag}: desktop expected 8 nav items, got {len(m['navItems'])}"
        assert nav["bottom"] <= tb["chromeRect"]["bottom"] + 1, (
            f"{tag}: desktop nav spills below topbar chrome: nav={nav} chrome={tb['chromeRect']}"
        )
        assert nav["left"] >= br["right"] - 0.5 and nav["right"] <= tb["actionsRect"]["left"] + 0.5, (
            f"{tag}: desktop nav overlaps brand/actions: nav={nav} brand={br} actions={tb['actionsRect']}"
        )
        for it in m["navItems"]:
            assert it["h"] >= 43.5, f"{tag}: desktop nav item {it['view']} height {it['h']} < 44"
            assert it["labOffsetW"] > 0 and it["labSw"] <= it["labCw"] + 1, (
                f"{tag}: desktop nav item {it['view']} label clipped"
            )
        mr = m["mainRect"]
        assert mr["w"] <= 1240.5, f"{tag}: desktop main width {mr['w']} > 1240"
        if m["vw"] >= 1440:
            left_margin = mr["left"]
            right_margin = m["vw"] - mr["right"]
            assert abs(left_margin - right_margin) <= 2.0, (
                f"{tag}: desktop main not centered: left={left_margin} right={right_margin}"
            )


def check_account_sheet(pg, w, vh, lang):
    tag = f"{lang} {w}px accountSheet"
    pg.evaluate("showView('hoy'); window.scrollTo(0, 0);")
    pg.click("#userChip")
    pg.wait_for_selector("#accountSheet.is-open")
    pg.wait_for_timeout(120)

    data = pg.evaluate("""() => {
      const sheet = document.getElementById('accountSheet');
      const panel = sheet.querySelector('.acct-sheet-panel');
      const handle = sheet.querySelector('.acct-sheet-handle');
      const chip = document.getElementById('userChip');
      const r = el => {
        const b = el.getBoundingClientRect();
        return {left: +b.left.toFixed(1), top: +b.top.toFixed(1), right: +b.right.toFixed(1), bottom: +b.bottom.toFixed(1), w: +b.width.toFixed(1), h: +b.height.toFixed(1)};
      };
      const btns = [...sheet.querySelectorAll('button')].filter(b => getComputedStyle(b).display !== 'none').map(b => ({
        id: b.id,
        text: b.textContent.trim(),
        aria: b.getAttribute('aria-label') || '',
        ...r(b),
      }));
      return {
        role: sheet.getAttribute('role'),
        ariaModal: sheet.getAttribute('aria-modal'),
        expanded: chip.getAttribute('aria-expanded'),
        bodyOverflow: getComputedStyle(document.body).overflow,
        htmlOverflow: getComputedStyle(document.documentElement).overflow,
        panelRect: r(panel),
        handleVisible: handle ? getComputedStyle(handle).display !== 'none' : false,
        titleText: (document.getElementById('acctSheetTitle')?.textContent || '').trim(),
        syncText: (document.getElementById('acctSyncText')?.textContent || '').trim(),
        btns,
      };
    }""")

    assert data["role"] == "dialog" and data["ariaModal"] == "true", f"{tag}: bad dialog attrs {data}"
    assert data["expanded"] == "true", f"{tag}: chip aria-expanded={data['expanded']}"
    assert data["bodyOverflow"] == "hidden" or data["htmlOverflow"] == "hidden", (
        f"{tag}: body scroll not locked: {data}"
    )
    assert data["titleText"] and data["syncText"], f"{tag}: missing name/sync text: {data}"
    pr = data["panelRect"]
    assert pr["left"] >= -0.5 and pr["right"] <= w + 0.5 and pr["top"] >= 0 and pr["bottom"] <= vh + 1, (
        f"{tag}: panel outside viewport: {pr}"
    )
    if w <= 767:
        assert data["handleVisible"], f"{tag}: sheet handle missing at <=767"
        assert abs(pr["bottom"] - vh) <= 2, f"{tag}: bottom sheet not anchored to bottom: {pr} vh={vh}"
    else:
        assert not data["handleVisible"], f"{tag}: popover should hide drag handle at >=768"
        assert pr["top"] <= 80 and pr["right"] >= w - 40, f"{tag}: popover not near top-right: {pr}"

    for b in data["btns"]:
        assert b["w"] >= 43.5 and b["h"] >= 43.5, f"{tag}: btn {b['id']} < 44px: {b}"
        assert b["text"] or b["aria"], f"{tag}: btn {b['id']} missing visible/aria label"

    # Focus trap inside #accountSheet
    assert pg.evaluate("document.getElementById('accountSheet').contains(document.activeElement)"), (
        f"{tag}: focus not inside #accountSheet"
    )
    for _ in range(9):
        pg.keyboard.press("Tab")
    assert pg.evaluate("document.getElementById('accountSheet').contains(document.activeElement)"), (
        f"{tag}: Tab escaped #accountSheet focus trap"
    )

    # Theme switch: dark -> verify dark + streak contrast -> light
    pg.click("#acctThemeDark")
    pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'dark'")
    dark_tb = pg.evaluate(MEASURE_BARS_JS)["topbar"]
    assert dark_tb["streak"]["contrast"] >= 4.5, (
        f"{tag}: dark mode streak contrast {dark_tb['streak']['contrast']} < 4.5"
    )
    pg.click("#acctThemeSystem")
    assert pg.evaluate("localStorage.getItem('b2first_theme')") == "system"
    pg.click("#acctThemeLight")
    pg.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'")

    # Language switch inside Account sheet: -> other -> back
    other = "es" if lang == "en" else "en"
    pg.click(f"#acctLang{other.capitalize()}")
    pg.wait_for_function(f"document.documentElement.lang === '{other}'")
    pg.click(f"#acctLang{lang.capitalize()}")
    pg.wait_for_function(f"document.documentElement.lang === '{lang}'")

    # Escape closes and restores focus
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(80)
    assert pg.evaluate("document.getElementById('accountSheet').style.display") == "none", (
        f"{tag}: Escape did not close #accountSheet"
    )
    assert pg.evaluate("document.getElementById('userChip').getAttribute('aria-expanded')") == "false"

    # Backdrop click closes
    pg.click("#userChip")
    pg.wait_for_selector("#accountSheet.is-open")
    pg.evaluate("document.getElementById('accountSheet').dispatchEvent(new MouseEvent('click', {bubbles:true}))")
    pg.wait_for_timeout(80)
    assert pg.evaluate("document.getElementById('accountSheet').style.display") == "none", (
        f"{tag}: backdrop click did not close #accountSheet"
    )

    # Settings action opens #settingsModal cleanly
    pg.click("#userChip")
    pg.wait_for_selector("#accountSheet.is-open")
    pg.click("#acctSettingsBtn")
    pg.wait_for_timeout(120)
    assert pg.evaluate("getComputedStyle(document.getElementById('settingsModal')).display") != "none", (
        f"{tag}: #acctSettingsBtn did not open #settingsModal"
    )
    pg.keyboard.press("Escape")
    pg.evaluate("closeSettingsModal()")
    pg.wait_for_timeout(80)


def check_tier_columns(pg, w):
    if w >= 768:
        # Ensure today has a scheduled slot and at least 1 log entry so both
        # Today (session + aside) and Progress charts render their 2-col layout.
        pg.evaluate("""() => {
          const wd = new Date().getDay();
          const nextWd = (wd + 4) % 7;
          D.profile = {
            examDate: null, targetGrade: 'B',
            skills: {rue: 3, w: 3, l: 3, sp: 3},
            hoursWeek: 4, days: [wd, nextWd],
            struggles: [], strugglesDeclared: [],
          };
          D.settings = D.settings || {};
          D.settings.rotationMode = 'by-part';
          D.settings.itemsPerSession = 1;
          D.settings.schedule = [{day: wd, time: '15:30'}, {day: nextWd, time: '13:00'}];
          D.settings.sessions = D.settings.schedule.slice();
          D.log = D.log || [];
          if (!D.log.length) {
            D.log.push({ id: 'tier-test', date: new Date().toISOString().slice(0, 10), created_at: Date.now(), type: 'ue', part: 1, ok: 6, total: 8, min: 10 });
          }
          const sorted = getSessionDays();
          const todayKey = PLAN_DAY_ORDER[(wd + 6) % 7];
          const todayIdx = sorted.findIndex(d => d.key === todayKey);
          D.sessionOffset = todayIdx > 0 ? -todayIdx : 0;
          refreshAll();
        }""")
        pg.evaluate("showView('hoy'); window.scrollTo(0, 0);")
        pg.wait_for_timeout(100)
        today = pg.evaluate("""() => {
          const s = document.getElementById('todaySession').getBoundingClientRect();
          const a = document.getElementById('todayAside').getBoundingClientRect();
          return {
            sTop: +s.top.toFixed(1), sW: +s.width.toFixed(1),
            aTop: +a.top.toFixed(1), aW: +a.width.toFixed(1),
          };
        }""")
        assert abs(today["sTop"] - today["aTop"]) <= 2.0, (
            f"{w}px Today not 2 columns side-by-side: {today}"
        )
        assert today["sW"] > 300 and today["aW"] > 300, (
            f"{w}px Today column too narrow (<=300): {today}"
        )

        pg.evaluate("showView('plan'); window.scrollTo(0, 0);")
        pg.wait_for_timeout(100)
        plan = pg.evaluate("""() => {
          const l = document.querySelector('#v-plan .plan-col-left').getBoundingClientRect();
          const r = document.querySelector('#v-plan .plan-col-right').getBoundingClientRect();
          return {lTop: +l.top.toFixed(1), lW: +l.width.toFixed(1), rTop: +r.top.toFixed(1), rW: +r.width.toFixed(1)};
        }""")
        assert abs(plan["lTop"] - plan["rTop"]) <= 2.0 and plan["lW"] > 300 and plan["rW"] > 300, (
            f"{w}px Plan not 2 columns: {plan}"
        )

        pg.evaluate("showView('prog'); window.scrollTo(0, 0);")
        pg.wait_for_timeout(100)
        prog = pg.evaluate("""() => {
          const g = document.getElementById('progChartsGrid');
          const cols = [...g.querySelectorAll(':scope > .col-6')].map(c => {
            const b = c.getBoundingClientRect();
            return {top: +b.top.toFixed(1), w: +b.width.toFixed(1)};
          });
          return {display: getComputedStyle(g).display, cols};
        }""")
        assert prog["display"] != "none" and len(prog["cols"]) == 2, (
            f"{w}px Progress charts missing/wrong cols: {prog}"
        )
        assert abs(prog["cols"][0]["top"] - prog["cols"][1]["top"]) <= 2.0, (
            f"{w}px Progress charts not 2 columns side-by-side: {prog}"
        )
        assert prog["cols"][0]["w"] > 300 and prog["cols"][1]["w"] > 300, (
            f"{w}px Progress column <= 300: {prog}"
        )


def main():
    summary = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for w, h in WIDTHS:
            is_touch = w <= 1023
            ctx = browser.new_context(
                viewport={"width": w, "height": h},
                is_mobile=is_touch,
                has_touch=is_touch,
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

                    if w <= 1023:
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

                if w in (320, 390, 768, 1024, 1440):
                    check_account_sheet(pg, w, h, lang)
                    if lang == "en":
                        check_tier_columns(pg, w)

                if w <= 1023:
                    # Also check More bottom sheet open, constant nav height, focus trap, Escape, backdrop close
                    pg.evaluate("showView('hoy'); window.scrollTo(0, 0);")
                    pg.wait_for_timeout(80)
                    nav_h_closed = pg.evaluate("document.getElementById('sideNav').getBoundingClientRect().height")
                    pg.click("#navMoreBtn")
                    pg.wait_for_timeout(120)
                    m_more = pg.evaluate(MEASURE_BARS_JS)
                    assert_bars(m_more, f"{lang} {w}px more-open", check_more=True)
                    assert abs(m_more["nav"]["h"] - nav_h_closed) <= 0.5, (
                        f"{lang} {w}px: nav height changed on More open ({nav_h_closed} -> {m_more['nav']['h']})"
                    )
                    in_sheet = pg.evaluate("document.getElementById('moreSheet').contains(document.activeElement)")
                    assert in_sheet, f"{lang} {w}px: focus not moved into #moreSheet"
                    for _ in range(7):
                        pg.keyboard.press("Tab")
                    still_in_sheet = pg.evaluate("document.getElementById('moreSheet').contains(document.activeElement)")
                    assert still_in_sheet, f"{lang} {w}px: Tab escaped #moreSheet focus trap"
                    pg.keyboard.press("Escape")
                    pg.wait_for_timeout(80)
                    assert pg.evaluate("document.getElementById('moreSheet').style.display") == "none", (
                        f"{lang} {w}px: Escape did not close #moreSheet"
                    )
                    assert pg.evaluate("document.getElementById('navMoreBtn').getAttribute('aria-expanded')") == "false"
                    pg.click("#navMoreBtn")
                    pg.wait_for_timeout(80)
                    pg.evaluate("document.getElementById('moreSheet').dispatchEvent(new MouseEvent('click', {bubbles:true}))")
                    pg.wait_for_timeout(80)
                    assert pg.evaluate("document.getElementById('moreSheet').style.display") == "none", (
                        f"{lang} {w}px: backdrop click did not close #moreSheet"
                    )

                    # Sticky sub-bar + constant topbar height on scroll > 64px
                    expected_tb_h = 48 if w <= 767 else 56
                    for cv in VIEWS:
                        pg.evaluate(f"showView('{cv}'); window.scrollTo(0, 0);")
                        pg.wait_for_timeout(80)
                        scrollable = pg.evaluate("document.documentElement.scrollHeight - window.innerHeight > 80")
                        if scrollable:
                            pg.evaluate("window.scrollTo(0, 120);")
                            pg.wait_for_timeout(220)
                            cm = pg.evaluate("""() => {
                                const tb = document.getElementById('topbar');
                                const sb = document.getElementById('stickyViewBar');
                                const vt = document.getElementById('topbarViewTitle');
                                const fab = document.getElementById('qlFab');
                                const nav = document.getElementById('sideNav');
                                const visibleH1 = [...document.querySelectorAll('h1')].filter(el => {
                                    const cs = getComputedStyle(el);
                                    return cs.display !== 'none' && cs.visibility !== 'hidden' && el.getBoundingClientRect().height > 0;
                                }).length;
                                return {
                                    compact: document.body.classList.contains('topbar-compact'),
                                    tbH: +tb.getBoundingClientRect().height.toFixed(1),
                                    sbTop: +sb.getBoundingClientRect().top.toFixed(1),
                                    sbAriaHidden: sb.getAttribute('aria-hidden'),
                                    titleText: vt.textContent.trim(),
                                    titleTag: vt.tagName,
                                    sbOpacity: +getComputedStyle(sb).opacity,
                                    visibleH1,
                                    fabOpacity: +getComputedStyle(fab).opacity,
                                    fabBottom: +fab.getBoundingClientRect().bottom.toFixed(1),
                                    navTop: +nav.getBoundingClientRect().top.toFixed(1),
                                };
                            }""")
                            assert cm["compact"], f"{lang} {w}px {cv}: body.topbar-compact missing at scrollY=120"
                            assert abs(cm["tbH"] - expected_tb_h) <= 0.5, (
                                f"{lang} {w}px {cv}: topbar height changed on scroll: {cm['tbH']} != {expected_tb_h}"
                            )
                            assert abs(cm["sbTop"] - expected_tb_h) <= 1.0, (
                                f"{lang} {w}px {cv}: stickyViewBar top {cm['sbTop']} != {expected_tb_h}"
                            )
                            assert cm["titleText"] and cm["sbOpacity"] >= 0.9, (
                                f"{lang} {w}px {cv}: sticky view title missing/hidden: {cm}"
                            )
                            assert cm["sbAriaHidden"] == "false" and cm["titleTag"] != "H1", (
                                f"{lang} {w}px {cv}: sticky title heading/aria invalid: {cm}"
                            )
                            assert cm["visibleH1"] == 1, f"{lang} {w}px {cv}: visible h1 count {cm['visibleH1']} != 1"
                            assert cm["fabOpacity"] >= 0.9 and cm["fabBottom"] <= cm["navTop"] - 8, (
                                f"{lang} {w}px {cv}: FAB missing or too close to bottom bar: {cm}"
                            )
                            pg.evaluate("window.scrollTo(0, 0);")
                            pg.wait_for_timeout(220)
                            restored = pg.evaluate("""() => ({
                                compact: document.body.classList.contains('topbar-compact'),
                                tbH: +document.getElementById('topbar').getBoundingClientRect().height.toFixed(1),
                            })""")
                            assert not restored["compact"] and abs(restored["tbH"] - expected_tb_h) <= 0.5, (
                                f"{lang} {w}px {cv}: sticky bar did not restore at scrollY=0: {restored}"
                            )

                # Also check offline syncBadge (state-off) keeps 3-zone topbar untouched at 320px
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
