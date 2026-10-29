# PROMPT — Fase 2b: soporte DeepSeek en el proxy de IA + plantilla JSON explícita

Sos un ingeniero senior. Repo `/home/juan/b2first-tracker` (cwd correcto). Español
rioplatense. **Este turno es para CODIFICAR, no para narrar.**

## Contexto (ya está implementado, no lo rehagas)

- `prompts.py`: `BANDS` (rúbrica real transcrita del handbook, con comentarios de página),
  `RUBRIC_TEXT`, `WRITING_SYSTEM`, `writing_prompt(text, kind)`, `SCHEMA_KEYS`.
- `server.py`: `POST /api/ai/writing` que habla con **Gemini**
  (`B2_AI_BASE`, `B2_AI_MODEL`, header `x-goog-api-key`), timeout 25 s, rate limit
  10/min + 60/h por IP, validación de schema (4 bandas enteras 0–5, `rewrite` = 3 strings),
  códigos 400/422/429/502. La key nunca se loguea ni se persiste.
- `index.html`: tab **✨ AI** con el corrector; guarda el resultado en `D.log` con
  `{type:'w', kb,kc,ko,kl, total}`.
- `tests/test_ai.py`: 10 asserts contra un mock local, todos verdes.

## Medición real que motiva esta tarea (dato duro, no especulación)

Contra la API real de DeepSeek (`deepseek-chat`, `response_format:{"type":"json_object"}`):

- Con un system prompt genérico, `feedback` volvió como **array** en vez de objeto → schema inválido.
- Con la **forma exacta del JSON escrita en el system prompt**, devolvió perfecto:
  `bands` (4 enteros), `feedback` (objeto de 4 claves), `quotes` (objeto de 4 claves),
  `rewrite` (3 strings). 166 in / 281 out tokens.
- Costo medido: ~$0.0009 por corrección.

Conclusión: **DeepSeek necesita la plantilla explícita**, y el validador del server tiene que
rechazar `feedback`/`quotes` que vengan como array.

## Tarea A — `prompts.py`: plantilla explícita

En `WRITING_SYSTEM` agregá, literal, un bloque con la forma exacta a devolver:

```
Return ONLY this exact JSON shape (no markdown, no extra text):
{"bands":{"content":N,"communicative_achievement":N,"organisation":N,"language":N},
 "feedback":{"content":"...","communicative_achievement":"...","organisation":"...","language":"..."},
 "quotes":{"content":"...","communicative_achievement":"...","organisation":"...","language":"..."},
 "rewrite":["...","...","..."]}
N is an integer 0-5. feedback and quotes are OBJECTS with exactly those 4 keys.
rewrite is an ARRAY of exactly 3 strings. Never return arrays where objects are required.
```

Mantené todo lo que ya está (rúbrica, idioma del feedback en español rioplatense, citas en
inglés, prohibición de inventar criterios).

## Tarea B — `server.py`: dos proveedores

Selector por `os.environ.get("B2_AI_PROVIDER", "deepseek")` (o campo `provider` del body):

| `provider` | Endpoint | Auth | Body |
|---|---|---|---|
| `deepseek` | `{B2_AI_BASE:-https://api.deepseek.com}/chat/completions` | `Authorization: Bearer <key>` | OpenAI wire: `messages` + `response_format:{"type":"json_object"}` + `temperature:0.2` |
| `gemini` | `{B2_AI_BASE:-https://generativelanguage.googleapis.com/v1beta}/models/{B2_AI_MODEL}:generateContent` | `x-goog-api-key` | `contents` + `generationConfig.responseMimeType=application/json` |

Reglas:
- Extraer el texto de la respuesta según proveedor (`choices[0].message.content` vs
  `candidates[0].content.parts[0].text`).
- **Validación estricta nueva**: `feedback` y `quotes` deben ser `dict` con exactamente las
  4 claves de `SCHEMA_KEYS` y valores `str` no vacíos. Si vienen como lista → **422**.
  Igual para `bands` (4 enteros 0–5) y `rewrite` (3 strings).
- `B2_AI_MODEL` default: `deepseek-chat` si el provider es deepseek, `gemini-2.0-flash` si es gemini.
- La key sigue viniendo del body (`provider_key`) o de `B2_AI_KEY`; nunca se loguea ni persiste.
- No romper nada del comportamiento Gemini existente (los 10 asserts actuales siguen válidos).

## Tarea C — `tests/test_ai.py`: 3 asserts nuevos

11. Mock con wire DeepSeek (`choices[0].message.content`) y `feedback` como **objeto** → 200.
12. Mock DeepSeek con `feedback` como **array** → **422**.
13. `provider: "gemini"` en el body sigue funcionando con el mock Gemini → 200.

Los tests deben seguir sin red real (mocks en `127.0.0.1`).

## Tarea D — smoke real documentado (no lo corras con la key del usuario)

Agregá en el README una sección corta `AI provider setup`:

```bash
# en la Pi, fuera del repo:
~/.config/b2first/ai.env   (chmod 600)
B2_AI_KEY=...
B2_AI_PROVIDER=deepseek
# el server lo lee con:  set -a; . ~/.config/b2first/ai.env; set +a; systemctl restart b2first
```

Dejá claro que **la key no va al repo** y que el deploy público usa la key del visitante.

## Prohibido

- Agregar dependencias.
- Guardar/loguear la key. **No** leer `~/.config/b2first/ai.env` desde el código ni desde los tests.
- Tocar `store.py`, `data/`, `tests/test_final.py` ni los otros tests.
- Reescribir `index.html` (en esta fase no hace falta tocarlo).
- `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import prompts,server;print('IMPORT OK');print('shape' , 'rewrite is an ARRAY' in prompts.WRITING_SYSTEM)"
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
cd tests && uv run --with playwright python test_ai.py 2>&1 | tail -18
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -5
```

## Commit

```
feat(ia): soporte DeepSeek + plantilla JSON explícita y validación estricta de feedback/quotes
```

Respondé al final **sólo** con: archivos tocados, salida literal de los 4 comandos, hash del commit.
