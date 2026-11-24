# Fase fullmock-card — FULL MOCK como bloque dentro de “Real mocks”

Repo: `/home/juan/b2first-tracker`, base: HEAD vigente (después de `mock-guided`).

## Pedido del dueño

En la sección **“Real mocks”** el full mock tiene que aparecer **como un bloque más**, no como el botón verde “Start full mock” del encabezado.

## Cambios

1. **Quitar** el botón verde `u4-fullmock-btn` (“Start full mock” / “Empezar simulacro completo”) del `u4-section-head`. El encabezado queda sólo con título y subtítulo.
2. **Agregar** un bloque full mock dentro de `#examSelectGrid`, como quinto hijo y **primero en orden visual**:
   - `div.exam-card.exam-card-full` con `role="button"`, `tabindex="0"`, `data-action="startFullMock"`, `data-keydown="activate"`.
   - Kicker: “All 4 papers” / “Las 4 pruebas”.
   - Meta: “195′ + 14′ Speaking”.
   - Título: “Full mock” / “Full mock”.
   - Desc: “The official sequence: R&UoE → Writing → Listening → Speaking, one timer per paper.” / “La secuencia oficial: R&UoE → Writing → Listening → Speaking, un timer por paper.”
   - Mismo lenguaje visual que las otras 4 tarjetas (borde, hover, foco, target ≥44 px). Sin color verde de CTA: es un bloque, no un botón.
   - En desktop (`≥900px`) ocupa la fila completa (`grid-column:1/-1`) arriba de las 4 tarjetas; en mobile va primero, ancho completo.
3. Click/Enter abre el mismo flujo existente (`startFullMock()` → pre-flight + wizard guiado). Sin lógica nueva.
4. No duplicar: en “Real mocks” no queda ningún otro acceso al full mock (ni link, ni botón). El pre-flight sigue siendo el único lugar donde se elige muestra y se arranca.
5. i18n EN/ES simétrico para kicker, meta, título y descripción; keys nuevas `exam_full_card_*`. Dark/light.

## Alcance

- `index.html`, tests, capturas. Sin backend, sin límites, sin tocar el wizard, sin deploy.

## Tests

Actualizar `test_exam.py` / `test_fullmock_oneplace.py`:
1. `#examSelectGrid` contiene 5 bloques; el primero es `.exam-card-full` con texto “Full mock” y meta “195′ + 14′ Speaking”.
2. No existe `.u4-fullmock-btn` ni texto “Start full mock” en `#v-exam`.
3. Click en `.exam-card-full` abre `#fullMockPreflight` y el wizard en paso 1; Enter también.
4. El bloque mide ≥44 px de alto, no tiene overflow horizontal en 390×844, y es full-width.
5. En 1280×800 ocupa la fila completa y las 4 tarjetas quedan debajo en grilla 2×2 o 4×1 como hoy.
6. EN/ES simétrico, 0 errores de consola.

```bash
cd /home/juan/b2first-tracker/tests
for f in test_exam.py test_fullmock_oneplace.py test_mock_guided.py test_mock_start.py test_mobile.py test_i18n.py test_index_handlers_exist.py; do
  uv run --no-project --quiet --with playwright --with httpx python "$f" || echo "FAIL $f"
done
```

Capturas: `tests/out/real_mocks_full_card_390_light.png`, `real_mocks_full_card_1280_light.png`.

## Cierre

Un commit: `feat(exam): full mock como bloque dentro de Real mocks`. Sin deploy.
