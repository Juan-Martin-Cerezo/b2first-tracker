# Fase speaking-today — rediseño minimalista de Speaking en Today

Repo: `/home/juan/b2first-tracker`, HEAD `491c540`.

## Problema

La tarjeta de Speaking en Today (index.html ~3955-4175) está saturada: phase stepper con "Phase 2 · C1 Polish", título "Continuous Simulation", chips de visuales, tres selects (`#spPart`, `#spSil`, `#spRep`), input `#spNeg`, dos botones de timer (`sp1.start`, `sp2.start`) y cinco botones: "Save Speaking", "Proceed to Phase 2: C1 Polish", "Live studio", "Speaking exam", "Live examiner". No se entiende qué hacer.

## Diseño pedido

1. **Materiales primero, pero claramente separados**: una sección sobria "Materials / Materiales" con los recursos del banco de Speaking (chips o lista), visualmente distinta de las acciones: fondo suave, tipografía chica, sin botones primarios. Debe verse que es material de consulta, no una acción.
2. **Solo dos opciones**, cada una en su propio bloque separado (dos tarjetas, una arriba de la otra, con aire entre ellas), nunca en la misma fila de botones:
   - **Speaking Exam**: subtítulo "Cambridge B2 First · full mock or one part". Dos elecciones claras dentro: "Full exam · Parts 1–4" (14 min) y "One part" con selector 1/2/3/4. Un solo botón "Start". La tarea propia (`Use my own task`) sigue disponible dentro de la pantalla de elección del examen, tal como está hoy.
   - **Live Studio**: subtítulo que explique para qué sirve, en una frase: "Talk freely and see your silences and speaking time" / "Hablá libre y mirá tus silencios y tu tiempo de habla". Un solo botón "Open Live Studio".
3. **Nada más**: eliminar el phase stepper de Speaking, "Phase 2 · C1 Polish & Retake", "Proceed to Phase 2", el botón duplicado "Live examiner" (`#spkOpenBtn`), los timers `sp1.start`/`sp2.start`, los tres selects y el input numérico de la tarjeta.
4. **Registro de la sesión**: el log (`saveSP`) no puede desaparecer del producto, pero no debe sumar botones a la vista principal. Moverlo a un cierre compacto dentro de cada flujo: al terminar el examen o al cerrar Live Studio, un bloque "Log this session / Registrar sesión" con los datos mínimos (aciertos no aplica; parte, minutos, silencios) y un botón pequeño "Save session". Si el examen ya sabe la parte y los minutos, precargarlos. Sin campos que el usuario no entienda.
5. **Visual**: minimalista, mismo lenguaje que el resto de la app (dark oklch, sin #000), una sola columna en 390×844, sin scroll horizontal, targets ≥44px, contraste AA. Light y dark. i18n inglés/español para todo lo nuevo; nada hardcodeado.

## Reglas

- Solo `index.html`, estilos internos y los tests afectados. No tocar backend, límites, plan, listening, cuentas, owner, CSP ni landing.
- No romper: `SP_EXAM` (pantallas choose/brief/exam/feedback/report), tareas propias, Live Studio (`liveOpen`/HUD), y el guardado de log (`saveSP`) que alimenta el plan.
- No cambiar `openPlanUnit` ni las acciones existentes que usan otros tests; si algo se elimina, quitar también sus handlers y entradas de i18n para no dejar referencias muertas.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_v2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_exam.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_custom_task.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
```

Los 5 exit=0. Ajustar los tests que referencien los controles eliminados (`spPart`, `spSil`, `spRep`, `spNeg`, `sp1.start`, `sp2.start`, `spkOpenBtn`, phase stepper de speaking) al contrato nuevo; no debilitar asserts de comportamiento.

Capturas 390×844 light/dark y 1280×800 de la sección nueva, con las dos tarjetas visiblemente separadas y los materiales aparte.

## Cierre

Commit `feat(speaking): Today minimalista con Speaking Exam y Live Studio`. Sin deploy.
