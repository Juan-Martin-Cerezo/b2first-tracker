# PROMPT — Fase 9: onboarding / walkthrough de primer arranque

Sos un ingeniero senior de producto. Repo `/home/juan/b2first-tracker` (cwd correcto).
**Este turno es para CODIFICAR.** Todo en inglés: UI, código, comentarios, mensajes, commits.

## El problema

Alguien abre la app por primera vez y ve diez pestañas, un FAB y datos en cero. No sabe por
dónde empezar ni que la app se construye a partir de dos acciones: **un diagnóstico de 10
minutos** y **loguear cada sesión**. En el demo público esto es peor: el jurado llega en frío.

Falta un onboarding. Y tiene que ser **descartable en un toque** — nadie aguanta 7 pasos.

## Tarea A — Welcome card (primer arranque)

Se muestra **sólo si** `D.settings.onboarded` no está seteado. Es una card centrada en el viewport
(no una página), con backdrop `oklch(0 0 0 / 0.5)` + `backdrop-filter: blur(2px)`.

Contenido (inglés, tono directo, sin marketing):

```
Title:    Build your B2 First in two habits
Body:     This tracker is not a course. It does two things: it tells you which exam parts
          are weak, and it makes every practice session cost 15 seconds to log.
Steps:    1. Take the 10-minute diagnostic → three ranked weaknesses
          2. Log each session in three taps → streak, charts, weekly plan
          3. Paste a Writing task → graded against the official Cambridge criteria
CTA:      Start the diagnostic        (primary, abre la vista DIAGNOSTIC)
Secondary: Explore on my own          (cierra y marca onboarded)
Footer:   Replay this tour later from Plan → Settings.
```

- En modo demo (`config.demo === true`) el subtítulo agrega:
  *"You are in the demo: nothing you type is stored on the server."*
- `Esc`, click en el backdrop y el botón de cerrar → equivalen a **Explore on my own**.
- Nunca se muestra si `D.settings.onboarded === true`.

## Tarea B — Coach marks (3 pasos, después del welcome)

Sólo si el usuario eligió **Start the diagnostic**: 3 tooltips ancorados, uno a la vez,
con `Next / Back / Skip`, contador `1/3`:

1. **Nav** → *"Every view fits here. Today is what you should do right now."*
2. **Quick-log FAB** → *"Log a session in three taps. Do it straight after practising."*
3. **Diagnostic CTA** → *"Start here. Ten minutes, twelve items, three weaknesses."*

Reglas de implementación:
- Anclaje: `getBoundingClientRect()` del elemento real + `position: fixed`, reposicionar en
  `resize` y `scroll` (con `requestAnimationFrame`, sin listeners sin cleanup).
- Si el elemento no existe o no es visible (ej. FAB oculto en desktop), **saltear ese paso**,
  no mostrar un tooltip flotando en el vacío.
- Highlight: `box-shadow: 0 0 0 3px var(--acc), 0 0 0 9999px oklch(0 0 0 / 0.55)` en el target,
  sin `z-index` pelea (`isolation: isolate` en el wrapper).
- Flechita del tooltip apuntando al target, radio concéntrico con el target.

## Tarea C — Accesibilidad (no negociable)

- `role="dialog"` + `aria-modal="true"` + `aria-labelledby` en welcome y en cada coach mark.
- **Focus trap**: Tab cicla sólo dentro del diálogo; al abrir, foco al primer botón; al cerrar,
  foco vuelve al elemento que lo abrió.
- `Esc` cierra. `prefers-reduced-motion: reduce` → sin transición de entrada.
- El tooltip no tapa el elemento que señala (posición calculada con el rect real).

## Tarea D — Persistencia y replay

- `D.settings.onboarded: true` al terminar **o** al saltear (cualquiera de los dos).
- En **Plan → Settings**: botón *"Show the walkthrough again"* → resetea `onboarded` y lo
  relanza en el acto, sin recargar.
- Sobrevive a `save()`/`load()` y al sync. `D.settings` ya viaja en el progreso.

## Tarea E — Empty states (que acompañan al onboarding)

Cada vista vacía deja de ser un hueco:
- **Today** sin sesiones → *"Nothing logged yet. Your first session takes 15 seconds."* + botón `Quick log`
- **Charts** sin datos → *"Charts appear after your first session."* + botón `Quick log`
- **Errors** sin errores → *"No errors logged. Tag a miss after a practice test."*
- **Plan** sin diagnóstico → `needDiag` ya existe: verificá que el texto esté en inglés y el CTA funcione.

## Tarea F — `tests/test_onboard.py`

Server propio en puerto libre (`DATA_DIR` temporal, patrón de `test_sync.py`). Asserts (≥10):

1. primera visita con `localStorage` limpio → welcome visible (`role=dialog`)
2. el foco inicial está dentro del diálogo (no en `body`)
3. `Esc` cierra y `D.settings.onboarded === true`
4. recargar → welcome **no** aparece
5. "Explore on my own" también marca `onboarded` y cierra
6. "Start the diagnostic" abre la vista de diagnóstico **y** muestra el coach mark `1/3`
7. `Next` avanza a `2/3`, `Back` vuelve a `1/3`, `Skip` cierra y marca `onboarded`
8. el paso del FAB se saltea si el FAB no es visible
9. el tooltip no se superpone al rect del target (comparar geometrías)
10. "Show the walkthrough again" desde Settings lo relanza sin recargar
11. `prefers-reduced-motion` → sin animación de entrada (`transition-duration: 0s`)
12. `errores_js` vacío en todo el recorrido

## Prohibido

- Dependencias, frameworks, icon fonts.
- Bloquear la app si el usuario saltea: después de cerrar, todo funciona normal.
- Mostrarlo de nuevo en cada visita.
- Tocar la lógica de racha, plan, diagnóstico, corrector o auth.
- `pkill`, `rm -rf`, reiniciar servicios.

## Verificación obligatoria (pegá la salida literal)

```bash
cd /home/juan/b2first-tracker
python3 -c "import re;open('/tmp/b2f_app.js','w').write(re.search(r'<script>(.*?)</script>',open('index.html').read(),re.S).group(1))" && node --check /tmp/b2f_app.js
cd tests && uv run --with playwright python test_onboard.py 2>&1 | tail -16
cd tests && uv run --with playwright python test_final.py 2>&1 | tail -4
cd tests && uv run --with playwright python test_plan.py 2>&1 | tail -3
```

## Commit

```
feat(onboarding): first-run walkthrough and empty states
```

Respondé al final **sólo** con: archivos tocados, salida literal de los comandos, hash.
