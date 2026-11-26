# Fase progress-docs — Progress limpio + documentación para la hackathon

Repo: `/home/juan/b2first-tracker`, base HEAD `1951291`.

## Contexto

Mañana es la presentación en la hackathon **Build Your First AI App 2026** (Devpost, deadline 9 dic 2026). Los requisitos de submission son: descripción clara, problema que resuelve, explicación de la implementación de IA, demo, código fuente e instrucciones de setup; crédito explícito a librerías/open source/APIs/modelos preentrenados/asistentes usados. La app debe poder mostrarse sin pasos raros.

## Parte 1 — sacar “Errors by type” y ordenar Progress

1. Eliminar por completo el chart “Errors by type”: bloque HTML `charts_errors`, `#gErr`, render `errChart`/`gErr`, CSS/i18n `charts_errors`, `charts_errors_sub`, `pg_err_title`, datos asociados si quedan huérfanos. No dejar contenedores vacíos ni una columna muerta.
2. Reacomodar `#progChartsGrid` para que quede visualmente parejo:
   - “Weakest parts” a ancho completo o en dos columnas balanceadas con “Weekly consistency”; sin alturas dispares ni hueco donde estaba Errors.
   - Mejor orden visual: Evolución → Weakest parts + Consistency → Matrix. En mobile una sola columna, cards sin scroll horizontal y con margen inferior consistente.
   - Revisar spacing, títulos y subtítulos; que no queden referencias a “errors” en empty state (`pg_empty_sub`) ni en ningún copy.
3. Capturas 390 y 1280 (light/dark si el harness lo permite) y revisión visual real: sin cards cortadas, sin solapamiento del FAB, sin gráficos con alto 0.

## Parte 2 — documentación honesta y lista para hackathon

Actualizar TODO lo escrito para que describa el producto real de hoy (no promesas viejas):

- `README.md`: qué es, problema, cómo funciona la IA (writing feedback + speaking examiner turn-based, STT/TTS), stack, setup local, variables de entorno, límites/cuotas, privacidad en una línea, créditos. Sin marketing vacío ni emojis decorativos.
- `docs/README.md` y `docs/REPO-ABOUT.md`: índice y about alineados.
- `docs/PRIVACY.md`: qué se guarda (email, progreso, logs de práctica, métricas de uso), qué NO se guarda (audio crudo, transcripts de speaking), procesamiento por proveedores IA, retención, borrado de cuenta, contacto. Coherente con el código; no inventar plazos.
- `docs/TERMS.md`: uso educativo, cuentas, uso aceptable, cuotas, propiedad del contenido del usuario, materiales Cambridge con copyright y uso personal, limitación de responsabilidad, cambios.
- `docs/CONFIGURATION.md` y `docs/DATA-MAP.md`: variables y tablas/campos reales; si algo cambió, corregirlo.
- `docs/SECURITY.md` / `SECURITY-CHECKLIST.md`: solo si hay afirmaciones desactualizadas.
- Copy visible: landing, títulos/subtítulos, footer legal, meta description/OG, textos de privacidad/términos en la app. Quitar cualquier mención a features eliminadas (transcripts, errors chart, lesson plans, Azure si ya no se usa).
- Crear `docs/HACKATHON.md` con copy listo para Devpost: nombre, tagline, problema, solución, cómo usa IA, stack, demo (guion de 2–3 minutos paso a paso), qué es real vs limitado (pronunciación “No medida” sin proveedor, cuotas), créditos y links. En inglés, porque Devpost es en inglés; el resto de docs mantener el idioma que ya usan.
- No afirmar que hay funciones que no existen. Si algo es roadmap, marcarlo como roadmap.

## Verificación obligatoria

- `grep -ri "errors by type\|gErr\|charts_errors"` sin resultados.
- Tests: `test_graf.py`, `test_mobile.py`, `test_i18n.py`, `test_progress_view.py` (si existe), `test_landing_honest.py` (si existe), `test_readme_limits.py`, `test_index_handlers_exist.py`, `py_compile` de los .py tocados. Ajustar tests solo si el cambio de producto es intencional; no borrar cobertura.
- Capturas en `tests/out/progress_390_light.png` y `progress_1280_light.png`; mirarlas de verdad.
- Commit(s) claros. No deploy: lo hago yo tras verificar.

Devolver: archivos tocados, tests con exit code, capturas y cualquier claim que hayas corregido.
