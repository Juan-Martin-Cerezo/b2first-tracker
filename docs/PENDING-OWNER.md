# Todo lo pendiente — estado real al 2026-10-30

Este archivo es la memoria del proyecto. Si algo no está acá, no existe.
Cada línea se verifica contra el repo, la cola o el servicio antes de decir "listo".

---

## A. Hecho y verificado (no hace falta volver a pedirlo)

| Pedido | Verificación |
| --- | --- |
| Dominio propio con Cloudflare | `https://firsttracker.app` 200 en 114 ms · Funnel de Tailscale apagado |
| Tres planes: free / clave propia / pago | `/api/plan` responde `free`, `byo`, `pro`, `owner` |
| Códigos de activación para pro | `tools/issue_license.py pro 30` → canje OK, un solo uso, se guarda solo el hash |
| Cuenta owner sin límites | `plan: owner`, límites 1.000.000 |
| Clave propia del usuario (BYO) | key centinela: 0 apariciones en `data/`, journal y respuestas; SSRF bloqueado (400) |
| Conteo de palabras del writing | 39 palabras + 5 guiones → 422; 40 → 200 |
| Privacidad, términos, seguridad | `/privacy` `/terms` `/security` 200 con versión y fecha |
| Logs sin PII | `ip=a4e973df3752` (hash de 12 chars, no la IP) |
| Retención de datos | `tools/retention.py` idempotente, borró 2 backups viejos |
| Seguridad de la app | `tools/audit.sh` 39/39 |
| Seguridad del host | `tools/audit-host.sh` 55/55 · 8088 cerrado a internet |
| Login seguro (password) | PBKDF2 600k, tokens hasheados, bloqueo 15 min, auditoría encadenada |
| 26 fuentes de práctica | 22/26 responden a HEAD, sin dominios de piratería |
| Idiomas EN/ES | 458 claves en paridad; 14 textos sin traducir → **verificar con `tools/scan_texts.py`** |
| Socket del examinador | `responseModalities` dentro de `generationConfig` (antes: 1007 y cierre) |
| Barge-in que cortaba palabras | umbral 300 → 600 ms |

---

## B. En curso y en cola

| Fase | Qué hace | Estado |
| --- | --- | --- |
| 34 | Login con Google (OAuth + PKCE) y passkeys (WebAuthn) | **hecho**: botón visible, Google acepta el redirect, 51 checks de passkeys |
| 35 | Examen de speaking real: 4 partes, cronómetro, examinador con guion | **hecho** |
| 36 | Voz por turnos (STT + LLM + TTS) como respaldo del Live | **hecho** |
| 38 | Examen en vivo con examinador + compañero simultáneos | **hecho** |
| 33 | Stripe US$5/mes | **revertida**: Stripe exige 18+, ver C.2 |

Nada corriendo en este momento. La cola está vacía.

## C. Bloqueado en vos (nadie más puede hacerlo)

| # | Qué | Por qué | Cómo |
| --- | --- | --- | --- |
| 1 | Nombre y deadline del hackathon | sin eso no hay README, descripción ni guion de video | pasame el link |
| 2 | Cuenta adulta de Stripe | tenés 16; Stripe exige 18 y cuenta bancaria | padre/madre/tutor abre la cuenta |
| 3 | Cambiar la password de owner | `[redacted]` quedó escrita en este chat | Settings → Account |
| 4 | Rotar la key de Gemini | también quedó en el chat | AI Studio → Delete → Create |
| 5 | Apagar Web Analytics en Cloudflare | contradice la política que publicamos | Dashboard → Web Analytics → Disable |
| 6 | Tres pruebas de celular | solo vos tenés los dispositivos | datos móviles, iPhone/Safari con micrófono, escuchar voces |
| 7 | Azure Speech (opcional) | pronunciación por fonema; rechaza tarjetas prepagas | adulto + tarjeta |
| 8 | Precio y límites de pro | hoy US$5 con 60 writing + 6 mocks; costo ~US$2,10 | confirmá o cambiá |
| 9 | Rotar el **Google Client Secret** | lo pegaste en el chat | Cloud Console → Credentials → reset |
| 10 | Probar el examinador con tu voz | el micrófono falso no tiene eco; tu oído es la única prueba | abrir Live examiner con auriculares |

---

## D. Deuda técnica conocida (mía, no tuya)

