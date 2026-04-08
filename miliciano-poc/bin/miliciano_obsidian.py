"""Obsidian domain for Miliciano."""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import urllib.parse
import webbrowser
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from textwrap import dedent

OBSIDIAN_DEFAULT_VAULT = "~/Documents/Obsidian Vault"
OBSIDIAN_MILICIANO_NOTE = "Miliciano Cerebro.md"
OBSIDIAN_SKILLS_INDEX_NOTE = "Skills Index.md"
OBSIDIAN_SKILLS_FOLDER = "Skills"
OBSIDIAN_GRAPH_HOST = "127.0.0.1"
OBSIDIAN_GRAPH_PORT = int(os.environ.get("MILICIANO_OBSIDIAN_PORT", "8765"))

OBSIDIAN_LINK_PATTERN = re.compile(r"(?<![!])\[\[([^\]]+)\]\]")


def obsidian_vault_path():
    return os.path.expanduser(os.environ.get("OBSIDIAN_VAULT_PATH") or OBSIDIAN_DEFAULT_VAULT)


def format_timestamp(ts, ms=False):
    if ts in (None, "", 0):
        return "n/d"
    try:
        seconds = ts / 1000 if ms else ts
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return "n/d"


def strip_terminal_noise(text):
    cleaned = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text or "")
    cleaned = re.sub(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]+", " ", cleaned)
    cleaned = re.sub(r"\?25[hl]", "", cleaned)
    return cleaned.strip()


def panel(title, lines):
    print(f"\n== {title} ==")
    for line in lines:
        print(f"- {line}")


def status_badge(state):
    return {"ready": "[ready]", "pending": "[pending]", "error": "[error]"}.get(state, f"[{state}]")


def collect_obsidian_status(limit=5):
    vault = obsidian_vault_path()
    if not os.path.exists(vault):
        return {
            "path": vault,
            "present": False,
            "total_notes": 0,
            "folders": [],
            "recent": [],
            "dashboard_exists": False,
            "miliciano_exists": False,
        }

    folder_counts = Counter()
    note_entries = []
    dashboard_exists = False
    miliciano_exists = False
    skills_index_exists = False
    skills_notes = 0

    for root, _, files in os.walk(vault):
        rel_root = os.path.relpath(root, vault)
        top_folder = rel_root.split(os.sep, 1)[0] if rel_root != "." else "root"
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, vault)
            note_entries.append((os.path.getmtime(full_path), rel_path))
            folder_counts[top_folder] += 1
            if rel_path == "00 Dashboard.md":
                dashboard_exists = True
            if rel_path == OBSIDIAN_MILICIANO_NOTE:
                miliciano_exists = True
            if rel_path == OBSIDIAN_SKILLS_INDEX_NOTE:
                skills_index_exists = True
            if rel_path.startswith(f"{OBSIDIAN_SKILLS_FOLDER}{os.sep}"):
                skills_notes += 1

    note_entries.sort(key=lambda item: item[0], reverse=True)
    recent = [
        {"path": rel_path, "updated": format_timestamp(mtime)}
        for mtime, rel_path in note_entries[:limit]
    ]
    folders = [{"folder": folder, "count": count} for folder, count in sorted(folder_counts.items(), key=lambda item: (-item[1], item[0]))]
    return {
        "path": vault,
        "present": True,
        "total_notes": len(note_entries),
        "folders": folders,
        "recent": recent,
        "dashboard_exists": dashboard_exists,
        "miliciano_exists": miliciano_exists,
        "skills_index_exists": skills_index_exists,
        "skills_notes": skills_notes,
    }


