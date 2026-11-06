"""Backlog 48: the README's "How the plan works" section matches the shipped plan.

The section documents the two rotations, the duration table and the skill
cycles, so the test reads the constants that drive them out of index.html
(UNIT_MIN, FULL_SECTION, QUEUE_CYCLES, WEEK_SKILL_PAIRS, ROTATION_MODES) and
compares each claim. It counts every "N min" the section cites and fails when a
value is not in the table, so the README cannot invent a duration. It boots
nothing and reads no data/.

Run: cd tests && python3 test_readme_plan.py
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(REPO, "README.md")
INDEX = os.path.join(REPO, "index.html")

SKILL_LABEL = {"rue": "Reading & Use of English", "l": "Listening",
               "w": "Writing", "sp": "Speaking"}
PAPER_TYPE = {"Reading & Use of English": "ue", "Listening": "l",
              "Writing": "w", "Speaking": "sp"}
PAPER_SKILL = {"ue": "rue", "l": "l", "w": "w", "sp": "sp"}

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
index = read(INDEX)

# --- The section exists exactly once and says something -------------------
heads = re.findall(r"^## How the plan works$", readme, re.M)
check("section_present", len(heads) == 1, len(heads))
match = re.search(r"^## How the plan works$(.*?)(?=^## )", readme, re.M | re.S)
section = match.group(1) if match else ""
check("section_substantial", len(section) >= 1200, len(section))

# --- The constants the section is about, straight from index.html ---------
unit_block = re.search(r"const UNIT_MIN=\{(.*?)\n\};", index, re.S)
check("unit_min_found", bool(unit_block))
unit_min = {}
for skill, body in re.findall(r"(\w+):\{([^}]*)\}", unit_block.group(1) if unit_block else ""):
    unit_min[skill] = {k: int(v) for k, v in re.findall(r"(\w+):(\d+)", body)}
check("unit_min_parsed", set(unit_min) == {"rue", "l", "w", "sp"}, sorted(unit_min))

queue_block = re.search(r"const QUEUE_CYCLES=\{(.*?)\n\};", index, re.S)
check("queue_cycles_found", bool(queue_block))
cycles = {}
for skill, body in re.findall(r"(\w+):\[([^\]]*)\]", queue_block.group(1) if queue_block else ""):
    values = [v.strip().strip("'") for v in body.split(",") if v.strip()]
    cycles[skill] = [int(v) if v.isdigit() else v for v in values]
check("queue_cycles_parsed", set(cycles) == {"rue", "l", "w", "sp"}, sorted(cycles))

full_block = re.search(r"const FULL_SECTION=(\[.*?\]);", index, re.S)
full = [(t, int(m)) for t, m in re.findall(r"\['(\w+)',\s*(\d+)\]",
                                          full_block.group(1) if full_block else "")]
check("full_section_parsed", len(full) == 4, full)
full_min = dict(full)

pairs_block = re.search(r"const WEEK_SKILL_PAIRS=\[(.*?)\];", index, re.S)
pairs = re.findall(r"\['(\w+)','(\w+)'\]", pairs_block.group(1) if pairs_block else "")
check("week_pairs_parsed", len(pairs) == 2, pairs)

modes_block = re.search(r"const ROTATION_MODES=\[(.*?)\];", index, re.S)
modes = re.findall(r"'([a-z-]+)'", modes_block.group(1) if modes_block else "")
check("rotation_modes", modes == ["by-part", "full-section"], modes)

# --- Both modes are named with the labels the Plan tab shows --------------
by_part_label = re.search(r"plan_rotation_by_part:'([^']+)'", index)
full_label = re.search(r"plan_rotation_full_section:'([^']+)'", index)
check("mode_labels_present",
      bool(by_part_label) and bool(full_label)
      and by_part_label.group(1) in section
      and full_label.group(1) in section,
      {"by_part": by_part_label and by_part_label.group(1),
       "full": full_label and full_label.group(1)})
check("mode_values_used_by_ui",
      'value="by-part"' in index and 'value="full-section"' in index)

# --- By part: the skill pairs and the units-per-session range -------------
pair_sentence = "{} with {}, then {} with {}".format(
    SKILL_LABEL[pairs[0][0]], SKILL_LABEL[pairs[0][1]],
    SKILL_LABEL[pairs[1][0]], SKILL_LABEL[pairs[1][1]])
check("week_pairs_sentence", pair_sentence in section, pair_sentence)

per_range = re.search(r"n>=(\d+)&&n<=(\d+)", index)
per_lo, per_hi = (int(per_range.group(1)), int(per_range.group(2))) if per_range else (None, None)
check("items_per_session_range",
      per_range is not None and "{}–{} units".format(per_lo, per_hi) in section,
      {"code": [per_lo, per_hi], "range": "{}–{} units".format(per_lo, per_hi)})

# --- Full paper each session: the cycle order ----------------------------
order_sentence = " → ".join(SKILL_LABEL[PAPER_SKILL[t]] for t, _ in full)
check("full_section_order", order_sentence in section, order_sentence)

# --- The duration table matches UNIT_MIN and the paper totals -------------
rows = {}
for paper, units, total in re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|$",
                                      section, re.M):
    if paper in PAPER_TYPE:
        rows[paper] = (units, int(total))
check("table_rows", set(rows) == set(PAPER_TYPE), sorted(rows))

table_minutes = set()
table_totals = {}
for paper, (units, total) in rows.items():
    kind = PAPER_TYPE[paper]
    table_totals[kind] = total
    if kind == "w":
        task = re.search(r"(\d+) per task \((.+)\)", units)
        genres = [g.strip() for g in task.group(2).split(",")] if task else []
        task_min = int(task.group(1)) if task else None
        table_minutes.add(task_min)
        check("writing_tasks_match_cycle", genres == cycles.get("w"), genres)
        check("writing_task_minutes",
              {task_min} == set(unit_min.get("w", {}).values()), unit_min.get("w"))
        check("writing_total", total == 2 * (task_min or 0), total)
    else:
        cited = {int(p): int(m) for p, m in re.findall(r"part (\d+):\s*(\d+)", units)}
        table_minutes.update(cited.values())
        code_minutes = {int(k): v for k, v in unit_min.get(PAPER_SKILL[kind], {}).items()}
        check("{}_minutes_match_table".format(kind), cited == code_minutes,
              {"readme": cited, "code": code_minutes})
        check("{}_total".format(kind), total == sum(cited.values()), total)
    check("{}_total_matches_full_section".format(kind), total == full_min.get(kind),
          {"readme": total, "code": full_min.get(kind)})

# --- No minute outside the table: every "N min" is a table value ----------
cited_minutes = {int(n) for n in re.findall(r"(\d+)\s*min\b", section)}
allowed_minutes = table_minutes | set(table_totals.values())
check("minutes_only_from_table", cited_minutes <= allowed_minutes,
      sorted(cited_minutes - allowed_minutes))

# --- The cycles listed are the cycles the queue consumes ------------------
numeric_cycle = lambda s: list(range(1, len(s) + 1)) == s
for skill in ("rue", "l", "sp"):
    values = cycles.get(skill, [])
    line = "{}: parts 1–{}.".format(SKILL_LABEL[skill], len(values))
    check("{}_cycle_parts".format(skill), numeric_cycle(values) and line in section, line)
writing_line = "Writing: {}.".format(", ".join(cycles.get("w", [])))
check("w_cycle_genres", writing_line in section, writing_line)

# --- The queue position comes from the log, as the section says ----------
check("queue_reads_log_claim", "from the units already in the log" in section)
check("queue_reads_log_code", "queueStartSession(s,log" in index)

print(json.dumps(out, indent=1, ensure_ascii=False))
if failed:
    print("FAILED: " + ", ".join(failed))
    sys.exit(1)
print("ALL OK")
