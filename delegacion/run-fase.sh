#!/usr/bin/env bash
# Runner de fases delegadas de b2first-tracker.
# Uso: delegacion/run-fase.sh <fase> [agy|cc]
#   fase 0 => delegacion/prompt-fase0.md
# Cadena de harness: agy gemini-4-argon-medium -> (cuota) -> command-code mimo-v2.6-pro
# Estado en ~/.cache/b2f/deleg.json  (lo lee el watchdog de 10m)
set -uo pipefail

REPO="/home/juan/b2first-tracker"
FASE="${1:?falta la fase}"
HARNESS="${2:-agy}"
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
CACHE="$HOME/.cache/b2f"; mkdir -p "$CACHE"
STATE="$CACHE/deleg.json"
LOG="$CACHE/fase${FASE}-${HARNESS}-$(date +%Y%m%d-%H%M%S).log"

AGY_MODEL="${AGY_MODEL:-gemini-4-argon-medium}"
CC_MODEL="${CC_MODEL:-xiaomi/mimo-v2.6-pro}"
PROMPT="$REPO/delegacion/prompt-fase${FASE}.md"

cd "$REPO" || exit 90
git config user.name  "Juan Martin Cerezo" >/dev/null 2>&1
git config user.email "83360058+Juan-Martin-Cerezo@users.noreply.github.com" >/dev/null 2>&1

[ -f "$PROMPT" ] || { echo "FALTA $PROMPT"; exit 91; }

BRANCH=$(git rev-parse --abbrev-ref HEAD)
BASE=$(git rev-parse HEAD)
SUCIO=$(git status --porcelain | wc -l)

# ---------- baseline ----------
js_check() {
  python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))"
  node --check /tmp/b2f_app.js 2>/dev/null
}
js_check
JS_EXIT=$?
SVC=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8088/ || echo 000)

{
  echo "== fase $FASE | harness $HARNESS | branch $BRANCH | base ${BASE:0:8}"
  echo "== baseline: node --check=$JS_EXIT | GET / =$SVC | arbol_sucio=$SUCIO"
} | tee -a "$LOG"

if [ "$JS_EXIT" -ne 0 ] || [ "$SVC" != "200" ]; then
  echo "BASELINE ROJO: no se lanza el agente (arreglar primero)" | tee -a "$LOG"
  python3 - "$STATE" "$FASE" "$HARNESS" "$LOG" <<'PY'
import json,sys,time
s,f,h,l=sys.argv[1:5]
json.dump({"fase":f,"harness":h,"status":"blocked","reason":"baseline rojo","log":l,"ts":int(time.time())},open(s,"w"))
PY
  exit 92
fi

# ---------- agente ----------
PROMPT_TXT="$(cat "$PROMPT")"
echo "== lanzando $HARNESS ($([ "$HARNESS" = agy ] && echo "$AGY_MODEL" || echo "$CC_MODEL"))" | tee -a "$LOG"

if [ "$HARNESS" = "agy" ]; then
  agy -p "$PROMPT_TXT" --model "$AGY_MODEL" --dangerously-skip-permissions \
      --print-timeout 45m >>"$LOG" 2>&1
  EXIT=$?
else
  command-code -p "$PROMPT_TXT" -m "$CC_MODEL" --trust --dangerously-skip-permissions \
      --tools-all --skip-onboarding --max-turns 240 >>"$LOG" 2>&1
  EXIT=$?
fi

# ---------- rescate + verificación ----------
if [ -n "$(git status --porcelain)" ]; then
  git add -A && git commit -q -m "wip(delegacion): restos del agente sin commitear (rescatados por el runner)"
fi

COMMITS=$(git log --format=%s "$BASE"..HEAD | grep -vcE '^(docs|chore)\(delegacion\)' || true)
HEAD=$(git rev-parse --short HEAD)
DIRTY=$(git status --porcelain | wc -l)
js_check
JS2=$?
SVC2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8088/ || echo 000)
QUOTA=$(grep -icE "usage limit|quota exceeded|RESOURCE_EXHAUSTED|insufficient credit|429" "$LOG" || true)
NOAUTH=$(grep -icE "not authenticated|401|Unauthorized" "$LOG" || true)

VERDICT="ok"
[ "$COMMITS" -eq 0 ] && VERDICT="sin_commits"
[ "$JS2" -ne 0 ] && VERDICT="js_roto"
[ "$QUOTA" -gt 0 ] && VERDICT="cuota_agotada"
[ "$EXIT" -ne 0 ] && [ "$VERDICT" = "ok" ] && VERDICT="exit_$EXIT"

{
  echo "== fin: EXIT=$EXIT commits=$COMMITS head=$HEAD dirty=$DIRTY js=$JS2 svc=$SVC2 quota=$QUOTA noauth=$NOAUTH"
  echo "== VERDICT: $VERDICT"
} | tee -a "$LOG"

python3 - "$STATE" "$FASE" "$HARNESS" "$LOG" "$VERDICT" "$COMMITS" "$HEAD" "$EXIT" "$QUOTA" "$NOAUTH" <<'PY'
import json,sys,time
s,f,h,l,v,c,head,e,q,na=sys.argv[1:11]
json.dump({"fase":f,"harness":h,"status":"finished","verdict":v,"commits":int(c),
           "head":head,"exit":int(e),"quota":int(q),"noauth":int(na),
           "log":l,"ts":int(time.time())},open(s,"w"))
PY

# 2 = cuota agotada -> el watchdog cambia de harness
[ "$VERDICT" = "cuota_agotada" ] && exit 2
[ "$VERDICT" = "ok" ] && exit 0
exit 1
