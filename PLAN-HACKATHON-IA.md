# Plan — B2 First Tracker + IA · Hackathon "Build Your First AI App"

> Deadline: **27/11/2026 17:00 EST** (19:00 ARG). Hoy: 29/10/2026 → **29 días**.
> Evento: https://build-your-first-ai-app.devpost.com/ · ya registrado (68 participantes).
> Categoría natural: **AI Study Assistant**.

---

## 1. Tesis

No construir una app nueva. Enchufarle IA al tracker que ya usás todos los días.

El jurado pesa: implementación 30% · creatividad 25% · impacto 25% · presentación 20%.
Una app real, en uso, con tests y datos históricos reales gana a un chatbot de manual.
El 90% de los otros 67 inscriptos va a empezar de cero.

**El diferencial que nadie puede copiar**: `D.errs[]` tiene tu taxonomía de errores
(`L-GAP` / `G-ERR` / `T-MIS` / `T-LIM`) acumulada durante meses. Eso alimenta
recomendaciones que ningún competidor puede generar.

---

## 2. Alcance

### Dentro (lo que se submitea)

| # | Feature | Input | Output | Días |
|---|---|---|---|---|
| 1 | **Corrector de Writing** | texto + `kind` (essay/email/review…) | 4 bandas Cambridge (Content, Communicative Achievement, Organisation, Language) 0–5 + feedback por criterio + reescritura de 3 oraciones | 3 |
| 2 | **Diagnóstico inicial (cold start)** | 12 ítems de placement generados por IA (3 por parte) o último examen hecho | `D.log[]` + `D.errs[]` iniciales → primer plan de la semana | 2 |
| 3 | **Explicador de respuestas** (RAG) | pregunta + examen/parte | por qué B y no C, citando el texto | 3 |

> **Cambio de diseño por datos reales (29/10)**: el feature 2 original era "plan de la
> semana desde `D.errs[]`". Medido: **hay 0 errores registrados y 5 sesiones en 67 días**.
> Sin datos de entrada ese feature no tiene nada que analizar. Se reemplaza por un
> diagnóstico que **genera** los datos, que además resuelve el problema de todo usuario
> nuevo (nadie tiene historial el día 1). El plan adaptativo real llega después, cuando
> haya ≥20 sesiones registradas.

Mínimo viable para submitir: **1 + 2**. El 3 se agrega si sobra tiempo.

### Fuera (explícito)

- Speaking con IA (audio, latencia, costo) → post-submit.
- Reescribir el frontend con framework.
- Base de datos real / migrar a Postgres.
- Multiusuario serio (el tracker es tuyo; los visitantes usan modo demo).

---

## 3. Auditoría del estado actual (verificada, no supuesta)

| Componente | Realidad medida | Veredicto |
|---|---|---|
| `index.html` | **4.233 líneas**, vanilla, single-file, secciones comentadas | ok, no tocar |
| `server.py` | 671 líneas, stdlib, `ThreadingHTTPServer` | ok, no tocar |
| Auth | `users.json` + salt + `tokens.json` con TTL. Hash = SHA-256 rápido, password mín. **4 chars** | **débil para deploy público** |
| Persistencia | JSON + backups (últimos 20), last-write-wins | ok para 1 usuario |
| Tests | 6 suites Playwright | **activo: no romperlo** |
| Secrets | `.key`/`.crt` y `data/` **NO** trackeados ✅ | ok |
| Repo | `github.com/Juan-Martin-Cerezo/b2first-tracker` → **PRIVATE** | hay que publicar |

### Correcciones a lo que dije en el chat

- ❌ "no hay auth" → **falso**, hay auth propia con tokens y TTL.
- ❌ "el `.key`/`.crt` de Tailscale está commiteado" → **falso**, `.gitignore` los cubre.
- ⚠️ "arquitectura arcaica" → discutible, ver §4.

---

## 4. Decisión de arquitectura (ADR-001): no reescribir

**Contexto**: single-file vanilla + stdlib + JSON. Juan lo llama "arcaica o básica".

**Decisión**: se mantiene. Se agregan capas, no se reemplaza.

**Por qué**:

| Reescribir a Next.js/React | Costo | Beneficio en el jurado |
|---|---|---|
| Frontend nuevo | 2–3 semanas | ~0. El jurado usa la app, no audita el stack |
| Migrar tests Playwright | 3–4 días | negativo: riesgo de romper lo que funciona |
| Perder modo offline + deploy trivial | — | negativo |
| Riesgo de no llegar al deadline | alto | — |

`YAGNI`: la arquitectura minimalista **es** una decisión de diseño defendible, y es
la que hace que la app abra en el celular sin build. Un rewrite en 29 días es cómo se
pierde un hackathon y se rompe la herramienta que usás a diario.

### Lo que sí cambia (quirúrgico, 4 items)

