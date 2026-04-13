#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from textwrap import dedent

from miliciano_constants import OBSIDIAN_GRAPH_HOST, OBSIDIAN_GRAPH_PORT


def detect_obsidian_app():
    launcher = os.path.expanduser("~/Applications/Obsidian-launch.sh")
    appimage = os.path.expanduser("~/Applications/Obsidian.AppImage")
    if os.path.exists(launcher):
        return {"available": True, "mode": "launcher", "path": launcher}
    if os.path.exists(appimage):
        return {"available": True, "mode": "appimage", "path": appimage}
    from shutil import which
    exe = which("obsidian")
    if exe:
        return {"available": True, "mode": "binary", "path": exe}
    return {"available": False, "mode": "none", "path": None}


def build_obsidian_uri(vault_name, target=None):
    encoded_vault = urllib.parse.quote(vault_name)
    if target:
        rel_target = target.replace(os.sep, "/")
        if rel_target.endswith(".md"):
            rel_target = rel_target[:-3]
        return f"obsidian://open?vault={encoded_vault}&file={urllib.parse.quote(rel_target)}"
    return f"obsidian://open?vault={encoded_vault}"


def open_obsidian_native(vault_path, vault_name, target=None, new_window=False):
    app = detect_obsidian_app()
    abs_target = None
    rel_target = None
    if target:
        abs_target = target if os.path.isabs(target) else os.path.join(vault_path, target)
        if os.path.exists(abs_target):
            rel_target = os.path.relpath(abs_target, vault_path)
    uri = build_obsidian_uri(vault_name, rel_target)

    try:
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Obsidian abierto en la app existente · {rel_target or vault_name}")
        return
    except Exception:
        pass

    if app["available"]:
        cmd = [app["path"]]
        if new_window and app["mode"] != "binary":
            cmd.append("--new-window")
        cmd.append(abs_target or vault_path)
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"Obsidian abierto en modo nativo · {cmd[-1]}")
            return
        except Exception:
            pass

    subprocess.Popen(["xdg-open", vault_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"No pude abrir la app de Obsidian; abrí el vault en el gestor de archivos → {vault_path}")


def obsidian_graph_html():
    return dedent("""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Miliciano Obsidian Graph</title>
      <style>
        body { font-family: system-ui, sans-serif; margin: 0; padding: 20px; background: #0b1020; color: #eef0ff; }
        .node { display: inline-block; margin: 6px; padding: 6px 10px; border-radius: 999px; background: rgba(255,255,255,.08); }
      </style>
    </head>
    <body>
      <h1>Miliciano Obsidian Graph</h1>
      <div id="graph">Cargando…</div>
      <script>
        fetch('/api/graph').then(r => r.json()).then(data => {
          document.getElementById('graph').innerHTML = (data.nodes || []).map(n => `<span class="node">${n.path}</span>`).join(' ');
        });
      </script>
    </body>
    </html>
    """).strip()


def serve_obsidian_graph(collect_graph, collect_status, health_check_json, port=OBSIDIAN_GRAPH_PORT, host=OBSIDIAN_GRAPH_HOST, open_browser=True):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _write(self, body, content_type="text/plain; charset=utf-8", status=200):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path in {"/", "/index.html"}:
                return self._write(obsidian_graph_html(), "text/html; charset=utf-8")
            if path == "/api/graph":
                return self._write(json.dumps(collect_graph(), ensure_ascii=False), "application/json; charset=utf-8")
            if path == "/api/status":
                return self._write(json.dumps(collect_status(), ensure_ascii=False), "application/json; charset=utf-8")
            if path == "/health":
                health = health_check_json()
                return self._write(json.dumps(health, ensure_ascii=False), "application/json; charset=utf-8", status=200 if health["healthy"] else 503)
            return self._write("Not found", status=404)

    server = None
    for candidate in range(int(port), int(port) + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), Handler)
            url = f"http://{host}:{candidate}/"
            print(f"Obsidian Graph listo en {url}")
            if open_browser:
                webbrowser.open(url)
            server.serve_forever()
            return
        except OSError:
            continue
        except KeyboardInterrupt:
            break
        finally:
            if server:
                server.server_close()
    raise RuntimeError(f"No pude abrir un puerto para Obsidian Graph desde {port}")
