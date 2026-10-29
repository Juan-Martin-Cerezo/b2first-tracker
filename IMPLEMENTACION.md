# IMPLEMENTACIÓN — paso por paso

> Documento de ejecución. Cada tarea tiene archivo, ancla, criterio de aceptación y cómo
> se verifica. Orden **estricto**: no arrancar una fase sin cerrar la anterior.
> Líneas de referencia verificadas el 29/10/2026 — se corren al editar, buscar por nombre.
> Plan general: [PLAN-HACKATHON-IA.md](PLAN-HACKATHON-IA.md)

Estado del repo hoy: `index.html` 4.233 líneas · `server.py` 671 · 6 suites Playwright ·
workspace limpio, remoto privado.

---

# FASE 0 — Cimientos (medio día)

## 0.1 Rama de trabajo

```bash
cd ~/b2first-tracker
git checkout -b feat/ia-hackathon
git status   # debe estar limpio
```

**DoD**: rama creada, `git status` sin cambios sin commitear.

## 0.2 `store.py` — el seam de almacenamiento

**Por qué**: hoy `server.py` lee/escribe JSON en 12 lugares distintos. Sin este archivo,
migrar a SQLite (para que lo use mucha gente) implica tocar todo el server.

Crear `store.py` con exactamente estas funciones y **ninguna otra**:

```python
get_user(uid) -> dict|None
create_user(uid, record) -> None
list_users() -> dict              # {uid: record}
get_progress(uid) -> dict|None
put_progress(uid, data) -> None   # incluye el backup rotado (BK_KEEP=20)
backup(uid, label=None) -> str    # devuelve path del backup
```

Reglas:
- Implementación JSON, mismo formato en disco que hoy. **Cero migración de datos.**
- `store.py` no sabe nada de HTTP: no importa `http.server`, no conoce tokens.
- Los paths se calculan desde una sola constante `DATA_DIR` (ya existe en `server.py`).

Refactor en `server.py`: reemplazar los accesos directos a `users.json` /
`progress.json` / `backups/` por llamadas a `store.*`. Los endpoints y sus respuestas
**no cambian ni un byte**.

**DoD**:

```bash
cd tests
uv run --with playwright python test_sync.py    # persistencia + backups
uv run --with playwright python test_personalization.py
```

Ambas verdes. Si `test_sync.py` falla en backups → el rotado quedó mal en el seam.

## 0.3 Endurecer passwords (ADR-004)

`server.py` hoy: `hash_password(salt, password)` con SHA-256 y mínimo 4 caracteres.

1. Nuevo hash: `hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 200_000)`.
2. El registro guarda `"algo": "pbkdf2"`. Los usuarios viejos no tienen `algo`.
3. En `login_user`: si el registro no tiene `algo` → verificar con SHA-256 legacy y, si
   coincide, **rehashear a pbkdf2 y guardar** (migración transparente).
4. Mínimo de password: 4 → **8** (sólo en registro nuevo; no romper logins viejos).

**DoD**: login con `owner` sigue funcionando; el registro de un usuario nuevo guarda
`algo: pbkdf2`; `data/users.json` muestra el hash nuevo tras el primer login.

## 0.4 Checkpoint de fase

```bash
python3 -c "import re;open('/tmp/app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/app.js
sudo systemctl restart b2first
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8088/api/me
git commit -am "refactor: seam de almacenamiento + hash pbkdf2"
```

---

# FASE 1 — Quick-log + racha (2 días)

> Objetivo de negocio: que registrar una sesión cueste **3 toques y menos de 15 segundos**.
> Hoy tenés 5 sesiones en 67 días. Este es el feature más importante de todos.

## 1.1 Botón flotante

- Ancla: después de `</nav>` del bottom-nav (`index.html` ~línea 996).
- `<button id="qlFab" class="ql-fab" onclick="openQuickLog()">+</button>`
- CSS: `position:fixed; right:16px; bottom:76px; width:56px; height:56px; border-radius:50%`
  (76px para no tapar el nav en mobile). `z-index:60`.
