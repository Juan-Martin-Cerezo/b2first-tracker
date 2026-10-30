#!/usr/bin/env bash
# tools/audit.sh — reproducible external security audit for the B2 First Tracker.
#
# Read-only probes (GET / HEAD / OPTIONS / TRACE). Dependencies: bash + curl
# only, nothing to install. Usage:
#
#   bash tools/audit.sh [base-url]
#
# Every check prints PASS or FAIL plus one line of evidence. The last line is
# the verdict (PASS/FAIL). Exit code: 0 = every check passed, 1 = at least one
# FAIL. Checks that need TLS are meaningless against a plain http:// target and
# are reported as N/A (neither pass nor fail) — the default target is public.
set -u

BASE="${1:-https://firsttracker.app}"
BASE="${BASE%/}"
MAX=20
case "$BASE" in
  https://*) TLS=1 ;;
  *) TLS=0 ;;
esac

PASS_N=0
FAIL_N=0
NA_N=0

echo "B2 First Tracker — external security audit"
echo "Target: $BASE"
echo "Date:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
printf '%-52s | %-6s | %s\n' "CHECK" "RESULT" "EVIDENCE"
printf '%-52s-+-%-6s-+-%s\n' \
  "----------------------------------------------------" "------" "----------------------------------------"

row() { # row CHECK RESULT EVIDENCE
  printf '%-52s | %-6s | %s\n' "$1" "$2" "$3"
  case "$2" in
    PASS) PASS_N=$((PASS_N + 1)) ;;
    FAIL) FAIL_N=$((FAIL_N + 1)) ;;
    *)    NA_N=$((NA_N + 1)) ;;
  esac
}

