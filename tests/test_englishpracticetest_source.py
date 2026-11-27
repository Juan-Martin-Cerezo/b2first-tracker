#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""English Practice Test FCE listening archive is present in the Library."""
import os
import sys

from playwright.sync_api import sync_playwright

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))
sys.path.insert(0, TESTS_DIR)

from helpers import isolated_server, login_owner, OWNER_NAME  # noqa: E402

EXPECTED = {
    "https://englishpracticetest.net/category/fce-b2-listening-tests/",
}


def main():
    base = isolated_server(extra_env={"B2_OWNER_UIDS": OWNER_NAME})
    url = base + "/"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "app", wait_until="networkidle")
        login_owner(pg, url)
        pg.click("nav button[data-view='practice']")
        pg.wait_for_timeout(400)
        rows = pg.evaluate(
            """() => [...document.querySelectorAll('#pracLibList a.exlib-row')]
                .map(a => ({href: a.getAttribute('href') || '', name: a.dataset.name || '',
                            skill: a.dataset.skill || '', type: a.dataset.type || ''}))
                .filter(r => r.href.includes('englishpracticetest.net'))"""
        )
        urls = [r["href"] for r in rows]
        assert len(rows) == 1, f"Expected 1 FCE English Practice Test row, got {len(rows)}: {urls}"
        assert set(urls) == EXPECTED, f"Wrong URLs: {sorted(set(urls) ^ EXPECTED)}"
        assert len(urls) == len(set(urls)), "Duplicate English Practice Test URLs"
        assert all(r["type"] == "online" for r in rows), rows
        skills = {r["skill"] for r in rows}
        assert skills == {"l"}, f"Missing skill: {skills}"
        sw, iw = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
        assert sw <= iw, f"Mobile overflow: {sw} > {iw}"
        assert not errors, f"Page errors: {errors}"
        browser.close()
    print("PASS English Practice Test: FCE B2 listening archive in Library")


if __name__ == "__main__":
    raise SystemExit(main())