def print_obsidian_overview():
    status = collect_obsidian_status()
    panel("OBSIDIAN CEREBRO", [
        f"vault     {status_badge('ready' if status['present'] else 'pending')}  {status['path']}",
        f"notas     {status['total_notes']}",
        f"dashboard {status_badge('ready' if status['dashboard_exists'] else 'pending')}  00 Dashboard",
        f"miliciano {status_badge('ready' if status['miliciano_exists'] else 'pending')}  {OBSIDIAN_MILICIANO_NOTE}",
        f"skills    {status_badge('ready' if status['skills_index_exists'] else 'pending')}  {OBSIDIAN_SKILLS_INDEX_NOTE} ({status['skills_notes']})",
    ])
    if status["folders"]:
        panel("CARPETAS MÁS ACTIVAS", [f"{row['folder']:<16} {row['count']} nota(s)" for row in status["folders"][:6]])
    if status["recent"]:
        panel("ÚLTIMOS CAMBIOS", [f"{row['updated']} · {row['path']}" for row in status['recent']])
    print("Uso:")
    print("  miliciano obsidian")
    print("  miliciano obsidian sync")
    print("  miliciano obsidian show")
    print("  miliciano obsidian web")
    print("  miliciano obsidian native")
    print("  miliciano obsidian dashboard")
    print("  miliciano obsidian note \"texto\"")


