# PROMPT — Fase 2: Corrector de Writing con IA (rúbrica Cambridge real)

Sos un ingeniero senior. Repo `/home/juan/b2first-tracker` (cwd correcto). Español
rioplatense. **Este turno es para CODIFICAR, no para narrar.**

## Estado del repo (no lo re-investigues)

- `server.py` (≈700 líneas) Python **stdlib**, `ThreadingHTTPServer`. Ya existe `store.py`
  con el seam de almacenamiento. Endpoints en `_handle()`: `/`, `/libros`, `/files/`,
  `/assets/`, `/libros.json`, `/api/users`, `/api/register`, `/api/login`, `/api/logout`,
  `/api/me`, `/api/progress`. Hay `do_GET/do_PUT/do_POST/do_HEAD`.
- `index.html` single-file: nav con `<button data-view="hoy|exam|partes|prog|graf|plan|err|libros">`,
  vistas `#view-*`, `refreshAll()` central, `SETTINGS_DEFAULT` (tiene `aiKey` ya reservado
  o agregalo), `D.log[]` con `{type,date,part,correct,total,min,score,kind,...}`.
- Servicio systemd `b2first` en 8088. Tests Playwright en `tests/`.

## Regla #1 del proyecto: NADA DE DATOS INVENTADOS

Las band descriptors de Cambridge **no se generan**: se transcriben del handbook oficial
que está en disco:

`/home/juan/Descargas/b2-first/05-Handbooks/b2-first-handbook.pdf` (90 páginas, con capa
de texto). Las escalas de Writing están en las **páginas 32–35** (y 80–81 la versión
For Schools). Extraé el texto así (script de desarrollo, NO dependencia del server):

```bash
uv run --with pypdf python -c "
from pypdf import PdfReader
r=PdfReader('/home/juan/Descargas/b2-first/05-Handbooks/b2-first-handbook.pdf')
for i in (32,33,34,35):
    print('=== PDF PAGE',i+1); print(r.pages[i].extract_text())
"
```

Guardá el script en `tools/extract_rubric.py` (uso manual, nunca importado por `server.py`).

## Tarea A — `prompts.py`

```python
BANDS = {          # 4 criterios × bandas 0–5, transcritas del handbook
  "content": {0: "...", 1: "...", 2: "...", 3: "...", 4: "...", 5: "..."},
  "communicative_achievement": {...},
  "organisation": {...},
  "language": {...},
}
RUBRIC_SOURCE = "B2 First Handbook, páginas 32-35 (Cambridge University Press)"
RUBRIC_TEXT = "..."          # encabezado + las 4 escalas tal cual
WRITING_SYSTEM = """..."""   # rol de examinador senior Cambridge
def writing_prompt(text, kind): ...   # devuelve el user prompt
SCHEMA_KEYS = ("content","communicative_achievement","organisation","language")
```

Cada valor de `BANDS` lleva un comentario `# pág N` indicando de dónde salió. Si una banda
no es legible en el PDF, poné `"ver RUBRIC_SOURCE pág N"` — **nunca la inventes**.

Reglas del prompt de sistema:
- Devolver **sólo JSON**, sin markdown ni texto extra.
- Notas enteras 0–5 por criterio, cada una con **una cita textual** del texto del alumno
  que la justifique (`quotes`). Si no hay cita válida, la banda es inválida.
- Feedback al alumno en **español rioplatense**; las citas y las correcciones de inglés en inglés.
- `rewrite`: exactamente 3 oraciones mejoradas del propio texto (no texto nuevo).
- Prohibido inventar reglas gramaticales.

## Tarea B — endpoint proxy `POST /api/ai/writing` en `server.py`

Request: `{"text": "...", "kind": "Essay", "provider_key": "..."}` (o `"provider"` opcional).

Respuesta 200:
```json
{"bands":{"content":4,"communicative_achievement":3,"organisation":4,"language":3},
 "total":14,
 "feedback":{"content":"...","communicative_achievement":"...","organisation":"...","language":"..."},
 "quotes":{"content":"...","communicative_achievement":"...","organisation":"...","language":"..."},
 "rewrite":["...","...","..."],
 "model":"gemini-2.0-flash"}
```

Códigos: `400` texto fuera de 50–3000 chars o `kind` no permitido (`Essay|Article|Report|Review|Email`)
· `422` respuesta del modelo que no valida el schema · `429` rate limit · `502` proveedor
caído/timeout/sin key.