- En desktop (`min-width:900px`): `bottom:24px; right:24px`.

**DoD**: visible en celular sin tapar el nav, clickeable con guante de 44px mínimo.

## 1.2 Modal de 3 pasos

Nuevo bloque HTML antes de `#authOverlay`:

```html
<div id="qlModal" class="overlay hidden">
  <div class="ql-card">
    <h3 id="qlTitle">Registrar sesión</h3>
    <div class="ql-step" id="qlStep1"><!-- chips de tipo --></div>
    <div class="ql-step hidden" id="qlStep2"><!-- numpad de puntaje --></div>
    <div class="ql-step hidden" id="qlStep3"><!-- minutos + nota --></div>
    <div class="ql-actions"><button onclick="closeQuickLog()">Cancelar</button>
      <button id="qlNext" onclick="qlNext()">Siguiente</button></div>
  </div>
</div>
```

**Paso 1 — tipo** (chips, un toque):

| Chip | `type` | Campos que pide |
|---|---|---|
| Use of English | `ue` | part 1–7 + `correct`/`total` |
| Listening | `lp` | part 1–4 + `correct`/`total` |
| Writing | `w` | `kind` (Essay/Article/Report/Review/Email) + texto para el corrector IA |
| Speaking | `sp` | part 1–4 + nota 0–5 |
| Examen completo | `rue` | `correct`/`total` de 70 |

**Paso 2 — puntaje**: numpad propio (`input inputmode="numeric"`), no `<select>`.
Atajos: `0-5`, `6-10`, `11-15`, `16-20`, `21-25`, `26-30` para `correct`.

**Paso 3 — minutos**: precargado desde `D.settings` según tipo
(`ueMin` 50 · `listenMin` 40 · `writeMin` 35 · `sp1Sec+sp2Sec` · `even/odd` para `rue`).
El usuario sólo confirma. Nota opcional libre.

Al confirmar: `D.log.push({...})` → `save()` (dispara sync) → `refreshAll()`.

**DoD**: desde el celular, sesión de UoE registrada en ≤3 toques y ≤15s cronometrados.
Aparece en PROGRESS → LOG al instante. `b2first.service` sin errores en `journalctl`.

## 1.3 Racha (streak) — **derivada, no persistida**

**Decisión**: la racha se calcula desde `D.log`. No se guarda estado nuevo → cero
migraciones, cero bugs de sincronización, y funciona retroactivo con las 5 sesiones
que ya tenés.

Funciones nuevas en `index.html`, sección nueva `STREAK` (después de `renderToday`):

```js
function dayKey(d){ /* 'YYYY-MM-DD' en hora LOCAL, no UTC */ }
function sessionDays(){ /* Set de dayKey únicos de D.log, ignorando fechas futuras */ }
function calcStreak(){
  // devuelve {current, longest, todayDone, atRisk, lastDate, freezesLeft, weekCount}
}
function renderStreak(){ /* pinta la tarjeta en TODAY + el pill del footer */ }
```

### Reglas exactas

1. **Un día cuenta** si tiene ≥1 entrada en `D.log` (cualquier tipo, cualquier duración).
2. `current`: días consecutivos hacia atrás desde **hoy**. Si hoy no hay sesión pero ayer
   sí → `atRisk=true` y la racha **sigue viva** hasta medianoche local.
3. `longest`: máximo histórico de días consecutivos. Se calcula sobre todo el log.
4. **Escudo (freeze)**: `D.settings.streakFreeze = 1`. Saltea **un** día muerto por
   semana ISO sin cortar la racha. Se muestra como `🛡` gastado. Default 1.
5. **Meta semanal**: `D.settings.weekGoal = 5`. `weekCount` = días con sesión en la
   semana actual (lunes→domingo). No corta racha, pero se muestra como anillo `3/5`.
6. **Zona horaria**: `dayKey` usa la fecha local (`d.toLocaleDateString('sv-SE')` da
   `YYYY-MM-DD`). Nunca `toISOString()` — eso corre a UTC y rompe la racha de noche.
