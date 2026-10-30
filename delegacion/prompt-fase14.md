# PROMPT — Fase 14: sincronizar TODA la documentación con la app real

Sos technical writer senior. Repo `/home/juan/b2first-tracker`. **CODIFICAR.** Inglés en los archivos
del repo; los prompts de `delegacion/` pueden quedar como están.

## El problema

La app cambió mucho en una noche: onboarding de intake, plan que nace del perfil, interfaz en
inglés con dark mode real, multiusuario con registro abierto, límites y cuotas, tokens hasheados,
audit log, `/api/health`, backups verificados, auditoría externa. La documentación quedó atrás:
todavía describe un tracker monousuario en español.

**Regla de oro: documentá lo que el código hace hoy, verificado.** Si algo no lo podés confirmar
leyendo el código o corriendo el comando, no lo escribas.

## Archivos a revisar y actualizar

| Archivo | Qué corregir |
| --- | --- |
| `README.md` | Features reales (intake, plan desde perfil, multiusuario, export/delete, activity), stack, quick start con `B2_*`, tabla de tests completa, sección Security, screenshots si cambiaron |
| `SUBMISSION.md` | Relato del build alineado: intake, calibración del corrector con los números, seguridad y multiusuario; nada de "demo" como modo principal |
| `docs/DEVPOST-FIELDS.md` | Campos con los datos de hoy (URL pública, repo, features, "built with") |
| `docs/VIDEO-SCRIPT.md` | Guion sobre la app real: intake → plan → quick-log → corrección → cuenta |
| `IMPLEMENTACION.md` | Marcarlo como histórico: agregar arriba un bloque `> Status: historical plan (phases 0-6). Current state: see README + SECURITY.md` |
| `agents.md` | Modelo de datos con `D.profile`, `schema_version`, sección de auth/multiusuario, tests nuevos, pitfalls nuevos (proxy XFF, tokens hasheados, backup timer) |
| `delegacion/README.md` (si existe) | Cómo se corre el loop hoy, cadena de harnesses, tope de 75 min |
| `LICENSE` | Verificar año y nombre |

## Verificaciones obligatorias antes de escribir

1. `ls tests/` → la tabla de tests del README debe listar **todos** los archivos reales, con una
   línea de qué cubre cada uno. Ninguno inventado, ninguno faltante.
2. `grep -oE "B2_[A-Z_]+" -r --include=*.py . | sort -u` → la tabla de variables de entorno debe
   coincidir exactamente con las que el código lee.
3. `python3 -c "import json;print(sorted(json.load(open('data/users.json')).keys()))"` → no pegues
   datos personales; sólo mencioná la estructura.
4. `curl -s http://127.0.0.1:8088/api/config` → el estado real (`demo`, `register`, `ai`).
5. `git log --oneline | wc -l` y la lista de suites verdes: no inventes números de cobertura.

## Reglas de estilo

- Sin adjetivos de marketing. Nada de "powerful", "seamless", "revolutionary".
- Cada afirmación técnica con su número o su comando.
- Tablas cuando hay comparación; prosa corta cuando hay explicación.
- Nada de emojis en los `.md` del repo.
- Links internos relativos y válidos (`SECURITY.md`, `docs/...`).

## Prohibido

Tocar `server.py`, `index.html`, `store.py`, `tests/`. Deploy, systemd, Docker. Inventar features,
números o capturas. Escribir en español los archivos del repo (van en inglés).

## Verificación (pegá salida literal)

```bash
cd /home/juan/b2first-tracker
ls tests/ | tr '\n' ' '
grep -rhoE "B2_[A-Z_]+" --include=*.py . | sort -u | tr '\n' ' '
curl -s http://127.0.0.1:8088/api/config
for f in README.md SUBMISSION.md SECURITY.md agents.md docs/VIDEO-SCRIPT.md docs/DEVPOST-FIELDS.md; do printf "%-30s %s lineas\n" "$f" "$(wc -l < $f)"; done
grep -c "TODO\|TBD\|XXX" README.md SUBMISSION.md SECURITY.md | tr '\n' ' '
```

Commit: `docs: sync all documentation with the current application`
