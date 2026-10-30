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
| 35 | Examen de speaking real: 4 partes, tarea en pantalla, cronómetro, 5 pantallas, examinador con guion | **corriendo** |
| 36 | Voz por turnos que sí funciona con esta key (STT + LLM + TTS, latencia medida) | en cola |
| 33 | Stripe US$5/mes: checkout, webhooks firmados, idempotencia, gracia de 3 días | en cola |
| 34 | Login con Google (OAuth + PKCE) y passkeys (WebAuthn) | en cola |

---

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

---

## D. Deuda técnica conocida (mía, no tuya)

1. **Las suites escriben en la base de producción**: `test-runner`, `i18n-suite`, `layout-suite`, `shot-*`. Deberían usar un `B2_DATA_DIR` temporal.
2. **`HANDOFF.md` dice 4 GB de RAM** — la Pi tiene 8 GB.
3. **4 fuentes de British Council** no verificables por HEAD (timeout desde la Pi).
4. **Página en 129 KB gzip** — se puede partir el material en otro request.
5. **No hay recuperación de contraseña** por email; solo `tools/reset_password.py` desde la Pi.
6. **Límite de login 10/10 min por IP** — molesto en una casa con dos dispositivos. Diferido a propósito.
7. **Full-duplex imposible** con esta key: 0 de 50 modelos con `bidiGenerateContent`.
8. **Cloudflare inyecta su beacon** de analytics; el CSP lo bloquea pero tira error en consola.

---

## E. Reglas que no se negocian

- Código, comentarios, UI y commits en inglés. Conversación en español rioplatense.
- Backend Python stdlib puro; `index.html` es un solo archivo.
- Delegación **serial**: un agente a la vez, un solo árbol de trabajo.
- No afirmar que algo funciona en producción si solo se probó contra un stub.
- Avisar antes de tocar o reiniciar cosas del sistema.
- Sin piratería: solo material oficial gratuito o comprado.