def parse_skill_frontmatter(text):
    lines = (text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fm[key.strip().lower()] = value.strip().strip('"').strip("'")
    return fm


def detect_skill_origin(skill_name, rel_dir):
    low = f"{skill_name} {rel_dir}".lower()
    if "miliciano" in low:
        return "Miliciano"
    if "hermes" in low:
        return "Hermes"
    return "Compartido"


def collect_local_skills():
    base = os.path.expanduser("~/.hermes/skills")
    skills = []
    if not os.path.exists(base):
        return skills
    for root, _, files in os.walk(base):
        if "SKILL.md" not in files:
            continue
        skill_path = os.path.join(root, "SKILL.md")
        rel_dir = os.path.relpath(root, base)
        try:
            raw = open(skill_path, "r", encoding="utf-8").read()
        except Exception:
            raw = ""
        fm = parse_skill_frontmatter(raw)
        skill_name = fm.get("name") or os.path.basename(root)
        category = rel_dir.split(os.sep, 1)[0] if rel_dir != "." else "root"
        subpath = rel_dir.replace(os.sep, "/") if rel_dir != "." else os.path.basename(root)
        description = fm.get("description") or ""
        origin = detect_skill_origin(skill_name, rel_dir)
        skills.append({
            "name": skill_name,
            "description": description,
            "category": category,
            "subpath": subpath,
            "origin": origin,
            "source_path": skill_path,
            "note_path": os.path.join(OBSIDIAN_SKILLS_FOLDER, subpath, "Skill.md"),
        })
    skills.sort(key=lambda item: (item["origin"], item["category"], item["name"]))
    return skills


def markdown_escape(text):
    return (text or "").replace("\n", " ").replace("|", "\\|")


def write_skill_note(vault, skill):
    note_path = os.path.join(vault, skill["note_path"])
    os.makedirs(os.path.dirname(note_path), exist_ok=True)
    link_back = "[[Skills Index]]"
    lines = [
        f"# {skill['name']}",
        "",
        f"- Origen: {skill['origin']}",
        f"- Categoría: {skill['category']}",
        f"- Ruta fuente: `{skill['source_path']}`",
        f"- Descripción: {skill['description'] or 'Sin descripción'}",
        "",
        "## Navegación",
        f"- {link_back}",
        f"- [[{OBSIDIAN_MILICIANO_NOTE.replace('.md', '')}]]",
        "",
        "## Fuente",
        "```md",
    ]
    try:
        source_text = open(skill["source_path"], "r", encoding="utf-8").read().strip()
    except Exception:
        source_text = ""
    if source_text:
        lines.extend(source_text.splitlines())
    else:
        lines.append("(sin contenido disponible)")
    lines.extend(["```", ""])
    with open(note_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    return note_path


def sync_obsidian_skills_index():
    status = collect_obsidian_status()
    vault = status["path"]
    os.makedirs(vault, exist_ok=True)
    skills = collect_local_skills()
    skills_folder = os.path.join(vault, OBSIDIAN_SKILLS_FOLDER)
    os.makedirs(skills_folder, exist_ok=True)
    for skill in skills:
        write_skill_note(vault, skill)

    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    index_path = os.path.join(vault, OBSIDIAN_SKILLS_INDEX_NOTE)
    grouped = {}
    for skill in skills:
        grouped.setdefault((skill["origin"], skill["category"]), []).append(skill)
    lines = [
        "# Skills Index",
        "",
        "Inventario vivo del pool compartido de skills de Hermes y Miliciano.",
        "",
        f"- Última actualización: {now}",
        f"- Fuente: `~/.hermes/skills`",
        f"- Total de skills: {len(skills)}",
        "",
        "## Leyenda",
        "- Hermes: skills heredadas o de base del ecosistema Hermes",
        "- Miliciano: skills propias del wrapper/producto Miliciano",
        "- Compartido: skills reutilizables del pool común",
        "",
    ]
    for (origin, category), bucket in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        lines.append(f"## {origin} · {category}")
        for skill in bucket:
            note_rel = skill["note_path"].replace(os.sep, "/")[:-3]
            desc = skill["description"] or "Sin descripción"
            lines.append(f"- [[{note_rel}|{skill['name']}]] — {desc}")
        lines.append("")
    lines.extend([
        "## Navegación",
        f"- [[{OBSIDIAN_MILICIANO_NOTE.replace('.md', '')}]]",
        "- [[00 Dashboard]]",
    ])
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    return index_path, len(skills)


def sync_obsidian_cerebro():
    status = collect_obsidian_status()
    vault = status["path"]
    os.makedirs(vault, exist_ok=True)
    skills_index_path, skills_count = sync_obsidian_skills_index()
    note_path = os.path.join(vault, OBSIDIAN_MILICIANO_NOTE)
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# Miliciano Cerebro",
        "",
        "Nodo operativo para ver cómo crece el conocimiento de Miliciano dentro de Obsidian.",
        "",
        f"- Última actualización: {now}",
        f"- Vault: {vault}",
        f"- Total de notas: {status['total_notes']}",
        f"- Skills index: [[{OBSIDIAN_SKILLS_INDEX_NOTE.replace('.md', '')}]] ({skills_count} skills)",
        "",
        "## Enlaces vivos",
        "- [[00 Dashboard]]",
        "- [[01 Inbox]]",
        "- [[02 Consultas]]",
        "- [[03 Entidades]]",
        "- [[04 Decisiones]]",
        "- [[05 Evidencia]]",
        "- [[06 Pendientes]]",
        "- [[99 Grafo actual]]",
        f"- [[{OBSIDIAN_SKILLS_INDEX_NOTE.replace('.md', '')}]]",
        "",
        "## Últimos cambios",
    ]
    if status["recent"]:
        for row in status["recent"]:
            lines.append(f"- {row['updated']} · [[{row['path'].replace('.md', '')}]]")
    else:
        lines.append("- Sin notas todavía")
    lines.extend([
        "",
        "## Cómo crece este cerebro",
        "- Cada consulta debería dejar rastro en Inbox, Consultas, Evidencia, Decisiones o Pendientes.",
        "- El grafo debe mantenerse enlazado para que Obsidian muestre contexto útil.",
        "- Usa este nodo como punto de partida para revisar crecimiento y actividad.",
        f"- El inventario de skills se genera desde `~/.hermes/skills` y se refleja en {skills_index_path}.",
    ])
    with open(note_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    return note_path


def obsidian_memory_enabled():
    return os.environ.get("MILICIANO_OBSIDIAN_AUTOSAVE", "1").strip().lower() not in {"0", "false", "no", "off"}


def normalize_obsidian_text(text, max_chars=1800):
    cleaned = strip_terminal_noise((text or "").strip()).replace("\r\n", "\n")
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "\n…(truncado)"


def should_capture_obsidian(prompt):
    cleaned = " ".join((prompt or "").split()).strip()
    if not cleaned:
        return False
    if cleaned.lower() in {"hola", "buenas", "gracias", "ok", "vale", "si", "sí", "no"}:
        return False
    return len(cleaned) >= 8


def obsidian_memory_kind(prompt, source="consulta"):
    low = (prompt or "").lower()
    if source == "mission" or any(word in low for word in ("decidir", "decisión", "decision", "recomienda", "conviene", "elige", "compare", "comparar", "plan")):
        return "decision"
    if source == "exec":
        return "pending"
    return "query"


def obsidian_memory_paths(kind):
    if kind == "decision":
        return os.path.join(obsidian_vault_path(), "04 Decisiones", "Decision - actual.md"), os.path.join(obsidian_vault_path(), "04 Decisiones")
    if kind == "pending":
        return os.path.join(obsidian_vault_path(), "06 Pendientes", "Pendiente - actual.md"), os.path.join(obsidian_vault_path(), "06 Pendientes")
    return os.path.join(obsidian_vault_path(), "02 Consultas", "Consulta - actual.md"), os.path.join(obsidian_vault_path(), "02 Consultas")


def save_obsidian_memory(prompt, response=None, route=None, source="consulta", session_id=None, extra=None):
    if not obsidian_memory_enabled() or not should_capture_obsidian(prompt):
        return None

    kind = obsidian_memory_kind(prompt, source=source)
    active_path, folder = obsidian_memory_paths(kind)
    os.makedirs(folder, exist_ok=True)
    vault = obsidian_vault_path()
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    file_stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    history_name = f"{kind.title()} - {file_stamp}.md"
    history_path = os.path.join(folder, history_name)
    prompt_text = normalize_obsidian_text(prompt, max_chars=1800)
    response_text = normalize_obsidian_text(response or "", max_chars=2200)
    route_spec = route.get("spec") if isinstance(route, dict) else None
    route_role = route.get("role") if isinstance(route, dict) else None
    route_reason = route.get("reason") if isinstance(route, dict) else None

    tag = {"decision": "#decision", "pending": "#pendiente"}.get(kind, "#consulta")
    title = f"{kind.title()} - {file_stamp}"
    head = {
        "decision": "## Resolución",
        "pending": "## Estado",
        "query": "## Respuesta",
    }.get(kind, "## Respuesta")
    context_title = {
        "decision": "## Contexto",
        "pending": "## Tarea",
        "query": "## Objetivo",
    }.get(kind, "## Objetivo")

    body = [
        f"# {title}",
        tag,
        "#miliciano",
        "",
        context_title,
        prompt_text,
        "",
        head,
        response_text or ("Pendiente de cerrar." if kind == "pending" else "Sin respuesta aún."),
        "",
        "## Ruta",
        f"- Rol: {route_role or 'n/d'}",
        f"- Especificación: {route_spec or 'n/d'}",
        f"- Motivo: {route_reason or 'n/d'}",
    ]
    if session_id:
        body.extend(["", "## Sesión", f"- {session_id}"])
    if extra:
        body.extend(["", "## Extra", normalize_obsidian_text(extra, max_chars=1000)])
    body.extend(["", "## Enlaces", "- [[Miliciano Cerebro]]", "- [[00 Dashboard]]"])
    with open(history_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body).rstrip() + "\n")

    active_lines = [
        f"# {os.path.splitext(os.path.basename(active_path))[0]}",
        tag,
        "#miliciano",
        "",
        f"## { 'Decisión vigente' if kind == 'decision' else 'Pendiente vigente' if kind == 'pending' else 'Última consulta' }",
        prompt_text,
        "",
        f"## { 'Resolución' if kind == 'decision' else 'Estado' if kind == 'pending' else 'Última respuesta' }",
        response_text or ("Pendiente de cerrar." if kind == "pending" else "Sin respuesta aún."),
        "",
        "## Historial",
        f"- [[{os.path.splitext(history_name)[0]}]]",
        "",
        "## Enlaces",
        "- [[Miliciano Cerebro]]",
        "- [[00 Dashboard]]",
    ]
    with open(active_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(active_lines).rstrip() + "\n")

    inbox_path = os.path.join(vault, "01 Inbox.md")
    inbox_line = f"- {stamp} · [{kind}] {prompt_text[:140]}"
    if response_text:
        inbox_line += f" → {response_text[:90].replace(chr(10), ' ')}"
    if os.path.exists(inbox_path):
        with open(inbox_path, "a", encoding="utf-8") as fh:
            fh.write(inbox_line + "\n")
    else:
        with open(inbox_path, "w", encoding="utf-8") as fh:
            fh.write("# Inbox\n\nCaptura rápida de ideas, pedidos y hallazgos antes de ordenarlos.\n\n## Entradas\n")
            fh.write(inbox_line + "\n")

    sync_obsidian_cerebro()
    return history_path


def obsidian_note_title(rel_path):
    return os.path.splitext(os.path.basename(rel_path))[0]


def obsidian_note_id(rel_path):
    return rel_path[:-3] if rel_path.lower().endswith(".md") else rel_path


def parse_obsidian_link(raw):
    target = (raw or "").split("|", 1)[0].split("#", 1)[0].strip()
    if not target or target.lower().startswith(("http://", "https://", "file://", "obsidian://")):
        return None
    return target.replace("\\", "/")


def build_obsidian_indexes(note_paths):
    exact, by_base = {}, {}
    for rel_path in note_paths:
        note_id = obsidian_note_id(rel_path)
        base = obsidian_note_title(rel_path).lower()
        exact[note_id.lower()] = rel_path
        exact[rel_path.lower()] = rel_path
        exact[(note_id + ".md").lower()] = rel_path
        by_base.setdefault(base, []).append(rel_path)
    return exact, by_base


def resolve_obsidian_link(target, exact_index, base_index):
    if not target:
        return None
    normalized = target.replace("\\", "/")
    for candidate in (normalized, normalized + ".md", normalized.lstrip("./"), normalized.lstrip("./") + ".md"):
        found = exact_index.get(candidate.lower())
        if found:
            return found
    matches = base_index.get(os.path.splitext(os.path.basename(normalized))[0].lower()) or []
    return matches[0] if len(matches) == 1 else None


def collect_obsidian_graph():
    status = collect_obsidian_status()
    graph = dict(status)
    graph.update({"nodes": [], "edges": []})
    vault = status["path"]
    if not status["present"]:
        return graph

    note_paths, note_texts, note_mtimes = [], {}, {}
    for root, _, files in os.walk(vault):
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, vault)
            note_paths.append(rel_path)
            note_mtimes[rel_path] = os.path.getmtime(full_path)
            try:
                note_texts[rel_path] = open(full_path, "r", encoding="utf-8").read()
            except Exception:
                note_texts[rel_path] = ""

    exact_index, base_index = build_obsidian_indexes(note_paths)
    incoming, outgoing, edges, seen_edges = {}, {}, [], set()
    for rel_path in note_paths:
        source = obsidian_note_id(rel_path)
        for raw_link in OBSIDIAN_LINK_PATTERN.findall(note_texts.get(rel_path, "")):
            resolved = resolve_obsidian_link(parse_obsidian_link(raw_link), exact_index, base_index)
            if not resolved or resolved == rel_path:
                continue
            edge = (source, obsidian_note_id(resolved))
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            edges.append({"source": edge[0], "target": edge[1]})
            outgoing.setdefault(edge[0], set()).add(edge[1])
            incoming.setdefault(edge[1], set()).add(edge[0])

    nodes = []
    for rel_path in note_paths:
        note_id = obsidian_note_id(rel_path)
        in_degree = len(incoming.get(note_id, set()))
        out_degree = len(outgoing.get(note_id, set()))
        degree = in_degree + out_degree
        nodes.append({
            "id": note_id,
            "label": obsidian_note_title(rel_path),
            "path": rel_path,
            "folder": os.path.dirname(rel_path) or "root",
            "updated": format_timestamp(note_mtimes.get(rel_path, 0)),
            "incoming": in_degree,
            "outgoing": out_degree,
            "degree": degree,
            "size": max(10, min(28, 10 + degree * 2)),
            "pinned": rel_path == OBSIDIAN_MILICIANO_NOTE or rel_path == "00 Dashboard.md",
        })

    graph["nodes"] = sorted(nodes, key=lambda item: (-item["degree"], item["label"]))
    graph["edges"] = edges
    return graph