1. **Las suites escriben en la base de producción**: `test-runner`, `i18n-suite`, `layout-suite`, `shot-*`. Deberían usar un `B2_DATA_DIR` temporal.
2. **`HANDOFF.md` dice 4 GB de RAM** — la Pi tiene 8 GB.
3. **4 fuentes de British Council** no verificables por HEAD (timeout desde la Pi).
4. **Página en 129 KB gzip** — se puede partir el material en otro request.
5. **No hay recuperación de contraseña** por email; solo `tools/reset_password.py` desde la Pi.
6. **Límite de login 10/10 min por IP** — molesto en una casa con dos dispositivos. Diferido a propósito.
7. ~~**Full-duplex imposible**~~ — corregido: `gemini-3.8-live` lo soporta; el "0 de 50" era la primera página del catálogo paginado.
8. **Cloudflare inyecta su beacon** de analytics; el CSP lo bloquea pero tira error en consola.

---

## E. Reglas que no se negocian

- Código, comentarios, UI y commits en inglés. Conversación en español rioplatense.
- Backend Python stdlib puro; `index.html` es un solo archivo.
- Delegación **serial**: un agente a la vez, un solo árbol de trabajo.
- No afirmar que algo funciona en producción si solo se probó contra un stub.
- Avisar antes de tocar o reiniciar cosas del sistema.
- Sin piratería: solo material oficial gratuito o comprado.

---

## F. Actualización 2026-10-31 — speaking en tiempo real

Resuelto:

- **El Live API sí funciona con esta key.** Google manda la voz del examinador como
  **frames binarios** (PCM 24 kHz), no como base64 dentro de JSON. El cliente solo leía
  strings y descartaba el audio: por eso el examinador "no hablaba" aunque Google
  generaba 7,6 s de voz. `spkPlayPcm16()` los reproduce.
- **El sondeo de capacidades mentía.** Consultaba `/models` paginado (50 por página) y
  `gemini-3.8-live` no estaba en la primera página → `live:false`. Ahora consulta
  `/models/<modelo>` directo. `live:true` habilitado con `zz-live.conf`.
- **Un mock por examen, no por voz.** Examinador y partner mandan el mismo `session_id`;
  antes el partner quemaba un segundo mock y un plan free daba 429.
- **El examinador ya no repite la línea dos veces** (texto + fallback del navegador).
- Suites verdes: `test_speaking_exam`, `test_speaking_live`, `test_speaking_duo`,
  `test_speaking_metrics`, `test_final`.

Pendiente del owner:

- **Client ID + secret de Google** en `~/.config/b2first/oauth.env` (el drop-in ya lo lee
  si existe). Sin eso `/api/auth/google/start` devuelve 503 y el botón no aparece.
- **Probar el Live examiner con voz real** y decir si contesta a lo dicho o repite el guion.

---

## G. Actualización 2026-10-31 (tarde) — speaking, dinero y publicación

Resuelto y medido:

- **El "ruido" del examinador** eran frames JSON leídos como PCM. Se decodifica UTF-8 primero.
- **"Repite la misma frase"**: la transcripción llega troceada (a veces acumulativa, a veces delta)
  y el panel imprimía cada trozo. Ahora se fusiona y la fila se reescribe en el sitio.
- **Se cortaba a mitad de palabra**: el micrófono no tenía cancelación de eco, así que el VAD
  oía al parlante y lo interrumpía. AEC activo.
- **"Good morning" en loop**: cada barge-in mandaba `audioStreamEnd`, o sea "el candidato
  terminó" → el modelo volvía a saludar. Ya no se manda; solo se corta el audio local.
- **Barge-in sin retorno**: la pausa se liberaba esperando 300 ms de silencio del micrófono;
  en un cuarto ruidoso nunca llegaba y el examinador quedaba mudo. Ahora expira a los 2 s.
- **Tope de gasto**: Google no tiene tope duro por dólares. Presupuesto propio en el servidor
  (`B2_SPK_MONTHLY_MINUTES`, 900 min = US$6,30) + 15 min por sesión en el navegador.
  Medición real: **US$0,0070 por minuto**, examen de 12 min ≈ US$0,08.
- **La cuenta ya está en tier pago**: 15 peticiones en 2,9 s sin un solo 429.
- **Registro público abierto**: cuenta creada y borrada de punta a punta contra el dominio.
- **Watchdog** cada 15 min avisa por Telegram si `firsttracker.app` deja de responder.
- **Fuera la opción "guardar mi email como hash"**: era una decisión técnica puesta sobre el
  estudiante. El hash no se guarda nunca, sin preguntar.

Suites verdes hoy: `test_speaking_exam`, `test_speaking_live`, `test_speaking_duo`,
`test_speaking_metrics`, `test_final`, `test_legal`, `test_i18n`, `test_auth_methods`.
