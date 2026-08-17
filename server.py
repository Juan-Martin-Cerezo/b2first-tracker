#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B2 First study portal — sirve el tracker + material (PDF/audio) desde la Pi.

Acceso: http://100.112.213.66:8088 (Tailscale) o http://127.0.0.1:8088 (local).
Escanea ~/Descargas/b2-first dinámicamente: cualquier PDF/MP3/ZIP que
agregues a esa carpeta aparece solo en /libros (catálogo con buscador)
y en /libros.json (que consume la pestaña LIBROS del tracker).

Endpoints:
  GET /            → index.html (el tracker single-file)
  GET /libros      → página HTML con todo el material (visor + audios)
  GET /libros.json → JSON con el catálogo (para el tracker)
  GET /files/<rel> → sirve un archivo del material con soporte Range
                     (necesario para que el audio se pueda re-buscar)
  GET /favicon.ico → 204 (no existe, no loguear 404)

Dependencias: SOLO stdlib (http.server, os, re, html, mimetypes).
Deploy: systemd unit b2first.service (Restart=always) en este dir.
"""
import os, re, html, mimetypes
from urllib.parse import quote, unquote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ROOT    = os.path.expanduser("~/Descargas/b2-first")  # material (PDF/MP3/ZIP)
TRACKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
PORT    = 8088                                        # 8080 lo ocupa docker-proxy
EXTS    = {".pdf": "PDF", ".mp3": "AUDIO", ".zip": "ZIP"}


# ---------------------------------------------------------------------------
# Catálogo de archivos
# ---------------------------------------------------------------------------
def scan():
    """Recorre ROOT y devuelve la lista de archivos {rel, name, ext, size, folder}.

    rel = ruta relativa (para /files/), folder = carpeta padre (para agrupar).
    """
    items = []
    for dirpath, _dirs, filenames in os.walk(ROOT):
        for fn in sorted(filenames):
            ext = os.path.splitext(fn)[1].lower()
            if ext in EXTS:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT)
                items.append({
                    "rel": rel,
                    "name": fn,
                    "ext": EXTS[ext],
                    "size": os.path.getsize(full),
                    "folder": os.path.dirname(rel) or "Material",
                })
    return items


def fmt_size(n):
    """Formatea bytes → '1.2 MB' legible."""
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.0f} TB"


def esc(s):
    """Escape HTML (evita inyección por nombres de archivo raros)."""
    return html.escape(str(s))


# ---------------------------------------------------------------------------
# Página /libros (material con visor + audios + buscador)
# ---------------------------------------------------------------------------
def portal():
    """Genera la página HTML del material agrupada por carpeta."""
    items = scan()
    # Agrupar por carpeta conservando el orden natural de las carpetas.
    groups = {}
    for it in items:
        groups.setdefault(it["folder"], []).append(it)
    order = ["Material", "sample1", "sample2", "for-schools-1", "for-schools-2"]
    def key(f):
        return order.index(f) if f in order else 99

    blocks = []
    for folder in sorted(groups, key=key):
        cards = ""
        for it in groups[folder]:
            href = "/files/" + quote(it["rel"])  # quote → espacios/acentos OK
            if it["ext"] == "AUDIO":
                cards += f'''<div class="card audio">
                  <div class="top"><span class="ico">🎧</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <audio controls preload="none" src="{href}"></audio>
                  <a class="dl" href="{href}" download>Descargar</a></div>'''
            elif it["ext"] == "PDF":
                cards += f'''<div class="card">
                  <div class="top"><span class="ico">📄</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <div class="acts"><a class="btn" href="{href}" target="_blank">Abrir PDF</a><a class="dl" href="{href}" download>Descargar</a></div></div>'''
            else:  # ZIP
                cards += f'''<div class="card">
                  <div class="top"><span class="ico">🗜️</span><div><b>{esc(it["name"])}</b><span class="meta">{it["folder"]} · {fmt_size(it["size"])}</span></div></div>
                  <a class="btn" href="{href}" download>Descargar ZIP</a></div>'''
        blocks.append(f'<h3 class="folder">{esc(folder)}</h3><div class="grid">{cards}</div>')

    total = sum(1 for _ in items)
    # Página completa con estilos dark (mismo look que el tracker) + buscador
    # en vivo que oculta tarjetas y carpetas vacías.
    return f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Material B2 First</title><style>
:root{{--bg:#0f1117;--panel:#171a23;--panel2:#1e2230;--line:#2a2f42;--txt:#e6e9f2;--dim:#8b93ab;--acc:#4f8cff;--mon:#39d98a}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,sans-serif;padding:16px 16px 40px}}
h1{{font-size:20px;margin-bottom:4px}}h1 a{{color:var(--txt);text-decoration:none}}
.sub{{color:var(--dim);font-size:13px;margin-bottom:16px}}
.folder{{color:var(--acc);font-size:15px;margin:18px 0 8px;text-transform:capitalize}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}}
.card .top{{display:flex;gap:10px;align-items:flex-start}}
.card .ico{{font-size:22px}}
.card b{{font-size:13.5px;display:block;line-height:1.3}}
.card .meta{{font-size:11.5px;color:var(--dim)}}
.acts{{display:flex;gap:8px;margin-top:10px;align-items:center}}
audio{{width:100%;margin-top:10px;height:34px}}
.btn{{background:var(--acc);color:#fff;border-radius:8px;padding:7px 12px;font-size:12.5px;font-weight:600;text-decoration:none}}
.dl{{color:var(--acc);font-size:12px;text-decoration:none;margin-left:auto}}
.back{{display:inline-block;margin-bottom:14px;color:var(--acc);text-decoration:none;font-size:13px}}
</style></head><body>
<a class="back" href="/">← Volver al Tracker</a>
<h1>📚 Material B2 First</h1>
<div class="sub">{total} archivos · los PDFs abren en el visor del navegador (PC y celular) · los audios se reproducen acá</div>
<input id="filtro" placeholder="🔍 Buscar material... (ej: listening, speaking, handbook)" style="width:100%;max-width:420px;background:var(--bg);border:1px solid var(--line);border-radius:9px;color:var(--txt);padding:10px 12px;font-size:14px;margin-bottom:14px">
<div id="contenido">
{''.join(blocks)}
</div>
<script>
document.getElementById('filtro').addEventListener('input',function(){{
  var q=this.value.toLowerCase().trim();
  // Ocultar/mostrar tarjetas según el texto del filtro.
  document.querySelectorAll('#contenido .card').forEach(function(c){{
    c.style.display=(!q||c.textContent.toLowerCase().includes(q))?'':'none';
  }});
  // Ocultar las carpetas que quedaron sin tarjetas visibles.
  document.querySelectorAll('#contenido .folder').forEach(function(h){{
    var sib=[];
    var n=h.nextElementSibling;
    while(n&&n.classList&&!n.classList.contains('folder')){{sib.push(n);n=n.nextElementSibling;}}
    h.style.display=sib.some(function(c){{return c.style.display!=='none'}})||!q?'':'none';
  }});
}});
</script>
</body></html>'''


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    server_version = "B2FirstPortal/1.0"

    def log_message(self, fmt, *a):
        """Silencia el log por request (ruido en journald)."""
        pass

    def _send(self, code, body, ctype, extra=None):
        """Helper: respuesta con headers mínimos + Content-Length."""
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        """Router único (usado por GET y HEAD)."""
        path = unquote(self.path.split("?")[0])

        # Tracker (index.html)
        if path in ("/", "/index.html"):
            try:
                body = open(TRACKER, "rb").read()
                self._send(200, body, "text/html; charset=utf-8")
            except OSError:
                self._send(404, b"tracker no encontrado", "text/plain")
            return

        # Página de material
        if path == "/libros":
            self._send(200, portal().encode("utf-8"), "text/html; charset=utf-8")
            return

        # Archivos del material con anti-traversal + soporte Range (audio)
        if path.startswith("/files/"):
            rel = path[len("/files/"):]
            full = os.path.realpath(os.path.join(ROOT, rel))
            # Bloquea .. y links fuera de ROOT.
            if not full.startswith(os.path.realpath(ROOT)) or not os.path.isfile(full):
                self._send(404, b"no existe", "text/plain")
                return
            size = os.path.getsize(full)
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            # Range: el navegador pide chunks para el <audio> (seek/rebobinar).
            rng = self.headers.get("Range")
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng)
                if m:
                    start = int(m.group(1) or 0)
                    end = int(m.group(2) or size - 1)
                    end = min(end, size - 1)
                    with open(full, "rb") as f:
                        f.seek(start)
                        data = f.read(end - start + 1)
                    self._send(206, data, ctype, {
                        "Content-Range": f"bytes {start}-{end}/{size}",
                        "Accept-Ranges": "bytes",
                    })
                    return
            with open(full, "rb") as f:
                data = f.read()
            self._send(200, data, ctype, {"Accept-Ranges": "bytes"})
            return

        # JSON del catálogo (lo consume la pestaña LIBROS del tracker)
        if path == "/libros.json":
            data = [{"name": it["name"], "folder": it["folder"], "ext": it["ext"],
                     "size": it["size"], "href": "/files/" + quote(it["rel"])}
                    for it in scan()]
            import json
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return

        self._send(404, b"not found", "text/plain")

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle()


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"B2First portal en http://0.0.0.0:{PORT} (root={ROOT})")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