Implementación obligatoria:
- `urllib.request` de stdlib. **Cero dependencias nuevas.**
- Proveedor Gemini: `POST {B2_AI_BASE}/models/{model}:generateContent` con
  `{"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseMimeType":"application/json","temperature":0.2}}`
  y header `x-goog-api-key`. Default `B2_AI_BASE=https://generativelanguage.googleapis.com/v1beta`,
  `B2_AI_MODEL=gemini-2.0-flash`. **Las dos por variable de entorno** (así el test usa un mock local).
- Key: la del body; si falta, `os.environ["B2_AI_KEY"]`. **Nunca** se persiste, **nunca** se
  escribe en logs, **nunca** aparece en el cuerpo del error.
- Timeout duro **25 s**. JSON parseado con try/except; si falta una de las 4 claves, o un valor
  no es entero 0–5, o `rewrite` no tiene 3 strings → **422**.
- Rate limit en memoria con `threading.Lock`: **10/min y 60/hora por IP** (`X-Forwarded-For`
  si viene, si no `self.client_address[0]`). Responder 429 con `{"error":"rate limit"}`.

## Tarea C — Tab IA en `index.html`

1. Botón nuevo en el nav: `<button data-view="ia">✨ AI</button>` y su vista `#view-ia`,
   siguiendo el mecanismo de las vistas existentes (no inventes otro router).
2. Card **Corrector de Writing**: `<textarea id="iaText">` con contador de palabras
   (objetivo 140–190), `<select id="iaKind">` con los 5 `kind`, botón `Corregir`.
3. Al responder: 4 tarjetas con `x/5` y color por banda (0–2 rojo, 3 ámbar, 4–5 verde),
   el `feedback` debajo, `quotes` en un `<details>` y `rewrite` en lista.
4. Estados visibles: `idle` → `loading` (spinner + "corrigiendo…") → `ok` / `error` con
   botón "Reintentar". Si el server tarda o falla, la UI **no** queda colgada.
5. Al obtener resultado, **guardar en `D.log`**:
   `{type:'w', date:dayKey(new Date()), kind, kb,kc,ko,kl, total, min:0, note:'IA', text}`.
   Después `save()` y `refreshAll()` (para que aparezca en LOG y en los gráficos existentes).
6. Key: input en la pestaña **PLAN** → `D.settings.aiKey` (localStorage). Texto de aviso:
   *"tu key se guarda sólo en este dispositivo y viaja al server local"*. Nunca la loguees.
7. Si `D.settings.aiKey` está vacía, la card muestra un aviso con link a
   `https://aistudio.google.com/apikey` y el botón deshabilitado.

## Tarea D — `tests/test_ai.py` (sin red, sin keys reales)

Levantá un **mock provider** con `http.server` en un puerto libre (ej. 8123) que responda
el JSON del schema, y arrancá `server.py` con `B2_AI_BASE=http://127.0.0.1:8123/v1beta`
y `PORT` alternativo (patrón de `test_sync.py`: importar `server`, setear `DATA_DIR`/`PORT`
**antes** de levantar).

Asserts obligatorios (≥8):
1. texto de 10 chars → 400
2. `kind` inválido → 400
3. sin key → 502
4. mock responde bien → 200 con las 4 bandas y `total` = suma
5. mock responde JSON sin una clave → 422
6. mock responde banda `7` → 422
7. mock responde `rewrite` con 2 strings → 422
8. 11 requests seguidas → la 11ª es 429
9. la key enviada **no** aparece en el archivo de log del server ni en la respuesta de error

### Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
python3 -c "import prompts;print('BANDS OK', list(prompts.BANDS), len(prompts.RUBRIC_TEXT))"
curl -s -o /dev/null -w 'GET / -> %{http_code}\n' http://127.0.0.1:8088/
cd tests && uv run --with playwright python test_ai.py 2>&1 | tail -15
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -5
```

## Prohibido

- Agregar dependencias al runtime (pypdf **sólo** en `tools/`).
- Inventar band descriptors. Si el PDF no se puede leer, dejá el placeholder y decilo.
- Guardar o loguear la API key en cualquier lado.
- Tocar `store.py`, `data/`, `tests/test_final.py` ni los otros tests.
- Reescribir `index.html` de cero: ediciones quirúrgicas.
- `pkill`, `rm -rf`, reiniciar servicios.

## Commit

```
feat(ia): proxy Gemini con rúbrica oficial de Cambridge + tab AI de corrección de Writing
```

Respondé al final **sólo** con: archivos tocados, la salida literal de los 5 comandos, y el
hash del commit.
