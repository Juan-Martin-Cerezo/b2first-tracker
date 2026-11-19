# Fase auth — el ingreso principal es con mail (Google) y la passkey queda centrada

Repo: `/home/juan/b2first-tracker`. Base: HEAD actual (puede incluir la fase owner; verificá `git log`).

Juan: "Centra y acomodá lo de sign in with passkey, que sea con mail el sign in".

Hoy en `index.html` (#authOverlay, ~2770) el login muestra primero usuario + contraseña, y abajo, ambos a ancho completo, "Continue with Google" y "Sign in with a passkey" (este último con `display:none` hasta que el navegador lo soporta). Se ve como un apéndice, no como una opción de ingreso.

## Objetivo

1. El ingreso principal del tab "Log in" es con mail, vía Google. El botón "Continue with Google" va primero, arriba del formulario, con jerarquía visual primaria (mismo `btn` que el resto, ancho completo, sin inventar estilos nuevos).
2. Debajo, separador "or", y el formulario usuario + contraseña como alternativa. La etiqueta del campo pasa a "Email or username / Mail o usuario" solo si el backend puede resolver un mail: NO se puede (no se guarda mail), así que se mantiene "User name / Usuario" y el texto de ayuda aclara que el ingreso con mail es el botón de Google.
3. "Sign in with a passkey" queda centrado, como acción secundaria: mismo look que `.auth-link` centrado (`display:block;margin:10px auto 0;text-align:center`), sin ancho completo, debajo del formulario y con una línea corta que explique qué es ("Use this device's passkey").
4. Si Google no está configurado (`googleLoginBtn` oculto), el layout no debe dejar huecos: el separador "or" se oculta junto con el botón.
5. Mobile 390×844: nada se sale, el orden visual es Google → usuario/contraseña → passkey centrada. Light y dark.

## Reglas

- Solo `index.html` y los tests de auth. No tocar `server.py`, `plans.py`, speaking, CSP ni límites.
- No cambiar el flujo WebAuthn ni las funciones `startPasskeyLogin`/`startGoogleLogin`: es orden y estilo.
- Mantener todas las cadenas i18n en inglés y español, sin texto nuevo hardcodeado fuera de los objetos `I18N`.
- Un solo `h2` en la card; no agregar imágenes ni CDNs.

## Verificación obligatoria

```bash
cd /home/b2first-tracker/tests
uv run --no-project --quiet --with playwright --with httpx python test_auth_methods.py; echo exit=$?
uv run --no-project --quiet --with playwright --with httpx python test_ui_batch2.py; echo exit=$?
```

Ambos exit=0. Capturas del overlay de login en 390×844 (light y dark) y 1280×800, mostrando el orden nuevo y la passkey centrada. Revisá que el bloque de passkey no quede pegado al borde ni con texto cortado.

## Cierre

Commit `fix(auth): ingreso principal con Google y passkey centrada como alternativa`. Sin deploy.
