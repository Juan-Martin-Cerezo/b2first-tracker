# Verificación de fidelidad contra las pantallas de Stitch

Las pantallas de referencia se descargaron del proyecto Stitch
"B2 First Coach Tracker" (ID 985211921719693127) vía el MCP
(get_screen) usando `curl -L` sobre las URLs hosteadas:

- stitch_assets/{today,exam,progress,errors,parts,plan,session,
  analytics}_stitch.png  -> screenshots de referencia
- stitch_assets/{today,exam,progress,errors,parts,plan,session,
  analytics}_stitch.html -> código HTML generado
- stitch_assets/{logo,favicon,apple_touch}_stitch.png -> assets

## Estructura replicada (verificado lado a lado con visión)

| Pantalla Stitch | Estructura replicada en index.html |
|---|---|
| TODAY | Sidebar + topbar, grid 8/4, sesión con tasks numerados + timers, ROTATION navy + WEEKLY METRICS |
| EXAM | Grid de 4 tarjetas de selección (Full navy) + timer gigante con dial |
| PROGRESS | 3 stat cards + Matriz con tabs por etapa + historial/stats 2 col |
| ERRORS | Split view: registro izq + Failure Patterns + Log Error der |
| PARTS | Header SYLLABUS_INDEX + Total Parts 15 + cards por módulo |
| PLAN | Exam Timers (FCE Format) + Thresholds navy + Session Schedules + Rotation Cycles verde |
| ANALYTICS | 3 stat cards + grid 2x2 de gráficos |
| SESSION | Tasks numerados con sub-fases y timers (integrado en HOY) |

## Resultado de la comparación visual (visión sobre side-by-side)

- TODAY: "estructuralmente muy similares"
- EXAM: "muy similares" (grid de selección + timer)
- PROGRESS: "muy similares" (tabs por etapa agregados)
- PLAN: "muy similares" (bento reordenado)

## Tests (contrato preservado)

test_final, test_rot, test_exam, test_graf, test_tracker, test_sync:
cero errores JS, sin overflow a 390px, 8 botones nav, 3 gates,
15 partes, rotación 7 opciones, timer 01:15:00.
