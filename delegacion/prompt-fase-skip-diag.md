# Fase skip-diag — poder saltear el chequeo de 12 preguntas en el onboarding

Repo: `/home/juan/b2first-tracker`. Base: HEAD `61056ae`.

Juan pidió: "hagamos que el check de 12 preguntas se pueda saltear en el onboarding". Hoy el paso 3 del wizard es obligatorio: el comentario en `index.html:2840-2842` lo dice explícito y la única salida es empezar el diagnóstico.

## Comportamiento esperado

En el paso 3, cuando todavía no hay `D.diag`, mostrar junto a "Start the check" un botón secundario "Skip for now" que:

1. No abre el diagnóstico ni toca `D.diag`.
2. Guarda `D.profile.diagSkipped=true` (crear `D.profile` con `obDraftProfile()` si falta) y `D.onboardStep=4`.
3. Cierra la vista de diagnóstico y vuelve al wizard en el paso 4 (plan), igual que `obAfterDiagnostic()`, sin marcar `D.onboarded`.
4. Deja el flujo normal intacto: si el usuario ya tiene `D.diag`, el paso 3 sigue mostrando el resumen + "Continue to my plan" como hoy, sin botón de skip.

El usuario tiene que poder hacer el diagnóstico después desde la vista Diagnostic (ya existe el banner); no hace falta tocar esa vista.

## Qué cambiar

1. `index.html`
   - Paso 3 sin diag (`obStepHtml()`): agregar `<button type="button" class="btn gray" data-action="obSkipDiagnostic">${t('ob_diag_skip')}</button>` al `ob-cta-row`, después del botón de start. Sumar una línea chica de ayuda con `t('ob_diag_skip_hint')`.
   - Nueva función `obSkipDiagnostic()` cerca de `obStartDiagnostic()`, con la lógica de arriba (podés reusar `obAfterDiagnostic()` después de setear `diagSkipped` y limpiar `OB.awaitDiag`).
   - Registrar la acción en el mapa de acciones (`'obNext':()=>obNext(),` zona ~línea 20165): `'obSkipDiagnostic':()=>obSkipDiagnostic(),`.
   - i18n EN (~5083+) y ES (~6010+):
     - `ob_diag_skip`: `Skip for now` / `Saltear por ahora`
     - `ob_diag_skip_hint`: `You can take the 12-question check later from the Diagnostic view.` / `Podés hacer el chequeo de 12 preguntas después desde la vista Diagnostic.`
   - Actualizar el comentario del HTML del overlay (2840-2842) que hoy afirma que no hay control de skip.
2. `tests/test_onboard.py`
   - Agregar un caso corto, en contexto limpio (mismo patrón de reset que usan los otros bloques): llegar al paso 3, click en el botón de skip, y verificar con números: `step == "4/5"`, `D.diag` ausente/`null`, `D.profile.diagSkipped === true`, overlay visible y `D.onboarded === false`.
   - No cambiar los asserts existentes del flujo con diagnóstico.

## Reglas

- No tocar el servidor, el scoring del diagnóstico, gates ni la vista Diagnostic.
- No agregar dependencias. Un solo botón nuevo, estilo `btn gray` existente.
- Mobile 390×844: los dos botones del `ob-cta-row` tienen que apilarse sin desbordar; verificar captura.
- Textos en inglés y español, sin inventar promesas.

## Verificación obligatoria

```bash
cd /home/juan/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_onboard.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_diag.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
```

Los tres exit=0. Capturas del paso 3 en mobile 390×844 y desktop, con el botón de skip visible y sin overflow. Mirarlas antes de commitear.

## Cierre

Commit `feat(onboarding): permitir saltear el diagnóstico de 12 preguntas`. Árbol limpio. Sin deploy.