def obsidian_graph_html():
    return dedent("""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Miliciano Obsidian Graph</title>
      <style>
        body { font-family: system-ui, sans-serif; margin: 0; background: #0b1020; color: #eef0ff; }
        header { padding: 16px 20px; border-bottom: 1px solid rgba(255,255,255,.08); }
        main { display: grid; grid-template-columns: 1fr 320px; gap: 12px; padding: 12px; }
        .panel { background: rgba(18,24,46,.92); border: 1px solid rgba(255,255,255,.08); border-radius: 16px; padding: 12px; }
        #graph { width: 100%; height: 70vh; border-radius: 14px; background: rgba(0,0,0,.18); }
        .node { display: inline-block; margin: 4px 6px 4px 0; padding: 4px 8px; border-radius: 999px; background: rgba(168,85,247,.18); }
        .edge { color: #9aa3c7; font-size: 12px; margin: 2px 0; }
        input { width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,.08); background: rgba(0,0,0,.2); color: white; }
      </style>
    </head>
    <body>
      <header>
        <strong>Miliciano Obsidian Graph</strong><br>
        <small>Mapa del vault en vivo</small>
      </header>
      <main>
        <section class="panel">
          <input id="q" placeholder="Filtra por nota, carpeta o palabra clave..." />
          <div id="graph"></div>
        </section>
        <aside class="panel" id="side">
          Cargando...
        </aside>
      </main>
      <script>
        let raw = null;
        const graph = document.getElementById('graph');
        const side = document.getElementById('side');
        const q = document.getElementById('q');
        async function load() {
          raw = await (await fetch('/api/graph')).json();
          render();
        }
        function render() {
          const term = q.value.toLowerCase().trim();
          const nodes = (raw.nodes || []).filter(n => !term || `${n.label} ${n.path} ${n.folder}`.toLowerCase().includes(term));
          const nodeIds = new Set(nodes.map(n => n.id));
          const edges = (raw.edges || []).filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
          graph.innerHTML = nodes.map(n => `<span class="node">${escapeHtml(n.label)}</span>`).join(' ');
          side.innerHTML = '<h3>Notas</h3>' + nodes.map(n => `<div>${escapeHtml(n.path)} · ${n.degree}</div>`).join('') + '<h3>Enlaces</h3>' + edges.map(e => `<div class="edge">${escapeHtml(e.source)} → ${escapeHtml(e.target)}</div>`).join('');
        }
        function escapeHtml(s){return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');}
        q.addEventListener('input', render);
        load().catch(err => side.textContent = String(err));
      </script>
    </body>
    </html>
    """).strip()


