# Fase presupuesto — bajar límites de IA a lo que pagan las cuentas

Repo: `/home/juan/b2first-tracker`. Base: HEAD `92bfc4e`.

Juan tiene USD 2.18 de saldo prepago en DeepSeek (gasto único) y USD 10/mes de Gemini pagados por GCP. Los topes de hoy (200 writings/día por usuario, 12 mocks/día, 60 min/día, dueño sin tope) pueden quemar ~USD 198/mes. Hay que ajustarlos para que el gasto quepa en ese presupuesto.

Costos medidos con precios oficiales de hoy:
- Writing (una evaluación, prompt 10.291 chars + salida ~1.2k tokens) en DeepSeek Flash: USD 0.0011 off-peak, 0.0022 peak.
- Report de Speaking / línea de partner: USD 0.0008 / 0.0003.
- Minuto de Gemini Live: USD 0.0088 (audio in 0.005 + audio out 0.018 prorrateado).
- Mock completo de 14 min: USD 0.123 en Live, 0.047 por turnos.

## Números objetivo

Por usuario (service, todos iguales):
- writings: 10 por día (hoy 200)
- mocks de speaking: 1 por día (hoy 12)
- minutos de speaking: 20 por día (hoy 60)

Owner: 20 writings, 1 mock y 20 minutos por día (hoy 1.000.000 en todo).

Instancia (env, lo aplica el orquestador, no está en este archivo): 40 llamadas de texto/día y 30 minutos de speaking/día → ~USD 1.9/mes de DeepSeek y ~USD 7.9/mes de Gemini.

## Qué cambiar

`plans.py`:
- `DAY_WRITING_LIMIT = 10`
- `DAY_SPEAKING_MOCKS = 1`
- `DAY_SPEAKING_MINUTES = 20`
- Bloque `LIMITS["owner"]`: `writing` limit 20, `speaking` mocks 1 / minutes 20. Dejar `pronunciation: "full"`.
- Actualizar los comentarios que dicen que los números son "generous on purpose" y el del owner sin caps, explicando el presupuesto (USD 2.18 DeepSeek de una sola vez, USD 10/mes Gemini) y los costos por unidad.

No tocar la lógica del medidor, ni el formato de `usage.json`, ni las ventanas de reset.

## Reglas

- No cambiar `server.py`, `index.html` ni env vars.
- No tocar las cuentas existentes en `data/usage.json`.
- Los tests que siembran límites por env deben seguir pasando: no hardcodear nada fuera de `plans.py`.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_plan_limit_stack.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ai_guard.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_partner_limit.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
```

Los cuatro exit=0. Si algún test espera 12 mocks o 60 minutos hardcodeados, actualizalo al número nuevo en el mismo commit (nunca borres el assert).

Reportá el gasto teórico diario resultante con la cuenta hecha (llamadas × costo unitario), no una opinión.

## Cierre

Commit `chore(limits): ajustar topes de IA al presupuesto real`. Árbol limpio. Sin deploy.
