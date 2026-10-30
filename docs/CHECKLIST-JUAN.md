# Lo que falta y solo puede hacer Juan

Estado: 2026-10-30. Todo lo demás (código, hardening, tests, deploy) está hecho.
Ordenado por **cuánto desbloquea**, no por dificultad.

Regla: **ninguna key se pasa por chat**. Van en archivos con `chmod 600`.

---

## 1. Cloudflare (desbloquea latencia, 5 min)

| Qué | Dónde | Costo | Nota |
| --- | --- | --- | --- |
| Cuenta Cloudflare | dash.cloudflare.com | gratis | email + verificar |
| Dominio | Name.com / Cloudflare Registrar | `.app` US$0 el 1er año (verificar) | requiere tarjeta aunque sea $0 |
| Nameservers | panel del registrador | — | Cloudflare te da 2, se pegan ahí |
| `cloudflared tunnel login` | **en la Pi** | — | abre una URL, la abrís en la compu, elegís la zona |

```bash
# en la Pi, después de tener el dominio en Cloudflare:
cloudflared tunnel login
DOMAIN=firsttracker.app bash ~/b2first-tracker/cloudflare/setup.sh
```

Avisame cuando esté el `cert.pem` en `~/.cloudflared/` y corro el resto.
**No compres** el dominio con "b2 first" adentro: marca de Cambridge.

## 2. Voz real del examinador (desbloquea el speaking, 3 min)

| Qué | Dónde | Costo | Requisito |
| --- | --- | --- | --- |
| Gemini API key (Live API) | aistudio.google.com/apikey | free tier | cuenta Google |

```bash
install -d -m 700 ~/.config/b2first
cat > ~/.config/b2first/speech.env <<'EOF'
B2_SPK_GOOGLE_KEY=PEGAR_ACA
EOF
chmod 600 ~/.config/b2first/speech.env
```

Free tier de Gemini **entrena con tus datos**. Para usuarios reales hay que
activar billing (tarjeta).

## 3. Pronunciación por fonema (opcional, bloqueado por edad)

Azure Pronunciation Assessment es el único que da score por fonema.
Necesita **cuenta Azure + tarjeta + 18 años**. Free tier F0 = 5 h/mes
(≈21 mocks **compartidos entre todos los usuarios**).

Opciones, elegí una:
- **A** — un adulto (familiar) pone la cuenta y la tarjeta. Vos usás la key.
- **B** — se queda en `null` y la UI dice "not measured" (honesto, ya funciona así).
- **C** — proveedor alternativo pago (Speechace). Mismo problema de tarjeta.

Sin esto, Pronunciation y el reporte de 4 escalas quedan incompletos, pero
**nada se rompe**: el test anti-alucinación ya verifica que el LLM no invente
la banda.

## 4. Submit del hackathon (bloqueado por edad + falta un dato)

| Qué | Detalle |
| --- | --- |
| **Cuál hackathon y fecha límite** | **no lo sé — decímelo y te digo los requisitos exactos** |
| Cuenta Devpost | pide **18+** → cuenta de adulto |
| Video demo | 2–3 min, grabación de pantalla + voz |
| Repo público | ¿lo hago público o queda privado con demo URL? |
| README + licencia | lo armo yo, necesito que decidas la licencia (MIT?) |

## 5. Decisiones que no puedo tomar yo (sin comprar nada)

1. **Nombre final** del producto y del dominio.
2. **¿Cobrar o no?** Si sí: Stripe/MercadoPago piden 18+ y CUIT/CUIL.
   Los números que propuse: Free 1 mock/día · US$3 = 12 mocks · US$7 = 25/mes.
3. **Email público** para `security.txt` y la política de privacidad
   (¿`support@` de Zoho o uno nuevo del dominio?).
4. **Nombre legal del responsable** de los datos (vos sos menor: va un adulto).
5. **Idioma**: la UI está en inglés. ¿Se queda así?

## 6. Pruebas que solo vos podés hacer (10 min, cero costo)

- [ ] Abrir la app **en el celular, con datos móviles, fuera de casa** y decirme
      cuánto tarda en quedar usable. Es el único número que no puedo medir.
- [ ] **iPhone/Safari**: darle al micrófono en el Speaking. `AudioWorklet` +
      `getUserMedia` es el riesgo técnico más grande que queda sin probar.
- [ ] Escuchar al examinador con la key de Gemini puesta y decirme si suena
      natural o robótico (nadie escuchó las voces reales todavía: todo corrió en `sim`).

## 7. Opcionales que suman (no bloquean nada)

| Qué | Para qué | Costo |
| --- | --- | --- |
| UptimeRobot / BetterStack | alerta si la app se cae | gratis |
| Resend / Zoho SMTP + registros DNS | recuperar contraseña por email (hoy es solo local) | gratis |
| rclone a Drive | backup fuera de la Pi (hoy hay backups, pero en el mismo disco) | gratis |
| Cuenta de adulto para Azure | ver punto 3 | tarjeta |

---

## Lo que NO me tenés que conseguir

OpenAI, ElevenLabs, Twilio, Firebase, Vercel, Supabase, MongoDB, Redis.
El backend es stdlib puro a propósito y las voces van por Gemini Live directo
desde el browser. Sumar cualquiera de esas es deuda, no feature.

## Camino mínimo (si querés hacer lo menos posible)

1. Gemini key → 3 min, gratis, sin tarjeta. **Desbloquea el speaking entero.**
2. Cuenta Cloudflare + dominio → 5 min, tarjeta, $0. **Desbloquea 14x de latencia.**
3. Decirme la fecha del hackathon y si hay un adulto disponible para Devpost/Azure.

Con esas tres cosas el producto queda demostrable de punta a punta.