**ADR-002 — Proxy de IA con key del cliente.**
El repo es público → cero credenciales. `POST /api/ai/writing` recibe
`{text, kind, provider_key}`; el server reenvía al proveedor y **no persiste la key**.
Se guarda en `localStorage` del visitante. Alternativa server-side por env var
(`B2_AI_KEY`) para el demo propio, documentada en el README.

**ADR-003 — Rúbrica oficial hardcodeada, no inventada.**
Las band descriptors de Cambridge van en `prompts.py` como texto fijo. El modelo
**aplica** la rúbrica, no la genera. Regla dura del proyecto: nada de datos inventados.

**ADR-004 — Hardening mínimo para deploy público.**
- `hash_password` → `hashlib.pbkdf2_hmac('sha256', …, 200_000)` (stdlib, sin deps).
- Password mínimo 8 chars.
- Rate limit en memoria por IP: 10 req/min a `/api/ai/*`.
- `data/` fuera del deploy: en Render free el disco es efímero → los visitantes
  usan sólo `localStorage` (modo demo), el dueño usa la Pi.

**ADR-005 — Timeout y degradación.**
Timeout duro 25s al proveedor, error visible en la UI ("el corrector tardó, reintentá").
Sin streaming en v1: un Writing de 200 palabras tarda 6–10s y entra cómodo.

**ADR-006 — Seam de almacenamiento: JSON hoy, SQLite cuando haya usuarios reales.**

Objetivo declarado: que esto lo use **mucha gente**, no sólo Juan. Eso no se logra con
un framework, se logra separando el almacenamiento de los endpoints.

- Hoy: `data/users/<uid>/progress.json` (todo el estado en un blob por usuario).
- Seam: concentrar TODO acceso a datos en `store.py` con 6 funciones
  (`get_user`, `create_user`, `get_progress`, `put_progress`, `list_users`, `backup`).
- Después del hackathon: `store_sqlite.py` con las mismas 6 funciones usando
  **`sqlite3` de la stdlib** (`WAL`, una fila por sesión + una fila por error).
  Cero dependencias nuevas, mismo contrato de API, el frontend no se toca.

Por qué SQLite y no Postgres: es stdlib, no hay servidor que administrar, y aguanta
cientos de usuarios sin transpirar. Postgres entra recién si hay concurrencia real
o multi-instancia — y para entonces el seam ya está hecho y el swap es de un archivo.

---

## 5. Proveedor de IA

Criterios: free tier usable, latencia baja, buena escritura en inglés (corrige Writing
en inglés, explica en español rioplatense).

| Opción | Free tier | Nota |
|---|---|---|
| **Gemini 2.x Flash** (recomendado) | sí, generoso | rápido, buen JSON mode |
| Groq (Llama 3.x) | sí | el más rápido; JSON mode menos confiable |
| DeepSeek | bajo | el que ya usás en Hermes |
| Ollama local | ∞ | no sirve para el demo público (la Pi no expone 11434) |

Default: **Gemini Flash**, con `provider` conmutable en `D.settings` para que el
usuario final elija.

Formato de respuesta: JSON estricto, validado en el server contra un schema fijo
(las 4 categorías + rango 0–5). Si el modelo devuelve algo raro → 422, nunca
renderizar datos sin validar.

---

## 6. Roadmap con fechas

### Semana 1 — 29/10 → 04/11 · Núcleo IA
- [ ] `prompts.py`: rúbrica Cambridge + prompt del corrector + prompt del plan
- [ ] `POST /api/ai/writing` (proxy, timeout, validación de schema)
- [ ] `POST /api/ai/plan`
- [ ] Tab **IA** en `index.html`: textarea, selector de `kind`, botón, tarjetas de banda
- [ ] Campo "API key" en pestaña PLAN → `D.settings.aiKey`
- **Demo posible al final de la semana.**

### Semana 2 — 05/11 → 11/11 · Cerrar el círculo
- [ ] El plan generado se puede **guardar como sesión** → escribe en `D.log[]`
- [ ] Las bandas del Writing quedan en `D.log[]` con `kb/kc/ko/kl` → alimentan GATES
- [ ] Tests nuevos: `test_ai.py` (mock del proveedor, sin red)
- [ ] Botón "analizar mis últimos 20 errores" conectado a la tab ERRORES
- **Acá el producto se vuelve adictivo: escribir → corregir → plan → practicar.**

### Semana 3 — 12/11 → 18/11 · Publicar
- [ ] Repo público: `README.md` en inglés (cara al jurado), el actual pasa a `README.es.md`
- [ ] `Dockerfile` + deploy en Render free (o Fly.io)
- [ ] Modo demo: sin login, progreso en `localStorage`, banner "demo — tu progreso es local"
- [ ] Verificar que `data/` no se suba y que el deploy arranque en frío <30s
- [ ] Landing del repo: screenshot + GIF de 10s