7. **No contar futuro**: entradas con fecha > hoy se ignoran.
8. **Día de examen no corta**: si `today` está en `D.examDates` (nuevo, array opcional),
   la racha no se corta ese día.

### UI

Tarjeta en la vista TODAY, arriba del plan:

```
🔥 7 días        récord 12       🛡 1
[================----] 3/5 esta semana
⏰ hoy sin sesión — se corta a medianoche
```

- `current === 0` → `Sin racha — empezá hoy`
- `atRisk` → texto ámbar con el aviso de medianoche
- Pill compacto en el footer: `🔥 7`
- Animación: sólo un `transform:scale` de 150ms al incrementar. Sin confetti.

### Gamificación — límites explícitos

- **Nada de notificaciones push** (no hay service worker, y no se agrega).
- **Nada de puntos ni badges**: la racha es la única métrica social.
- **Nada de castigo visual agresivo** al cortar: se muestra `Sin racha` y el récord.
  Perder una racha no debe dar culpa; el objetivo es el hábito, no la ansiedad.

**DoD**: con log vacío → `Sin racha`. Con sesión hoy y ayer → `🔥 2`. Con 3 días
seguidos y un hueco de 1 día → sigue viva y `🛡` gastado. Test automatizado en 1.5.

## 1.4 `tests/test_streak.py`

Patrón de los tests existentes (`uv run --with playwright python …`). Inyectar datos:

```python
await page.evaluate("""() => {
  D.log = [
    {type:'ue', date:'2026-10-27', correct:12, total:20, min:50},
    {type:'lp', date:'2026-10-28', correct:8, total:10, min:40},
  ];
  save(); refreshAll();
}""")
```

Casos: (a) vacío, (b) hoy+ayer, (c) hueco de 1 día con escudo, (d) hueco de 2 días,
(e) fecha futura ignorada, (f) récord histórico, (g) `weekCount` correcto un domingo.

**DoD**: 7 asserts verdes. Este test corre contra el server real en 8088 (como
`test_final.py`), **sin** tocar `data/` del dueño: usar un usuario de prueba.

---

# FASE 2 — Corrector de Writing con IA (3 días)

## 2.1 Extraer la rúbrica oficial (no inventarla)

Regla dura del proyecto: nada de datos inventados.

- El handbook oficial está en `~/Descargas/b2-first/`. Localizar la tabla de
  **B2 First Writing assessment scales** (4 criterios × 5 bandas, 0–5).
- Si el PDF tiene capa de texto: extraer con `pypdf` (sólo en un script de `tools/`,
  nunca como dependencia del server). Si es sólo-imagen: transcribir a mano y anotar
  en el docstring de dónde salió (archivo + página).
- Guardar en `prompts.py` → `BANDS` (dict) + `RUBRIC_TEXT` (texto para el modelo).

**DoD**: `prompts.py` con las 4 categorías y sus 5 descriptores, cada uno con
comentario de origen (archivo, página). Sin texto generado por IA.

## 2.2 `prompts.py`

```python
BANDS = {...}            # transcrito del handbook
RUBRIC_TEXT = "..."      # encabezado + bandas, tal cual Cambridge
WRITING_SYSTEM = """You are a Cambridge B2 First (FCE) Senior Examiner.
Score ONLY with the rubric provided. Never invent criteria. ..."""
def writing_prompt(text, kind): ...
def diagnostic_prompt(): ...
SCHEMA_WRITING = {...}   # JSON schema estricto, ver 2.4
```

Reglas del prompt (no negociables):
- Responde **JSON**, sin markdown alrededor.
- `temperature: 0.2`.
- Cada banda es entero 0–5 y debe venir acompañada de **una cita textual del texto del
  alumno** que la justifique. Si no hay cita, la banda es inválida.
- El feedback al alumno va en **español rioplatense**; las citas y las correcciones de
  inglés, en inglés.
- Prohibido inventar reglas gramaticales: si no está seguro, no lo afirma.

## 2.3 Endpoint proxy — `POST /api/ai/writing`

Contrato:

