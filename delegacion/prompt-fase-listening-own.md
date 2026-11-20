# Fase listening-own — material propio de Listening (subir audio o pegar la tarea)

Repo: `/home/juan/b2first-tracker`, HEAD actual (`240ac86`).

Hoy la vista de Listening (index.html ~3740) es solo registro: `#lPart` (all/1/2/3/4), `#lFuente` con cuatro fuentes fijas, `#lRef`, `#lOk`, `#lP2`, `#lMin` y "Save Listening". No hay forma de usar material propio: Juan quiere poder **subir un audio** o **pegar/escribir la tarea** de su material personal, y que cualquier usuario pueda hacerlo.

## Alcance

### 1. Fuente "My own material / Mi material"
Agregar la opción `own` a `#lFuente`. Al elegirla aparece un panel nuevo (`#lOwnPanel`) con:
- Título (texto, máx 120).
- Tipo/parte (reusa `#lPart`, no dupliques).
- Tarea escrita: textarea `#lOwnTask` para pegar preguntas y opciones, una por línea, máx 16 ítems de 300 caracteres.
- Clave de respuestas (opcional): textarea `#lOwnKey`, una respuesta por línea, en el mismo orden (A/B/C, 1-8, palabras).
- Transcripción/script (opcional): textarea `#lOwnScript`, máx 6000 caracteres. Si no hay audio, el botón "Play script" lo lee con `speechSynthesis` (voz del navegador, sin API).
- Audio: `input type=file` `#lOwnAudio`, acepta `audio/mpeg, audio/mp4, audio/wav, audio/ogg, audio/webm`, máx 20 MB. Un solo archivo por material.
- Botón "Save my material" y "Delete".
- Estado claro: guardado, borrado, error de tamaño/formato, "audio subiendo…".

### 2. Persistencia por usuario (server-side)
- Nuevo endpoint `POST /api/listening/material` (JSON, `{title, part, task, key, script, audio_b64?, mime?}`), `GET /api/listening/material` (lista con id, título, parte, tiene audio, bytes) y `DELETE /api/listening/material?id=...`.
- Guardar bajo `B2_DATA_DIR/users/<uid>/listening/<id>/` con `meta.json` y `audio.<ext>`. Nada de paths del cliente; el id lo genera el server (token aleatorio).
- Tope: 20 MB de audio por material, 10 materiales por usuario, 40 MB por usuario (429/413 con error claro).
- Servir el audio en `GET /api/listening/material/audio?id=...` con `Content-Type` correcto, autenticado por sesión y `Accept-Ranges: bytes` (soporta seek). Sin cache pública (`Cache-Control: private, no-store`).
- Validar `part` en (1,2,3,4) y sanear todo el texto (sin HTML, límites de tamaño). Sin secretos ni logs de contenido.

### 3. UI de la sesión
- Con material propio elegido: reproductor `<audio controls>` apuntando al endpoint, título, lista de preguntas numeradas y, si hay clave, botón "Check answers" que compara lo que el usuario escribió en inputs por pregunta y muestra aciertos/total (no envía nada al server).
- Al guardar la sesión con `saveL`, el `ref` usa el título del material propio y el modo sigue tomando `#lPart`. No cambiar el formato del log ni `saveL`/`switchListeningPhase`.
- Mobile 390×844: sin scroll horizontal, controles de 44px mínimo, textareas usables. Light y dark. i18n inglés/español para todas las cadenas nuevas.

### 4. Reglas
- No tocar Speaking, plan, límites, cuentas, owner, CSP ni landing. Si hace falta `media-src 'self'` ya está: verificá y si no, agregalo solo a `/app`.
- Nada de CDNs ni librerías nuevas. `python3` stdlib en el server.
- Si el navegador no soporta `speechSynthesis`, el botón "Play script" se oculta y el resto sigue funcionando.
- Los archivos subidos no se sirven si la sesión no es del dueño.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_listening_own_material.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_listening_part.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
```

Test nuevo `test_listening_own_material.py` (servidor aislado, stub de red para el audio si hace falta):
1. Pegar tarea + clave + script, guardar, recargar: el material sigue y se lista.
2. Subir un WAV chico (generado en el test, <1 s), guardar, pedir el audio por HTTP: 200, `Content-Type` de audio, bytes idénticos.
3. Borrar: desaparece de la lista y el audio devuelve 404.
4. Límites: audio >20 MB → 413; 11 materiales → 429.
5. Otro usuario no puede pedir el audio ajeno (403/404).
6. UI 390×844: panel visible, sin overflow horizontal, sin pageerrors.

## Cierre

Commit `feat(listening): material propio con audio o tarea escrita`. Sin deploy.
