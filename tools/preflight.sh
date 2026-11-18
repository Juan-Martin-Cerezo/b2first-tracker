#!/usr/bin/env bash
# tools/preflight.sh -- release gate. Runs every check in order and stops at
# the first failure. Exit 0 only when the whole chain passes.
#
# Steps:
#   1. py_compile of server.py and mfa.py
#   2. JavaScript syntax of the two inline <script> blocks in index.html
#   3. no inline on*= handler in index.html / landing.html (must be zero)
#   4. no purchase/redemption copy in index.html / landing.html
#   5. core regression suites (override with B2_PREFLIGHT_SUITES)
#   6. tools/pentest.py --spawn
#
# This is a gate, not a CI service: it runs on the operator's host before a
# deploy. See docs/internal/SDLC.md.
#
# Usage: bash tools/preflight.sh
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1

STEP=0
run() {
  STEP=$((STEP + 1))
  printf '\n[%d] %s\n' "$STEP" "$1"
  shift
  if ! "$@"; then
    echo "PREFLIGHT FAIL: step $STEP" >&2
    exit 1
  fi
}

step_py_compile() {
  python3 -m py_compile server.py mfa.py
}

step_js_syntax() {
  command -v node >/dev/null 2>&1 || {
    echo "node is required for the JavaScript syntax check" >&2
    return 1
  }
  python3 - <<'PY'
import re
import subprocess
import sys
import tempfile

src = open("index.html", encoding="utf-8").read()
blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", src, re.S)
if len(blocks) != 2:
    raise SystemExit("expected 2 inline <script> blocks in index.html, found %d"
                     % len(blocks))
for index, block in enumerate(blocks, 1):
    path = tempfile.mktemp(suffix=".js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(block)
    result = subprocess.run(["node", "--check", path],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("script block %d: %s" % (index, result.stderr.strip()), file=sys.stderr)
        raise SystemExit(1)
    print("script block %d: syntax OK" % index)
PY
}

step_no_inline_handlers() {
  local hits
  hits="$(grep -nEo '\bon[a-z]+[[:space:]]*=[[:space:]]*["'"'"']' \
      index.html landing.html || true)"
  if [ -n "$hits" ]; then
    echo "inline on*= handlers found (must be 0):" >&2
    echo "$hits" >&2
    return 1
  fi
  echo "inline on*= handlers: 0"
}

step_no_purchase_copy() {
  local hits
  hits="$(grep -niE '\b(buy|checkout|redeem|purchase|activation[ -]code|comprar)\b' \
      index.html landing.html || true)"
  if [ -n "$hits" ]; then
    echo "purchase/redemption strings found:" >&2
    echo "$hits" >&2
    return 1
  fi
  echo "purchase/redemption strings: 0"
}

step_core_suites() {
  local suites="${B2_PREFLIGHT_SUITES:-test_mfa.py test_auth_gate.py test_spike.py test_security3.py test_multiuser.py}"
  local suite
  for suite in $suites; do
    [ -f "tests/$suite" ] || {
      echo "missing core suite: tests/$suite" >&2
      return 1
    }
    echo "--- $suite"
    ( cd tests && uv run --no-project --quiet --with playwright --with httpx \
        python "$suite" ) || return 1
  done
}

step_pentest() {
  uv run --no-project --quiet --with playwright --with httpx \
    python tools/pentest.py --spawn
}

run "py_compile server.py mfa.py" step_py_compile
run "JavaScript syntax (two script blocks)" step_js_syntax
run "no inline on*= handlers" step_no_inline_handlers
run "no purchase/redemption copy" step_no_purchase_copy
run "core regression suites" step_core_suites
run "pentest --spawn" step_pentest

echo
echo "PREFLIGHT PASS: all $STEP checks passed"
exit 0