```
POST /api/ai/writing
{ "text": "...", "kind": "Essay", "provider_key": "...", "provider": "gemini" }
→ 200 { "bands": {"content":4,"ca":3,"org":4,"lang":3}, "total":14,
        "feedback": {"content":"...","ca":"...","org":"...","lang":"..."},
        "quotes": {...}, "rewrite": ["...","...","..."], "model": "gemini-2.x-flash" }
→ 400 texto <50 o >3000 chars / kind inválido
→ 422 el modelo devolvió algo que no valida el schema
→ 429 rate limit
→ 502 el proveedor falló o timeout
```

Implementación:
- `urllib.request` de stdlib. **Cero dependencias nuevas.**
- Timeout duro 25s. `ThreadingHTTPServer` ya cubre la concurrencia.
- La `provider_key` **nunca** se loguea, nunca se persiste, nunca se devuelve en errores.
- Fallback server-side: si no viene `provider_key` y existe `os.environ["B2_AI_KEY"]`,
  se usa esa (para el demo propio).
- Rate limit en memoria: `10/min` y `60/hora` por IP (`X-Forwarded-For` si existe).
- Validación del schema **en el server**: 4 claves, enteros 0–5, `rewrite` = 3 strings.
  Si falla → 422. Nunca renderizar datos sin validar.

**DoD**:

```bash
curl -s -X POST http://127.0.0.1:8088/api/ai/writing -H 'Content-Type: application/json' \
 -d '{"text":"<200 palabras>","kind":"Essay","provider_key":"..."}' | python3 -m json.tool
```

Devuelve las 4 bandas + quotes + rewrite. Con texto de 10 chars → 400. Con key falsa → 502.

## 2.4 Tab IA en el frontend

- Nuevo botón en el nav: `<button data-view="ia">✨ AI</button>` (después de `err`).
- Vista nueva `#view-ia` con dos tarjetas: **Corrector de Writing** y **Diagnóstico**.
- Corrector: textarea (contador 140–190 palabras), selector `kind`, botón "Corregir".
- Al responder: 4 tarjetas con la banda `x/5`, color por banda (0-2 rojo, 3 ámbar, 4-5 verde)
  y el feedback debajo. Botón "Ver cita" que resalta la oración citada en el textarea.
- Guardar el resultado en `D.log` como `{type:'w', kind, kb,kc,ko,kl, total, date, text}`
  → alimenta GATES y gráficos existentes **sin tocarlos**.
- Key: input en la pestaña PLAN → `D.settings.aiKey` (localStorage). Aviso visible:
  "tu key se guarda sólo en este dispositivo".
- Estados: `idle` → `loading` (spinner + "corrigiendo…") → `ok` / `error` con reintento.

**DoD**: pegar un essay de 180 palabras → 4 bandas en <12s → guardado → aparece en LOG
y en el gráfico de evolución. Con el server apagado, la UI muestra error y no queda colgada.

---

# FASE 3 — Diagnóstico cold-start (2 días)

## 3.1 Qué es

Onboarding con IA para cualquier usuario nuevo (y para vos, que tenés 5 sesiones):
12 ítems en 15 minutos → `D.log[]` + `D.errs[]` iniciales → primer plan concreto.

- 3 ítems de Use of English (parts 1, 2, 4)
- 3 de Reading (parts 5, 6, 7)
- 3 de Listening (parts 1, 3, 4)
- 3 de Writing: un micro-task de 60 palabras + 2 preguntas de gramática fina

## 3.2 Generación

`POST /api/ai/diagnostic` → devuelve 12 ítems en JSON: `{id, module, part, stem,
options[4], answer_index, explanation}`.
Los ítems deben ser **originales**, nivel B2, y validados por schema (4 opciones
exactas, `answer_index` 0–3).

**No se usan exámenes oficiales** para esto: son material con copyright y el proyecto
prohíbe la piratería. Ítems generados, temática neutra, revisados a mano una vez y
guardados en `material/diagnostico.json` (así el demo no gasta tokens).

## 3.3 Flujo

