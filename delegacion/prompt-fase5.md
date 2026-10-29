# PROMPT — Fase 5: paquete de submission del hackathon (sólo documentación)

Sos un ingeniero senior + technical writer. Repo `/home/juan/b2first-tracker` (cwd correcto).
Español rioplatense para lo interno; el material de submission va en **inglés** porque lo lee
el jurado. **Este turno es para ESCRIBIR ARCHIVOS, no para tocar la app.**

## Contexto del hackathon

- **Build Your First AI App 2026** (Devpost, host Yasir Insights). Deadline
  **27/11/2026 17:00 EST**. Categorías: AI/ML, Education, Productivity, Beginner Friendly, Open Ended.
- Rúbrica: implementación **30%**, creatividad **25%**, impacto real **25%**, presentación/docs **20%**.
- La app es un tracker de Cambridge B2 First: single-file frontend, backend stdlib, y ahora
  corrección de Writing con IA usando la **rúbrica oficial de Cambridge** transcrita del handbook.

## Tarea A — `SUBMISSION.md` (inglés)

Estructura exacta (Devpost pide estos bloques):

1. **Inspiration** — por qué existe: prepararse solo para el B2 First sin feedback de Writing
   (25% del examen) y con un tracker que no se usaba.
2. **What it does** — sesiones, racha, diagnóstico de 12 ítems, gráficos, y el corrector de
   Writing con 4 bandas Cambridge + `weaknesses` obligatorias + reescritura de 3 oraciones.
3. **How we built it** — un `index.html` sin build, `server.py` sólo stdlib, JSON en disco,
   proxy de IA con validación estricta de schema, rúbrica transcrita del handbook oficial.
4. **Challenges we ran into** — 3 reales, con el dato concreto:
   - el corrector inflaba las bandas (19/20 a textos mediocres) → reglas de calibración +
     campo `weaknesses` obligatorio que el server valida (422 si falta);
   - DeepSeek devolvía `feedback` como array → plantilla JSON explícita + validación estricta;
   - PDFs de Writing sin capa de texto → links oficiales en vez de extracción.
5. **Accomplishments** — separación real de bandas medida: texto débil 9/20, medio 14/20,
   fuerte 20/20 (antes los tres daban ~19/20).
6. **What we learned** — que un corrector generoso es peor que no corregir.
7. **What's next** — Speaking Parts 3-4 con IA, plan semanal derivado del diagnóstico,
   almacenamiento SQLite para multiusuario.
8. **Built With** — lista literal para Devpost: `python`, `javascript`, `html`, `css`,
   `docker`, `deepseek`, `gemini`, `playwright`, `systemd`, `linux`, `raspberry-pi`.

Reglas: sin hipérbole vacía, sin "revolutionary", sin emojis. Números concretos y verificables.
No inventar métricas que no estén en este repositorio.

## Tarea B — `docs/VIDEO-SCRIPT.md` (inglés, 90–110 segundos)

Guion por tomas, con `[0:00–0:08]` y texto exacto a decir. 6 tomas:

1. El problema en 8 segundos (Writing es 25% del examen y nadie te corrige).
2. Diagnóstico de 12 ítems en 10 minutos → 3 debilidades.
3. Quick-log de 3 toques + racha (mostrar el FAB).
4. Corrector: pegar un essay → 4 bandas + debilidades + reescritura.
5. La calibración: mostrar que un texto malo saca 9/20 y uno bueno 20/20.
6. Cierre: repo público + cómo correrlo (`python3 server.py`).

Cada toma con: qué se ve en pantalla, qué se dice, y qué NO mostrar (datos personales).
Sin música ni claims falsos.

## Tarea C — `docs/DEVPOST-FIELDS.md` (inglés)

Tabla campo → valor listo para copiar/pegar en el formulario de Devpost:
Project name, Elevator pitch (≤200 chars), Thumbnail suggestion, Video URL placeholder,
GitHub URL, "Try it out" URL placeholder, Built with, Tags, y la respuesta a
"Country of residence".

## Tarea D — no tocar nada más

- **No** modificar `index.html`, `server.py`, `prompts.py` ni tests.
- **No** agregar dependencias ni secrets.
- Si `README.md` menciona el hackathon, no lo cambies.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
ls -l SUBMISSION.md docs/VIDEO-SCRIPT.md docs/DEVPOST-FIELDS.md
python3 -c "
import re
s=open('SUBMISSION.md').read()
for sec in ['Inspiration','What it does','How we built it','Challenges','Accomplishments','What we learned','What\'s next','Built With']:
    print(('OK  ' if sec.lower() in s.lower() else 'FALTA '), sec)
print('chars:', len(s))
"
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -4
```

## Commit

```
docs(submission): paquete de submission del hackathon (descripción, guion de video, campos Devpost)
```

Respondé al final **sólo** con: archivos creados, salida literal de los comandos, hash del commit.
