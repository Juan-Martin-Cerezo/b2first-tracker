#!/usr/bin/env bash
# tools/audit.sh — reproducible external security audit for the B2 First Tracker
# public instance.
#
# Read-only probes (GET / HEAD / OPTIONS). Dependencies: bash + curl only,
# nothing verbose and nothing installed. Usage:
#
#   bash tools/audit.sh [base-url]
#
# Prints a CHECK | RESULT | DETAIL table and ends with the verdict PASS or FAIL
# on the last line. Exit code: 0 = every check passed, 1 = at least one FAIL.
set -u

BASE="${1:-https://vps-server.tail40095b.ts.net}"
BASE="${BASE%/}"
MAX=20

PASS_N=0
FAIL_N=0

echo "B2 First Tracker — external security audit"
echo "Target: $BASE"
echo "Date:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
printf '%-49s | %-6s | %s\n' "CHECK" "RESULT" "DETAIL"
printf '%-49s-+-%-6s-+-%s\n' \
  "-------------------------------------------------" "------" "----------------------------------------"

row() { # row CHECK RESULT DETAIL
  printf '%-49s | %-6s | %s\n' "$1" "$2" "$3"
  if [ "$2" = "PASS" ]; then
    PASS_N=$((PASS_N + 1))
  else
    FAIL_N=$((FAIL_N + 1))
  fi
}

# --- probe: TLS verification and protocol of GET / -------------------------
PROBE=$(curl -s -o /dev/null --max-time "$MAX" \
  -w '%{http_version} %{ssl_verify_result} %{http_code}' "$BASE/" 2>/dev/null)
PROBE_RC=$?
HTTP_VER=$(printf '%s' "$PROBE" | cut -d' ' -f1)
SSL_VER=$(printf '%s' "$PROBE" | cut -d' ' -f2)
HTTP_CODE=$(printf '%s' "$PROBE" | cut -d' ' -f3)

if [ "$PROBE_RC" -eq 0 ] && [ "$SSL_VER" = "0" ]; then
  row "TLS certificate verifies" "PASS" "ssl_verify_result=0 (HTTP code ${HTTP_CODE:-?})"
else
  row "TLS certificate verifies" "FAIL" "curl exit $PROBE_RC, ssl_verify_result=${SSL_VER:-n/a}"
fi

if [ "$HTTP_VER" = "2" ]; then
  row "HTTP/2 negotiated" "PASS" "HTTP/2"
else
  row "HTTP/2 negotiated" "FAIL" "got HTTP/${HTTP_VER:-none} (expected 2)"
fi

# --- probe: response headers of GET / --------------------------------------
HDRS=$(curl -sI --max-time "$MAX" "$BASE/" 2>/dev/null)

hdr() { # hdr NAME -> header value on GET /, empty when absent
  printf '%s\n' "$HDRS" | grep -i "^$1:" | head -1 | sed 's/^[^:]*: *//' | tr -d '\r'
}

for h in x-content-type-options x-frame-options referrer-policy \
         content-security-policy x-request-id; do
  v=$(hdr "$h")
  if [ -n "$v" ]; then
    row "Header $h present" "PASS" "$(printf '%s' "$v" | cut -c1-60)"
  else
    row "Header $h present" "FAIL" "missing on GET /"
  fi
done

ACAO=$(hdr "access-control-allow-origin")
if [ -n "$ACAO" ]; then
  row "No access-control-allow-origin on /" "FAIL" "access-control-allow-origin: $ACAO"
else
  row "No access-control-allow-origin on /" "PASS" "absent"
fi

XPB=$(hdr "x-powered-by")
if [ -n "$XPB" ]; then
  row "No X-Powered-By on /" "FAIL" "x-powered-by: $XPB"
else
  row "No X-Powered-By on /" "PASS" "absent"
fi

SRV=$(hdr "server")
if [ -z "$SRV" ]; then
  row "No versioned Server banner on /" "PASS" "no Server header"
elif printf '%s' "$SRV" | grep -Eq '[0-9]+\.[0-9]+'; then
  row "No versioned Server banner on /" "FAIL" "server: $SRV"
else
  row "No versioned Server banner on /" "PASS" "server: $SRV (no version)"
fi

# --- probe: progress download without a session token -> 401 ---------------
CODE=$(curl -s -o /dev/null --max-time "$MAX" -w '%{http_code}' \
  "$BASE/api/progress?download=1" 2>/dev/null)
if [ "$CODE" = "401" ]; then
  row "GET /api/progress?download=1 no token -> 401" "PASS" "HTTP $CODE"
else
  row "GET /api/progress?download=1 no token -> 401" "FAIL" "HTTP ${CODE:-none} (expected 401)"
fi

# --- probe: path traversal in the user parameter -> 400 --------------------
CODE=$(curl -s -o /dev/null --max-time "$MAX" -w '%{http_code}' \
  "$BASE/api/progress?user=../../etc/passwd" 2>/dev/null)
if [ "$CODE" = "400" ]; then
  row "GET /api/progress?user=../../etc/passwd -> 400" "PASS" "HTTP $CODE"
else
  row "GET /api/progress?user=../../etc/passwd -> 400" "FAIL" "HTTP ${CODE:-none} (expected 400)"
fi

# --- probe: health endpoint -> 200 with ok:true ----------------------------
HJSON=$(curl -s --max-time "$MAX" "$BASE/api/health" 2>/dev/null)
HCODE=$(curl -s -o /dev/null --max-time "$MAX" -w '%{http_code}' "$BASE/api/health" 2>/dev/null)
if [ "$HCODE" = "200" ] && printf '%s' "$HJSON" | grep -q '"ok": *true'; then
  row "GET /api/health -> 200 ok:true" "PASS" "HTTP 200, \"ok\": true"
else
  row "GET /api/health -> 200 ok:true" "FAIL" "HTTP ${HCODE:-none}, body=$(printf '%s' "$HJSON" | cut -c1-40)"
fi

# --- probe: preflight carries no permissive CORS headers -------------------
OPT=$(curl -s -X OPTIONS -D - -o /dev/null --max-time "$MAX" \
  "$BASE/api/progress" 2>/dev/null)
CORS=$(printf '%s\n' "$OPT" | grep -i '^access-control-allow-' | head -1 | tr -d '\r')
if [ -n "$CORS" ]; then
  row "OPTIONS /api/progress has no CORS headers" "FAIL" "$CORS"
else
  row "OPTIONS /api/progress has no CORS headers" "PASS" "no access-control-allow-* headers"
fi

TOTAL=$((PASS_N + FAIL_N))
echo
echo "$PASS_N/$TOTAL checks passed"
if [ "$FAIL_N" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
echo "FAIL"
exit 1