code_of() { # code_of URL [curl args...] -> HTTP status (000 on transport failure)
  local url="$1"; shift
  curl -s -o /dev/null --max-time "$MAX" -w '%{http_code}' "$@" "$url" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------
if [ "$TLS" = "1" ]; then
  PROBE=$(curl -s -o /dev/null --max-time "$MAX" \
    -w '%{http_version} %{ssl_verify_result} %{http_code}' "$BASE/" 2>/dev/null)
  PROBE_RC=$?
  HTTP_VER=$(printf '%s' "$PROBE" | cut -d' ' -f1)
  SSL_VER=$(printf '%s' "$PROBE" | cut -d' ' -f2)
  HTTP_CODE=$(printf '%s' "$PROBE" | cut -d' ' -f3)

  if [ "$PROBE_RC" -eq 0 ] && [ "$SSL_VER" = "0" ]; then
    row "TLS certificate verifies" "PASS" "ssl_verify_result=0 (HTTP ${HTTP_CODE:-?})"
  else
    row "TLS certificate verifies" "FAIL" "curl exit $PROBE_RC, ssl_verify_result=${SSL_VER:-n/a}"
  fi

  if [ "$HTTP_VER" = "2" ]; then
    row "HTTP/2 negotiated" "PASS" "HTTP/2"
  else
    row "HTTP/2 negotiated" "FAIL" "got HTTP/${HTTP_VER:-none} (expected 2)"
  fi
else
  row "TLS certificate verifies" "N/A" "plain http:// target"
  row "HTTP/2 negotiated" "N/A" "plain http:// target"
fi

# ---------------------------------------------------------------------------
# Response headers on GET /
# ---------------------------------------------------------------------------
HDRS=$(curl -sI --max-time "$MAX" "$BASE/" 2>/dev/null)

hdr() { # hdr NAME -> header value on GET /, empty when absent
  printf '%s\n' "$HDRS" | grep -i "^$1:" | head -1 | sed 's/^[^:]*: *//' | tr -d '\r'
}

for h in x-content-type-options x-frame-options referrer-policy \
         content-security-policy x-request-id; do
  v=$(hdr "$h")
  if [ -n "$v" ]; then
    row "Header $h present" "PASS" "$(printf '%s' "$v" | cut -c1-56)"
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

# --- fase 24 headers -------------------------------------------------------
HSTS=$(hdr "strict-transport-security")
if printf '%s' "$HSTS" | grep -qi 'max-age=63072000' \
   && printf '%s' "$HSTS" | grep -qi 'includeSubDomains' \
   && printf '%s' "$HSTS" | grep -qi 'preload'; then
  row "HSTS max-age=63072000 + preload" "PASS" "$HSTS"
else
  row "HSTS max-age=63072000 + preload" "FAIL" "${HSTS:-missing}"
fi

CSP=$(hdr "content-security-policy")
for directive in "object-src 'none'" "base-uri 'none'" "frame-ancestors 'none'" "form-action 'self'"; do
  if printf '%s' "$CSP" | grep -qF "$directive"; then
    row "CSP has $directive" "PASS" "$directive"
  else
    row "CSP has $directive" "FAIL" "${CSP:-missing}"
  fi
done
if printf '%s' "$CSP" | grep -q "'unsafe-eval'"; then
  row "CSP has no 'unsafe-eval'" "FAIL" "'unsafe-eval' present"
else
  row "CSP has no 'unsafe-eval'" "PASS" "absent (documented 'unsafe-inline' allowed)"
fi

COOP=$(hdr "cross-origin-opener-policy")
if [ "$COOP" = "same-origin" ]; then
  row "COOP same-origin" "PASS" "cross-origin-opener-policy: $COOP"
else
  row "COOP same-origin" "FAIL" "${COOP:-missing}"
fi

CORP=$(hdr "cross-origin-resource-policy")
if [ "$CORP" = "same-origin" ]; then
  row "CORP same-origin" "PASS" "cross-origin-resource-policy: $CORP"
else
  row "CORP same-origin" "FAIL" "${CORP:-missing}"
fi

PERM=$(hdr "permissions-policy")
if printf '%s' "$PERM" | grep -q 'microphone=(self)'; then
  row "Permissions-Policy present (mic scoped)" "PASS" "$PERM"
elif [ -n "$PERM" ]; then
  row "Permissions-Policy present (mic scoped)" "FAIL" "microphone=(self) missing: $PERM"
else
  row "Permissions-Policy present (mic scoped)" "FAIL" "missing"
fi

TIMING=$(hdr "server-timing")
if printf '%s' "$TIMING" | grep -Eq 'app;dur=[0-9]'; then
  row "Server-Timing reports internal time" "PASS" "$TIMING"
else
  row "Server-Timing reports internal time" "FAIL" "${TIMING:-missing}"
fi

# ---------------------------------------------------------------------------
# Authentication / routing probes
# ---------------------------------------------------------------------------
# X-Forwarded-For reproduces the public path: the TLS proxy in front always adds
# it, and the tokenless legacy owner branch must refuse any proxied request.
CODE=$(code_of "$BASE/api/progress?download=1" -H 'X-Forwarded-For: 203.0.113.9')
if [ "$CODE" = "401" ]; then
  row "GET /api/progress?download=1 no token -> 401" "PASS" "HTTP $CODE"
else
  row "GET /api/progress?download=1 no token -> 401" "FAIL" "HTTP ${CODE:-none} (expected 401)"
fi

CODE=$(code_of "$BASE/api/progress?user=../../etc/passwd")
if [ "$CODE" = "400" ]; then
  row "GET /api/progress?user=../../etc/passwd -> 400" "PASS" "HTTP $CODE"
else
  row "GET /api/progress?user=../../etc/passwd -> 400" "FAIL" "HTTP ${CODE:-none} (expected 400)"
fi

# ---------------------------------------------------------------------------
# /.well-known/security.txt (RFC 9116)
# ---------------------------------------------------------------------------
SEC_TXT=$(curl -s --max-time "$MAX" -w '\n%{http_code}' "$BASE/.well-known/security.txt" 2>/dev/null)
SEC_CODE=$(printf '%s\n' "$SEC_TXT" | tail -1)
SEC_BODY=$(printf '%s\n' "$SEC_TXT" | sed '$d')
if [ "$SEC_CODE" = "200" ]; then
  row "security.txt returns 200" "PASS" "HTTP 200, $(printf '%s' "$SEC_BODY" | head -1 | cut -c1-44)"
else
  row "security.txt returns 200" "FAIL" "HTTP ${SEC_CODE:-none}"
fi
if printf '%s' "$SEC_BODY" | grep -q '^Contact:' \
   && printf '%s' "$SEC_BODY" | grep -q '^Expires:'; then
  row "security.txt has Contact and Expires" "PASS" "$(printf '%s' "$SEC_BODY" | grep -c '^Contact:') Contact line(s)"
else
  row "security.txt has Contact and Expires" "FAIL" "missing Contact/Expires"
fi

# ---------------------------------------------------------------------------
# Sensitive paths: blocked without an existence oracle
# ---------------------------------------------------------------------------
SENSITIVE="/.env /.git/config /data/users.json /data/tokens.json /server.py /store.py /data/users.json.bak"
for p in $SENSITIVE; do
  CODE=$(code_of "$BASE$p")
  if [ "$CODE" = "403" ] || [ "$CODE" = "404" ]; then
    row "Blocked $p" "PASS" "HTTP $CODE"
  else
    row "Blocked $p" "FAIL" "HTTP ${CODE:-none} (expected 403/404)"
  fi
done

# ---------------------------------------------------------------------------
# Error pages, methods, traversal, body limits
# ---------------------------------------------------------------------------
NOTFOUND=$(curl -s --max-time "$MAX" -w '\n%{http_code}' "$BASE/does-not-exist-b2f-9137" 2>/dev/null)
NF_CODE=$(printf '%s\n' "$NOTFOUND" | tail -1)
NF_BODY=$(printf '%s\n' "$NOTFOUND" | sed '$d')
if [ "$NF_CODE" = "404" ] \
   && ! printf '%s' "$NF_BODY" | grep -Eq 'Traceback|/home/|\.py|File "'; then
  row "404 does not leak a stack or path" "PASS" "HTTP 404, body=$(printf '%s' "$NF_BODY" | cut -c1-32)"
else
  row "404 does not leak a stack or path" "FAIL" "HTTP ${NF_CODE:-none}, body=$(printf '%s' "$NF_BODY" | cut -c1-48)"
fi

CODE=$(code_of "$BASE/" --http1.1 -X TRACE)
if [ "$CODE" = "405" ]; then
  row "TRACE -> 405" "PASS" "HTTP $CODE"
else
  row "TRACE -> 405" "FAIL" "HTTP ${CODE:-none} (expected 405)"
fi

CODE=$(code_of "$BASE/" --http1.1 -X FROB)
if [ "$CODE" = "405" ]; then
  row "Unknown method FROB -> 405" "PASS" "HTTP $CODE"
else
  row "Unknown method FROB -> 405" "FAIL" "HTTP ${CODE:-none} (expected 405)"
fi

CODE=$(code_of "$BASE/%2e%2e/%2e%2e/etc/passwd" --path-as-is)
if [ "$CODE" = "400" ]; then
  row "URL-encoded ../ traversal -> 400" "PASS" "HTTP $CODE"
else
  row "URL-encoded ../ traversal -> 400" "FAIL" "HTTP ${CODE:-none} (expected 400)"
fi

# A real 3 MB + 1 body: a declared-but-unsent Content-Length makes the TLS proxy
# in front wait for the body, so the probe uploads it (the origin still rejects
# from the header before reading a byte).
CODE=$(head -c 3145729 /dev/zero | curl -s -o /dev/null --max-time 30 --http1.1 \
  -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  --data-binary @- "$BASE/api/events" 2>/dev/null)
if [ "$CODE" = "413" ]; then
  row "Body > 3 MB rejected before read -> 413" "PASS" "HTTP $CODE"
else
  row "Body > 3 MB rejected before read -> 413" "FAIL" "HTTP ${CODE:-none} (expected 413)"
fi

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
HJSON=$(curl -s --max-time "$MAX" "$BASE/api/health" 2>/dev/null)
HCODE=$(code_of "$BASE/api/health")
if [ "$HCODE" = "200" ] && printf '%s' "$HJSON" | grep -q '"ok": *true'; then
  row "GET /api/health -> 200 ok:true" "PASS" "HTTP 200, \"ok\": true"
else
  row "GET /api/health -> 200 ok:true" "FAIL" "HTTP ${HCODE:-none}, body=$(printf '%s' "$HJSON" | cut -c1-40)"
fi
if printf '%s' "$HJSON" | grep -qiE 'token|password|salt|hash|/home/|/tmp/'; then
  row "Health exposes no sensitive data" "FAIL" "body contains a sensitive key/path"
else
  row "Health exposes no sensitive data" "PASS" "no token/password/hash/absolute path"
fi

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
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
if [ "$NA_N" -gt 0 ]; then
  echo "$PASS_N/$TOTAL checks passed ($NA_N N/A)"
else
  echo "$PASS_N/$TOTAL checks passed"
fi
if [ "$FAIL_N" -eq 0 ]; then
  echo "PASS"
  exit 0
fi
echo "FAIL"
exit 1
