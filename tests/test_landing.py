"""Phase 40 acceptance: the landing page at / and the app at /app.

Standalone like the other suites: boots the real server on a throwaway data
dir, then checks the routing split, the scoped Permissions-Policy, the PWA
start_url, the crawler files and that the landing pulls nothing from a CDN.
"""
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

from helpers import isolated_server

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = isolated_server()
LANDING = os.path.join(REPO, "landing.html")


def get(path):
    with urllib.request.urlopen(URL + path, timeout=10) as r:
        return r.status, r.read(), r.headers


out = {}

# 1. / is the landing: 200 HTML, one <h1>, no tracker auth overlay.
st, body, h = get("/")
html = body.decode("utf-8")
assert st == 200, st
assert "text/html" in h.get("Content-Type", ""), h.get("Content-Type")
assert len(re.findall(r"<h1[\s>]", html)) == 1, "expected exactly one <h1>"
for needle in ('href="/app"', "/terms", "/privacy", "/security"):
    assert needle in html, needle
assert 'id="authOverlay"' not in html, "the landing leaked the tracker overlay"
out["1_landing"] = {"status": st, "h1": 1, "bytes": len(body)}

st_home, body_home, _ = get("/home")
assert st_home == 200 and body_home == body, st_home
out["1b_home_alias"] = st_home

# 2. /app is still the tracker.
st_app, body_app, h_app = get("/app")
assert st_app == 200, st_app
assert "text/html" in h_app.get("Content-Type", ""), h_app.get("Content-Type")
assert 'id="authOverlay"' in body_app.decode("utf-8"), "tracker overlay missing at /app"
out["2_app"] = {"status": st_app, "bytes": len(body_app)}

# 3. The installed PWA opens the app, not the pitch.
st_man, body_man, _ = get("/assets/manifest.json")
assert st_man == 200, st_man
manifest = json.loads(body_man)
assert manifest["start_url"] == "/app", manifest.get("start_url")
out["3_manifest_start_url"] = manifest["start_url"]

# 4. Microphone is granted only where the speaking studio lives.
pp_root = h.get("Permissions-Policy", "")
pp_app = h_app.get("Permissions-Policy", "")
assert "microphone=(self)" not in pp_root, pp_root
assert "microphone=(self)" in pp_app, pp_app
out["4_permissions"] = {"root": pp_root, "app": pp_app}

# 5. Crawler files are served from the root and point at the sitemap.
st_robots, body_robots, h_robots = get("/robots.txt")
assert st_robots == 200, st_robots
assert "text/plain" in h_robots.get("Content-Type", ""), h_robots.get("Content-Type")
assert "Sitemap:" in body_robots.decode("utf-8"), body_robots[:120]
st_map, body_map, h_map = get("/sitemap.xml")
assert st_map == 200, st_map
assert "xml" in h_map.get("Content-Type", ""), h_map.get("Content-Type")
root = ET.fromstring(body_map)
assert root.tag.endswith("urlset"), root.tag
out["5_crawler_files"] = {"robots": st_robots, "sitemap": st_map}

# 6. No external resources: no CDN, no font host, no analytics. The schema.org
#    string is the JSON-LD vocabulary identifier (it is never fetched), and the
#    GitHub link plus the canonical domain are the only real outbound links.
with open(LANDING, encoding="utf-8") as f:
    source = f.read()
urls = set(re.findall(r"https?://[^\s\"'<>)\\]+", source))
banned = {u for u in urls
          if not (u.startswith("https://github.com/Juan-Martin-Cerezo/b2first-tracker")
                  or u.startswith("https://firsttracker.app")
                  or u == "https://schema.org")}
assert not banned, banned
out["6_external_urls"] = sorted(urls)

print(json.dumps(out, ensure_ascii=False, indent=1))
sys.exit(0)
