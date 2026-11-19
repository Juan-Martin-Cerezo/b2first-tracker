# Fase owner-ilimitado — la cuenta owner no tiene topes diarios

Repo: `/home/juan/b2first-tracker`. Base: HEAD con la fase de rotación ya commiteada (verificá `git log`).

Juan pidió que la cuenta de Google `juan-martin-cerezo` (uid `juan-martin-cerezo`, ya seteado en `B2_OWNER_UIDS`) tenga uso ilimitado. Hoy `plans.py` le da al owner 10 writings / 1 mock / 15 min, y además los topes por instancia (`B2_AI_DAILY_TOTAL=20`, `B2_SPK_MIN_DAILY_TOTAL=25`) lo frenan igual que a un usuario común.

## Qué cambiar

1. `plans.py`, `LIMITS["owner"]`: volver a topes efectivamente infinitos (writing 1_000_000, speaking mocks/minutes 1_000_000) con un comentario que diga que el owner no se mide por día; las perillas de instancia siguen existiendo para el resto.
2. `server.py`: en los tres gates de uso, si `plans.is_owner(uid)` se saltea el contador y se responde permitido:
   - el presupuesto diario de llamadas de texto (`_ai_daily_guard`/`_ai_budget`, buscar donde se compara con `_ai_per_user_cap()` y el total de instancia),
   - el gate de Speaking por usuario (`_speaking_gate`),
   - los minutos restantes de Speaking (`_spk_remaining_s`).
   No tocar el guard mensual de Gemini (`SPK_MONTH_MINUTES`, hoy 900): es el único freno de plata real y queda activo para todos, incluido el owner. Tampoco tocar rate limits por minuto (anti-abuso) ni el límite de body.
3. Test nuevo `tests/test_owner_unlimited.py`, offline: con `B2_OWNER_UIDS=juan-martin-cerezo`, el owner puede hacer 25 llamadas de texto y abrir 3 sesiones de speaking en el mismo día sin 429, mientras una cuenta común sigue recibiendo 429 en el primer tope; y el contador mensual de Live sigue devolviendo 429 cuando se agota. Usar el patrón de stub de `tests/test_speaking_exam.py`.
4. Actualizar el test existente que assertee los límites del owner (buscá `owner` en `tests/test_speaking_exam.py`, `tests/test_plan_limit_stack.py`, `tests/test_ai_guard.py`) al contrato nuevo: owner sin tope diario, límite mensual global intacto.

## Reglas

- No cambiar los límites de `service` (5 writings/1 mock/15 min) ni los env actuales.
- No tocar documentos, landing, CSP, rotación ni prompts de IA.
- Nada de secretos en tests.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_owner_unlimited.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ai_guard.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_plan_limit_stack.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_speaking_exam.py; echo exit=$?
```

Los cuatro exit=0.

## Cierre

Commit `feat(owner): uso ilimitado para la cuenta owner, con el guard mensual intacto`. Sin deploy.