1. Botón "Hacer diagnóstico (15 min)" en la tab IA.
2. Ítems de a uno, sin feedback hasta el final.
3. Al terminar: `POST /api/ai/diagnose` con las respuestas → devuelve
   `{level_estimate, weak_parts[], plan: [{day, task, min, part}]}`.
4. Se escriben las sesiones en `D.log` (una entrada por módulo) + los errores en
   `D.errs[]` con la taxonomía existente.
5. El plan se guarda en `D.settings.weekPlan` y se muestra en TODAY.

**DoD**: usuario con `D` vacío → completa diagnóstico → tiene plan de 5 días en TODAY
y ≥1 entrada en LOG por módulo. Se puede repetir a los 30 días.

---

# FASE 4 — Publicar (2 días)

## 4.1 Repo público

```bash
git rm --cached -r data/ 2>/dev/null   # ya está en .gitignore, verificar
git ls-files | grep -E "\.key|\.crt|data/"   # DEBE salir vacío
```

- Confirmar que `data/` jamás estuvo commiteado: `git log --all --oneline -- data/`
  Si aparece algo → reescribir historia con `git filter-repo` **y rotar** lo expuesto.
- `LICENSE` MIT. `README.md` en **inglés** (cara al jurado); el actual pasa a `README.es.md`.
- Screenshots: TODAY, tab IA con un Writing corregido, CHARTS.
- `gh repo edit --visibility public` — avisar antes de hacerlo.

## 4.2 Dockerfile + deploy

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY index.html server.py store.py prompts.py ./
COPY material ./material
ENV PORT=8088 DEMO=1
EXPOSE 8088
CMD ["python","server.py"]
```

- `PORT` y `DEMO` leídos de env en `server.py` (hoy el puerto está hardcodeado).
- `DEMO=1` → sin login obligatorio, progreso sólo en `localStorage`, banner visible,
  endpoints de auth deshabilitados.
- Deploy en Render free (o Fly.io sin sleep). Verificar arranque en frío <30s.

**DoD**: URL pública responde 200, el flujo corre completo en navegador limpio, y
`/api/progress` no toca `data/` del deploy.

---

# FASE 5 — Submission (2 días)

- Video 90–120s (guion en `PLAN-HACKATHON-IA.md` §6)
- Formulario Devpost §7: título, descripción, IA usada, repo, video
- Declaración de contribución: qué hice yo (100% del código), qué IA usé
  (Hermes/Claude Code para desarrollo, el modelo elegido para la corrección)
- Submitir **25/11**

---

# Orden de ejecución resumido

| # | Tarea | Fase | Días | Bloquea |
|---|---|---|---|---|
| 1 | Rama + `store.py` | 0 | 0.5 | todo |
| 2 | pbkdf2 + migración | 0 | 0.5 | deploy |
| 3 | FAB + modal quick-log | 1 | 1 | racha |
| 4 | Racha derivada + UI | 1 | 0.5 | — |
| 5 | `test_streak.py` | 1 | 0.5 | — |
| 6 | Rúbrica oficial → `prompts.py` | 2 | 0.5 | corrector |
| 7 | `/api/ai/writing` | 2 | 1 | tab IA |
| 8 | Tab IA + guardado en log | 2 | 1.5 | — |
| 9 | Diagnóstico 12 ítems | 3 | 2 | onboarding |
| 10 | Repo público + README en | 4 | 1 | deploy |
| 11 | Dockerfile + Render + DEMO | 4 | 1 | submission |
| 12 | Video + form | 5 | 2 | — |

**Total: 12 días de trabajo efectivo en 29 de calendario.** El margen es el punto.

---

# No hacer (explícito)

- Reescribir el frontend con framework (ADR-001).
- Agregar dependencias al `server.py` (sigue siendo stdlib puro).
- Notificaciones push o service worker.
- Migrar a Postgres antes de tener usuarios reales (ADR-006).
- Usar exámenes oficiales como ítems del diagnóstico (copyright).
- Persistir la API key en el server.
- Romper los 6 tests existentes.