### Semana 4 — 19/11 → 25/11 · Submission
- [ ] Video 90–120s: problema → corrector en vivo → plan generado → gráficos
- [ ] Formulario Devpost completo (§7)
- [ ] Ensayo general: abrir el deploy en un navegador limpio, sin sesión, y hacer el flujo entero
- **Submitir el 25/11, no el 27.**

### Buffer — 26/11 → 27/11
Sólo fixes. Nada nuevo.

---

## 7. Checklist de submission (Devpost)

- [ ] Título — propuesta: **"B2 First Coach — AI examiner for Cambridge Writing"**
- [ ] Descripción corta (1 línea) y larga (problema → solución → beneficiario)
- [ ] Prototipo funcional → URL del deploy
- [ ] Explicación de la IA: modelo, prompt, por qué rúbrica fija, validación de schema
- [ ] Repo público con licencia (MIT)
- [ ] Video + screenshots
- [ ] README con setup, features, stack, límites conocidos
- [ ] Declaración de contribución: qué hice yo, qué tools IA usé (Hermes/Claude Code)
- [ ] Cero credenciales, cero datos personales en el repo

**Riesgo de elegibilidad**: la regla 1 pide mayoría de edad (18 en AR). Registrado con
17 → inelegible de papeles. El submit va igual; el premio es un certificado y el valor
real es el portfolio. Decisión tomada, no se vuelve a discutir.

---

## 8. Riesgos

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| El corrector tarda >15s y arruina el demo | media | timeout 25s + "analizar 2 párrafos" en el video |
| El modelo inventa bandas incoherentes | media | schema validation + rúbrica fija + temperature 0.2 |
| Render free duerme y el juez ve error | alta | ping cada 10 min (cron) o Fly.io sin sleep |
| Rewrite del frontend se come el mes | si se intenta | **prohibido por ADR-001** |
| Deploy público expone progreso real | baja | `data/` gitignored + modo demo anónimo |

---

## 9. Definición de terminado

- 3 features andando en el deploy público
- `test_ai.py` verde + las 6 suites viejas verdes
- README en inglés con screenshots
- Video subido
- Submission enviada el 25/11

---

## 10. Utilidad real: el diagnóstico incómodo (medido, 29/10)

Leí `data/users/owner/progress.json` y los backups:

| Métrica | Valor real |
|---|---|
| Sesiones registradas | **5** |
| Rango de fechas | 21/08 → 26/10 (**67 días**) |
| Errores registrados | **0** |
| `stage` | 0 |
| Tipos practicados | `ue` ×3, `l` ×1, `lp` ×1 · **0 Writing, 0 Speaking** |
| Backups | 1 (21/08) |

Traducción: el tracker está construido y no se usa. **5 sesiones en dos meses, cero
Writing, cero errores registrados.** El First no se aprueba con features nuevas; se
aprueba con sesiones. Y Writing es el 25% de la nota y lo único que no practicaste nunca.

Consecuencias de diseño (esto es lo que hace el producto útil de verdad):

1. **El cuello de botella es el registro, no la inteligencia.** Si anotar una sesión
   cuesta más de 15 segundos desde el celular, no se anota. Prioridad: un tap para
   "hice este ejercicio, este puntaje" y que el resto lo infiera la IA.
2. **El corrector de Writing es el feature de mayor impacto personal**, porque ataca
   la parte que hoy tiene 0 sesiones y necesita feedback que no podés darte solo.
3. **El diagnóstico cold-start es obligatorio**, no un extra: sin historial, ni vos ni
   ningún usuario nuevo tienen de dónde arrancar.
4. **Nadie adopta una app que no le devuelve algo en la primera visita.** Para "mucha
   gente": entrar → diagnóstico de 15 min → plan concreto. Eso es el onboarding.

### Regla de oro para el proyecto

> Cada feature nueva se juzga por una sola pregunta: **¿aumenta la cantidad de sesiones
> registradas por semana?** Si no, es decoración.

Métrica objetivo: **≥5 sesiones/semana durante 8 semanas** (40 sesiones antes del
examen). El dashboard ya tiene los gráficos para mostrarlo; falta que haya datos.

---

## 11. Horizonte B: producto para mucha gente (post-submit)

No entra en los 29 días, queda anotado con su ruta:

| Etapa | Qué | Costo | Cuándo |
|---|---|---|---|
| B1 | `store.py` (seam) + `store_sqlite.py` | 2 días | dic 2026 |
| B2 | Onboarding con diagnóstico IA + plan inicial | ya hecho en Semana 1 | — |
| B3 | Material por usuario (hoy escanea `~/Descargas/b2-first/` de la Pi) → upload propio | 3 días | dic 2026 |
| B4 | Deploy con volumen persistente + dominio | 1 día | dic 2026 |
| B5 | Límite de uso de IA por usuario (free tier) o key propia | 1 día | ene 2027 |

El escaneo de `~/Descargas/b2-first/` es el acoplamiento más fuerte a la Pi: **eso** es
lo que impide que lo use otra persona hoy. Es el primer trabajo de B.