def serve_obsidian_graph(port=OBSIDIAN_GRAPH_PORT, host=OBSIDIAN_GRAPH_HOST, open_browser=True):
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
                return self._write(json.dumps(collect_obsidian_graph(), ensure_ascii=False), "application/json; charset=utf-8")
            if path == "/api/status":
                return self._write(json.dumps(collect_obsidian_status(), ensure_ascii=False), "application/json; charset=utf-8")
            return self._write("Not found", status=404)

    server = None
    bound_port = None
    for candidate in range(int(port), int(port) + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), Handler)
            bound_port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError(f"No pude abrir un puerto para Obsidian Graph desde {port}")

    url = f"http://{host}:{bound_port}/"
    print(f"Obsidian Graph listo en {url}")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando Obsidian Graph…")
    finally:
        server.server_close()


def open_obsidian_native(target=None, new_window=False):
    vault = obsidian_vault_path()
    launcher = os.path.expanduser("~/Applications/Obsidian-launch.sh")
    target_path = target.replace(os.sep, "/") if target else vault
    absolute_target = target_path if os.path.isabs(target_path) else os.path.join(vault, target_path)
    appimage = os.path.expanduser("~/Applications/Obsidian.AppImage")
    if os.path.exists(appimage):
        try:
            probe = subprocess.run(["file", appimage], text=True, capture_output=True, timeout=6)
            probe_text = (probe.stdout or "").lower()
            if platform.machine().lower() in {"x86_64", "amd64"} and ("aarch64" in probe_text or "arm" in probe_text):
                print("Obsidian nativo no puede abrirse en este host: la AppImage instalada es ARM/aarch64 y tu máquina es x86_64.", file=sys.stderr)
                print("Solución: instala la versión x86_64 de Obsidian o usa `miliciano obsidian web`.", file=sys.stderr)
                subprocess.Popen(["xdg-open", vault], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
        except Exception:
            pass
    cmd = [launcher if os.path.exists(launcher) else appimage]
    if new_window:
        cmd.append("--new-window")
    cmd.append(absolute_target if os.path.exists(absolute_target) else vault)
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Obsidian abierto en modo nativo · {cmd[-1]}")
    except Exception:
        subprocess.Popen(["xdg-open", vault], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"No pude abrir Obsidian nativo; abrí el vault en el gestor de archivos → {vault}")


def obsidian_search_notes(query):
    vault = obsidian_vault_path()
    results = []
    if not os.path.exists(vault):
        return results
    needle = (query or "").lower()
    for root, _, files in os.walk(vault):
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            full_path = os.path.join(root, name)
            rel_path = os.path.relpath(full_path, vault)
            try:
                text = open(full_path, "r", encoding="utf-8").read().lower()
            except Exception:
                continue
            if needle in name.lower() or needle in text:
                results.append(rel_path)
    return sorted(results)


def cmd_obsidian(args):
    if not args or args[0] in {"show", "status", "list"}:
        print_obsidian_overview()
        return

    action = args[0].lower()
    if action in {"sync", "refresh", "seed"}:
        note_path = sync_obsidian_cerebro()
        print(f"Obsidian sincronizado en {note_path}")
        print_obsidian_overview()
        return
    if action in {"web", "graph", "dashboard"}:
        print("Abriendo grafo interactivo de Obsidian…")
        serve_obsidian_graph(port=OBSIDIAN_GRAPH_PORT, open_browser=True)
        return
    if action in {"native", "app", "open"}:
        target = args[1] if len(args) > 1 else None
        open_obsidian_native(target=target)
        return
    if action in {"note", "append", "inbox"}:
        if len(args) < 2:
            print('Uso: miliciano obsidian note "texto"', file=sys.stderr)
            sys.exit(1)
        text = " ".join(args[1:]).strip()
        vault = obsidian_vault_path()
        os.makedirs(vault, exist_ok=True)
        inbox_path = os.path.join(vault, "01 Inbox.md")
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        line = f"- {timestamp} · {text}"
        if os.path.exists(inbox_path):
            with open(inbox_path, "a", encoding="utf-8") as fh:
                fh.write("\n" + line + "\n")
        else:
            with open(inbox_path, "w", encoding="utf-8") as fh:
                fh.write("# Inbox\n\nCaptura rápida de ideas, pedidos y hallazgos antes de ordenarlos.\n\n## Entradas\n")
                fh.write(line + "\n")
        print(f"Guardado en {inbox_path}")
        print_obsidian_overview()
        return

    print(f"Acción de obsidian desconocida: {action}", file=sys.stderr)
    print("Usa: show | sync | note | web | native", file=sys.stderr)
    sys.exit(1)
