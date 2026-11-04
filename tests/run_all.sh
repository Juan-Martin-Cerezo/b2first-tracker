#!/usr/bin/env bash
# Run every tests/test_*.py against this checkout and return one exit code.
#
# Each suite is a standalone script (see tests/README.md). They need no
# project dependencies: uv provides playwright and httpx in a throwaway
# environment, and the stdlib-only suites ignore them.
#
# Usage:
#   ./run_all.sh                # everything
#   ./run_all.sh speaking       # only tests whose file name matches "speaking"
#
# Per-test output lands in tests/out/run_all/<name>.log. Exit status is 0
# only when every selected test exits 0.
set -u

cd "$(dirname "$0")" || exit 1

OUT_DIR="out/run_all"
LOG_DIR="out/run_all"
PER_TEST_TIMEOUT="${RUN_ALL_TIMEOUT:-1200}"
FILTER="${1:-}"

mkdir -p "$OUT_DIR"

selected=()
for file in test_*.py; do
  [ -f "$file" ] || continue
  case "$file" in
    *"${FILTER}"*) selected+=("$file") ;;
  esac
done

if [ "${#selected[@]}" -eq 0 ]; then
  echo "no tests match '${FILTER}'" >&2
  exit 1
fi

passed=0
failed=()
started=$(date +%s)

for file in "${selected[@]}"; do
  name="${file%.py}"
  log="$LOG_DIR/$name.log"
  echo "=== $name"
  if timeout "$PER_TEST_TIMEOUT" \
      uv run --no-project --quiet --with playwright --with httpx \
      python "$file" >"$log" 2>&1; then
    passed=$((passed + 1))
    echo "    PASS  ($log)"
  else
    code=$?
    failed+=("$name")
    if [ "$code" -eq 124 ]; then
      echo "    FAIL  timeout after ${PER_TEST_TIMEOUT}s ($log)"
    else
      echo "    FAIL  exit $code ($log)"
    fi
    tail -n 5 "$log" | sed 's/^/    | /'
  fi
done

elapsed=$(( $(date +%s) - started ))
total=${#selected[@]}
echo
echo "run_all: $passed/$total passed in ${elapsed}s"
if [ "${#failed[@]}" -gt 0 ]; then
  printf 'failed: %s\n' "${failed[*]}"
  exit 1
fi
exit 0
