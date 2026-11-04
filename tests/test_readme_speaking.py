"""Backlog 12: the README's Speaking section describes the shipped exam.

The section is documentation, so the test checks the claims that can drift:
the part minutes against material/speaking.json, every path it names against
the repository, every route against server.py, every B2_* variable against the
Configuration table and the code, and the storage/privacy sentences against
index.html, server.py and store.py. It boots nothing and reads no data/.

Run: cd tests && python3 test_readme_speaking.py
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(REPO, "README.md")
SERVER = os.path.join(REPO, "server.py")
STORE = os.path.join(REPO, "store.py")
INDEX = os.path.join(REPO, "index.html")
BANK = os.path.join(REPO, "material", "speaking.json")
CREDITS = os.path.join(REPO, "assets", "speaking", "CREDITS.json")

out = {}
failed = []


def check(name, cond, detail=""):
    out[name] = "OK" if cond else "FAIL " + str(detail or name)
    if not cond:
        failed.append(name)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


readme = read(README)
server = read(SERVER)
store = read(STORE)
index = read(INDEX)
bank = json.loads(read(BANK))
credits = json.loads(read(CREDITS))

# --- 1. The section exists exactly once and is not a one-line stub --------
heads = re.findall(r"^## The Speaking exam$", readme, re.M)
check("section_present", len(heads) == 1, len(heads))
match = re.search(r"^## The Speaking exam$(.*?)(?=^## )", readme, re.M | re.S)
section = match.group(1) if match else ""
check("section_substantial", len(section) >= 1500, len(section))

# --- 2. The part table carries the minutes the bank actually runs ---------
rows = re.findall(r"^\|\s*\*\*Part (\d)\*\*\s*\|\s*(\d+) min\s*\|", section, re.M)
check("four_parts", [int(n) for n, _ in rows] == [1, 2, 3, 4],
      [n for n, _ in rows])
bank_minutes = {int(p["part"]): int(p["minutes"]) for p in bank["parts"]}
check("part_minutes_match_bank",
      {int(n): int(m) for n, m in rows} == bank_minutes,
      {"readme": rows, "bank": bank_minutes})
total = sum(int(m) for _, m in rows)
check("full_exam_total", total == 14 and "fourteen minutes" in section, total)

# --- 3. Every repository path named in the section exists ----------------
paths = set()
for token in re.findall(r"`([^`\n]+)`", section):
    token = token.strip()
    if token.startswith("/") or "<" in token or " " in token:
        continue
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+/?", token):
        continue
    if "." not in token.rsplit("/", 1)[-1]:
        continue
    paths.add(token)
check("paths_named", bool(paths), sorted(paths))
missing = [p for p in sorted(paths) if not os.path.exists(os.path.join(REPO, p))]
check("paths_exist", not missing, missing)

# --- 4. Every route named in the section is served by server.py ----------
routes = set(re.findall(r"/api/speaking/[a-z]+", section))
check("routes_named", bool(routes), sorted(routes))
dead_routes = [r for r in sorted(routes) if ('"%s"' % r) not in server]
check("routes_served", not dead_routes, dead_routes)
check("bank_is_served", '"/material/speaking.json"' in server)

# --- 5. Every B2_* variable named is documented and read by the code -----
config = re.search(r"^## Configuration$(.*?)(?=^## )", readme, re.M | re.S)
config = config.group(1) if config else ""
envs = set(re.findall(r"\bB2_[A-Z0-9_]+\b", section))
check("env_named", bool(envs), sorted(envs))
undocumented = [v for v in sorted(envs) if ("| `%s` |" % v) not in config]
check("env_in_config_table", not undocumented, undocumented)
unread = [v for v in sorted(envs) if ('"%s"' % v) not in server]
check("env_read_by_server", not unread, unread)

# --- 6. The silence sentence matches the constant ------------------------
words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10}
silence = re.search(r"after (\w+) seconds of silence", section)
declared = words.get(silence.group(1)) if silence else None
const = re.search(r"SPX_SILENCE_PROMPT_S\s*=\s*(\d+)", index)
check("silence_sentence", declared is not None, silence.group(0) if silence else "")
check("silence_matches_code",
      declared is not None and const is not None
      and declared == int(const.group(1)),
      {"readme": declared, "code": const.group(1) if const else None})

# --- 7. The transcript-storage claim matches the client and the server ---
check("transcript_not_stored_claim", "does not" in section
      and "store the transcript" in section)
check("exam_sends_store_transcript_false", "store_transcript:false" in index)
check("server_stores_only_on_request", 'if clean["store_transcript"]:' in server)
check("store_keeps_no_audio", not re.search(r"audio|wav|ogg", store, re.I))

# --- 8. The report grades candidates only and never guesses pronunciation -
check("report_candidate_only_claim", "grades only the candidate's turns" in section)
check("report_uses_candidate_text",
      'speaking_report.candidate_text(clean["transcript"])' in server)
check("pronunciation_not_measured_claim", "not measured" in section)
check("pronunciation_not_measured_ui", "spx_not_measured:'not measured'" in index)
check("pronunciation_comes_from_pa",
      "speaking_report.band_from_pa(clean[\"pa\"])" in server)

# --- 9. The Wikimedia claim is true of the credits file ------------------
check("commons_claim", "Wikimedia Commons" in section)
bad_credits = [k for k, v in credits.items()
               if not str(v.get("page", "")).startswith(
                   "https://commons.wikimedia.org/")
               or not str(v.get("license", "")).strip()]
check("credits_are_commons", credits and not bad_credits, bad_credits[:5])

print(json.dumps(out, indent=1, ensure_ascii=False))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print("ALL OK")
