# Fase presupuesto-2 — topes de IA con margen (edición mínima)

Repo: `/home/juan/b2first-tracker`. Base: HEAD `eae76d8`.

Cambio acotado en `plans.py` únicamente. El presupuesto real es USD 2.18 prepagos en DeepSeek (gasto único, sin recarga) y USD 10/mes de Gemini. Los costos medidos son: writing USD 0.0011-0.0022, minuto de Live USD 0.0088, mock de 14 min USD 0.123.

## Qué cambiar

En `plans.py`:
- `DAY_WRITING_LIMIT = 5`
- `DAY_SPEAKING_MOCKS = 1`
- `DAY_SPEAKING_MINUTES = 15`
- En `LIMITS["owner"]`: `writing` limit 10; `speaking` mocks 1 y minutes 15. `pronunciation` queda `"full"`.
- Actualizar los comentarios que dicen que los límites son "generous on purpose" y que el owner no tiene caps: reemplazar por el presupuesto y los costos por unidad de arriba.

No tocar nada más: ni lógica del medidor, ni `server.py`, ni `index.html`, ni env, ni `data/usage.json`.

## Verificación (liviana, sin Playwright)

```bash
cd /home/b2first-tracker
python3 -c "import plans; print(plans.DAY_WRITING_LIMIT, plans.DAY_SPEAKING_MOCKS, plans.DAY_SPEAKING_MINUTES, plans.LIMITS['owner'])"
python3 -m py_compile plans.py
cd tests && uv run --no-project --quiet --with httpx python test_plan_limit_stack.py; echo exit=$?
```

El print debe dar `5 1 15` y el owner con 10/1/15. `test_plan_limit_stack.py` exit=0. No corras test_ui_batch2 ni test_ai_guard en esta fase.

## Cierre

Commit `chore(limits): topes de IA con margen para el presupuesto`. Árbol limpio. Sin deploy.
