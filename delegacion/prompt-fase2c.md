# PROMPT — Fase 2c: calibración del corrector (el modelo está siendo generoso)

Sos un ingeniero senior. Repo `/home/juan/b2first-tracker` (cwd correcto). Español
rioplatense. **Este turno es para CODIFICAR, no para narrar.**

## Problema medido (evidencia real, no opinión)

Dos correcciones reales contra la API en producción, con textos que **no** son Band 5:

| Texto | Resultado del modelo actual |
|---|---|
| Email al editor, 160 palabras, B2 correcto pero simple | `content 5, ca 5, org 5, language 4` → **19/20** |
| Ensayo corto sobre IA en la escuela, oraciones cortas y repetitivas | `content 5, ca 5, org 5, language 4` → **19/20** |

Un examinador real no da 5/5/5 a esos textos. **El corrector está inflando las bandas**, y
eso es peor que no corregir: si te dice 19/20 no estudiás lo que falta.

Causa probable: no hay instrucción de estrictez, ni anclaje a evidencia negativa, ni
obligación de justificar por qué NO es una banda más alta.

## Tarea A — `prompts.py`: reglas de calibración en `WRITING_SYSTEM`

Agregá, además de lo que ya está (rúbrica, plantilla JSON, idioma), estas reglas — redactadas
en inglés porque el modelo rinde mejor así, pero el feedback final sigue en español rioplatense:

```
CALIBRATION RULES (mandatory):
1. Be strict. Band 5 means performance at the top of B2 / start of C1. Most real B2
   candidates land in 3-4, and a typical school essay is 3.
2. Before assigning any band, silently list at least 2 concrete weaknesses of the text
   for EACH criterion. If you can name 2 weaknesses in a criterion, that criterion
   CANNOT be 5.
3. For every criterion you score 4 or 5, state in the feedback WHY IT IS NOT ONE BAND HIGHER.
   This justification is mandatory and goes in the feedback text.
4. Band 5 on 'language' requires: a wide range of structures (conditionals, passives,
   relative clauses, perfect tenses) AND no more than one minor slip.
   Simple but correct sentences = 3, not 5.
5. Band 5 on 'organisation' requires: clear paragraphing with a developed argument in
   each paragraph AND a range of linking devices. A list of 'Firstly/Secondly' with
   one sentence each = 3.
6. Do not reward effort, length or neatness. Only observable features in the rubric.
7. If the text is under 120 words for a Part 1 task (140-190 expected), 'content'
   cannot exceed 3.
```

Además, agregá al JSON un campo nuevo **`weaknesses`**: objeto con las 4 claves, cada una
una lista de 2 strings (las debilidades concretas). Es la evidencia que fuerza la calibración.

Forma final del JSON a devolver (actualizá la plantilla del system prompt):

```
{"bands":{...4 enteros 0-5...},
 "feedback":{...4 strings, español rioplatense...},
 "quotes":{...4 citas textuales...},
 "weaknesses":{"content":["...","..."],"communicative_achievement":["...","..."],
               "organisation":["...","..."],"language":["...","..."]},
 "rewrite":["...","...","..."]}
```

Agregá `"weaknesses"` a `SCHEMA_KEYS` si hace falta (o una tupla aparte
`SCHEMA_KEYS_EXTRA = ("weaknesses",)` y usala en la validación).

## Tarea B — `server.py`: validar `weaknesses`

- `weaknesses` debe ser `dict` con las 4 claves, cada valor **lista de ≥2 strings no vacíos**.
- Si falta o viene con 1 string → **422**.
- Devolver `weaknesses` en la respuesta 200 (el frontend lo va a mostrar).
- Sin cambios de contrato para el resto.

## Tarea C — `index.html`: mostrar las debilidades

- En cada tarjeta de criterio, debajo del feedback, mostrar las 2 debilidades como lista
  con viñeta y color ámbar.
- No romper el guardado en `D.log` ni el resto de la tab AI.

## Tarea D — tests (`tests/test_ai.py`)

- 14: mock sin `weaknesses` → 422
- 15: mock con `weaknesses.language` de 1 solo string → 422
- 16: mock completo con `weaknesses` → 200 y la respuesta incluye las 8 debilidades
- Los 13 asserts existentes tienen que seguir verdes (actualizá los mocks para incluir
  `weaknesses`, si no los viejos 200 se vuelven 422).

## Prohibido

- Tocar la rúbrica `BANDS` (es la oficial; ya está transcrita).
- Agregar dependencias, guardar/loguear la key.
- Tocar `store.py`, `data/`, `tests/test_final.py`.
- `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import prompts;print('CALIB OK', 'CALIBRATION RULES' in prompts.WRITING_SYSTEM, 'weaknesses' in prompts.WRITING_SYSTEM)"
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
cd tests && uv run --with playwright python test_ai.py 2>&1 | tail -20
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -5
```

## Commit

```
feat(ia): calibración estricta de bandas + campo weaknesses como evidencia obligatoria
```

Respondé al final **sólo** con: archivos tocados, salida literal de los 4 comandos, hash del commit.
