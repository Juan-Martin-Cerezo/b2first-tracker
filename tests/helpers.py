"""Helper para los tests: login como owner antes de interactuar con la app.

El frontend ahora exige sesión (overlay de login). Los tests existentes
verifican la app funcional, así que se loguean como el usuario 'owner'
(creado por la migración) con la contraseña por defecto.
"""

OWNER_NAME = "Owner"
OWNER_PASS = "b2first"


def login_owner(pg, url):
    """Loguea al owner vía la API y setea la sesión en localStorage."""
    import json
    import urllib.request

    req = urllib.request.Request(
        url + "api/login",
        data=json.dumps({"name": OWNER_NAME, "password": OWNER_PASS}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        u = json.loads(r.read().decode())
    pg.evaluate(
        "localStorage.setItem('b2first_user', %s);" % json.dumps(json.dumps(u))
    )
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    # Cerrar el onboarding de primer ingreso si aparece (usuario sin D.onboarded)
    if pg.evaluate("typeof finishOnboarding==='function' && document.getElementById('onboardingOverlay') && document.getElementById('onboardingOverlay').style.display==='flex'"):
        pg.evaluate("finishOnboarding()")
        pg.wait_for_timeout(300)
