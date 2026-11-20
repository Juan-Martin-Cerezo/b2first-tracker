# Fase writing-progress — el corrector tiene que mostrarse trabajando

Repo: `/home/juan/b2first-tracker`, HEAD `63fbfac` (o el actual con la fase today-compact).

## Problema

Cuando el usuario toca "Correct it" en el corrector de Writing (`#iaLoading`, index.html ~5424) solo aparece un skeleton con el texto "correcting…". No hay señal de avance, no hay tiempo, y el usuario no sabe si la app se colgó. Juan quiere una barra de progreso o algo equivalente que lo haga quedarse esperando.

## Diseño pedido

En `#iaLoading` (mantener el skeleton, no reemplazarlo):

1. **Barra de progreso** (`role="progressbar"`, `aria-valuemin=0`, `aria-valuemax=100`, `aria-valuenow` actualizado) debajo del skeleton. Animación suave (transition 300–400 ms). Sube rápido a ~35% en los primeros 3 s, ~60% a los 8 s, ~80% a los 15 s y se estanca en 92% hasta que llega la respuesta. Nunca llega sola a 100.
2. **Pasos con estado**, en una lista corta:
   - "Reading your text" / "Leyendo tu texto" (0–3 s)
   - "Checking the task and content points" / "Revisando la consigna y los puntos" (3–8 s)
   - "Scoring each band" / "Puntuando cada criterio" (8–15 s)
   - "Writing the feedback" / "Escribiendo el feedback" (15 s+)
   El paso activo se marca como tal (`aria-current="step"`), los anteriores con ✓. Si la respuesta llega antes, los pasos restantes no se muestran como completados falsos: al terminar se oculta el panel.
3. **Tiempo transcurrido** visible junto a la barra: "0:07" actualizado cada segundo, en `prefers-reduced-motion` sin animación de barra (solo valor estático).
4. **Mensaje tranquilizador** después de 20 s: "Long texts can take up to a minute — your draft is safe." / "Los textos largos pueden tardar hasta un minuto — tu borrador está a salvo." y a los 45 s: "Still working…" / "Sigue trabajando…". El botón "Correct it" queda deshabilitado y con `aria-busy="true"` mientras corre.
5. Al terminar (resultado o error) el panel se oculta con `display:none` y se libera el botón. Nada de barras que queden visibles.

## Reglas

- Solo `index.html` (markup, CSS interno, JS del estado de carga) y el test. No tocar el endpoint de corrección, prompts, límites, plan, listening, cuentas, CSP ni landing.
- Sin handlers inline: usar `data-action`/`data-input` como el resto.
- i18n EN/ES simétrico. Light y dark, 390×844 sin overflow, contraste AA.
- Respetar `prefers-reduced-motion` para la animación de la barra.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_writing_progress.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_index_handlers_exist.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_i18n.py; echo exit=$?
```

Nuevo `tests/test_writing_progress.py` (stub de red que demora ~6 s en responder):
1. Al enviar, `#iaLoading` visible, `progressbar` presente y `aria-valuenow` crece entre dos muestras separadas 2 s.
2. Los pasos aparecen en orden y el activo tiene `aria-current="step"`.
3. El contador de tiempo avanza.
4. Al llegar la respuesta, `#iaLoading` se oculta y el botón vuelve a estar habilitado.
5. 390×844: sin overflow horizontal y EN/ES con los mismos textos.

Captura: `tests/out/writing_progress_390_light.png` a mitad de carga.

## Cierre

Commit `feat(writing): barra de progreso y pasos en el corrector`. Sin deploy.
