#!/usr/bin/env python3
"""Obsidian integration for Miliciano using the real vault and desktop app."""

from __future__ import annotations

import os
import sys
from collections import Counter

from miliciano_constants import OBSIDIAN_DEFAULT_VAULT, OBSIDIAN_MILICIANO_NOTE
from miliciano_obsidian_app import (
    detect_obsidian_app,
    open_obsidian_native as _open_obsidian_native,
    serve_obsidian_graph as _serve_obsidian_graph,
)
from miliciano_obsidian_memory import (
    MILICIANO_OBSIDIAN_DIR,
    append_unique_line,
    ensure_vault_structure,
    obsidian_inbox_path,
    obsidian_root_note_path,
    read_text,
    save_memory_entry,
    write_if_changed,
)
from miliciano_system import format_timestamp


def obsidian_vault_path():
    return os.path.expanduser(os.environ.get("OBSIDIAN_VAULT_PATH") or OBSIDIAN_DEFAULT_VAULT)


def obsidian_vault_name():
    return os.path.basename(obsidian_vault_path().rstrip(os.sep))


def save_obsidian_memory(prompt, response=None, route=None, source="consulta", session_id=None, extra=None):
    vault = obsidian_vault_path()
    return save_memory_entry(vault, prompt, response=response, route=route, source=source, session_id=session_id, extra=extra, sync_callback=sync_obsidian_cerebro)


def collect_obsidian_status(limit=5):
    vault = obsidian_vault_path()
    app = detect_obsidian_app()
    root_note = obsidian_root_note_path(vault)
    inbox_path = obsidian_inbox_path(vault)
    if not os.path.exists(vault):
        return {
            "path": vault,
            "present": False,
            "app_available": app["available"],
            "app_mode": app["mode"],
            "total_notes": 0,
            "folders": [],
            "recent": [],
            "miliciano_exists": False,
            "inbox_exists": False,
        }

    folder_counts = Counter()
    note_entries = []
    miliciano_notes = 0
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
            if rel_path.startswith(f"{MILICIANO_OBSIDIAN_DIR}{os.sep}") or rel_path == OBSIDIAN_MILICIANO_NOTE:
                miliciano_notes += 1

    note_entries.sort(key=lambda item: item[0], reverse=True)
    return {
        "path": vault,
        "present": True,
        "app_available": app["available"],
        "app_mode": app["mode"],
        "app_path": app["path"],
        "total_notes": len(note_entries),
        "folders": [{"folder": folder, "count": count} for folder, count in sorted(folder_counts.items(), key=lambda item: (-item[1], item[0]))],
        "recent": [{"path": rel_path, "updated": format_timestamp(mtime)} for mtime, rel_path in note_entries[:limit]],
        "miliciano_exists": os.path.exists(root_note),
        "inbox_exists": os.path.exists(inbox_path),
        "miliciano_notes": miliciano_notes,
        "root_note": root_note,
    }


def print_obsidian_overview():
    status = collect_obsidian_status()
    print("\n== OBSIDIAN ==")
    print(f"- vault     {'[ready]' if status['present'] else '[pending]'}  {status['path']}")
    print(f"- app       {'[ready]' if status['app_available'] else '[pending]'}  {status.get('app_mode', 'none')}")
    print(f"- notas     {status['total_notes']}")
    print(f"- miliciano {'[ready]' if status['miliciano_exists'] else '[pending]'}  {OBSIDIAN_MILICIANO_NOTE}")
    print(f"- inbox     {'[ready]' if status['inbox_exists'] else '[pending]'}  {MILICIANO_OBSIDIAN_DIR}/Inbox.md")
    print(f"- propias   {status.get('miliciano_notes', 0)} nota(s)")
    if status["recent"]:
        print("\n== ÚLTIMOS CAMBIOS ==")
        for row in status["recent"][:6]:
            print(f"- {row['updated']} · {row['path']}")


def sync_obsidian_cerebro():
    vault = ensure_vault_structure(obsidian_vault_path())
    status = collect_obsidian_status()
    from datetime import datetime
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# Miliciano Cerebro",
        "",
        "Punto de entrada de Miliciano dentro del vault real de Obsidian.",
        "",
        f"- Última actualización: {now}",
        f"- Vault: {vault}",
        f"- App detectada: {'sí' if status['app_available'] else 'no'} ({status.get('app_mode', 'none')})",
        f"- Notas del vault: {status['total_notes']}",
        f"- Notas de Miliciano: {status.get('miliciano_notes', 0)}",
        "",
        "## Navegación",
        f"- [[{MILICIANO_OBSIDIAN_DIR}/Inbox]]",
        f"- [[{MILICIANO_OBSIDIAN_DIR}/Query - current]]",
        f"- [[{MILICIANO_OBSIDIAN_DIR}/Decision - current]]",
        f"- [[{MILICIANO_OBSIDIAN_DIR}/Execution - current]]",
        f"- [[{MILICIANO_OBSIDIAN_DIR}/Session - current]]",
        "",
        "## Últimos cambios",
    ]
    if status["recent"]:
        for row in status["recent"][:8]:
            note_ref = row["path"][:-3] if row["path"].endswith(".md") else row["path"]
            lines.append(f"- {row['updated']} · [[{note_ref}]]")
    else:
        lines.append("- Sin notas todavía")
    write_if_changed(obsidian_root_note_path(vault), "\n".join(lines).rstrip() + "\n")
    return obsidian_root_note_path(vault)


def open_obsidian_native(target=None, new_window=False):
    vault = ensure_vault_structure(obsidian_vault_path())
    _open_obsidian_native(vault, obsidian_vault_name(), target=target, new_window=new_window)


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
            text = read_text(full_path).lower()
            if needle in name.lower() or needle in text:
                results.append(rel_path)
    return sorted(results)


def collect_obsidian_graph():
    status = collect_obsidian_status()
    graph = dict(status)
    graph.update({"nodes": [], "edges": []})
    vault = status["path"]
    if not status["present"]:
        return graph
    note_paths = []
    for root, _, files in os.walk(vault):
        for name in files:
            if name.lower().endswith(".md"):
                note_paths.append(os.path.relpath(os.path.join(root, name), vault))
    graph["nodes"] = [{"id": path[:-3], "label": os.path.basename(path[:-3]), "path": path} for path in sorted(note_paths)]
    return graph


def serve_obsidian_graph(port=None, host=None, open_browser=True):
    from miliciano_status import health_check_json
    _serve_obsidian_graph(collect_obsidian_graph, collect_obsidian_status, health_check_json, port=port or 8765, host=host or "127.0.0.1", open_browser=open_browser)


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
    if action in {"native", "app", "open"}:
        open_obsidian_native(target=args[1] if len(args) > 1 else None)
        return
    if action in {"note", "append", "inbox"}:
        if len(args) < 2:
            print('Uso: miliciano obsidian note "texto"', file=sys.stderr)
            sys.exit(1)
        vault = ensure_vault_structure(obsidian_vault_path())
        from datetime import datetime
        line = f"- {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} · {' '.join(args[1:]).strip()}"
        append_unique_line(obsidian_inbox_path(vault), line, "# Miliciano Inbox")
        sync_obsidian_cerebro()
        print(f"Guardado en {obsidian_inbox_path(vault)}")
        return
    if action in {"search", "find"}:
        if len(args) < 2:
            print('Uso: miliciano obsidian search "texto"', file=sys.stderr)
            sys.exit(1)
        for result in obsidian_search_notes(" ".join(args[1:]).strip())[:30]:
            print(result)
        return
    if action in {"web", "graph"}:
        print("Abriendo vista web del vault; para uso diario prioriza `miliciano obsidian open`.")
        serve_obsidian_graph(open_browser=True)
        return

    print(f"Acción de obsidian desconocida: {action}", file=sys.stderr)
    print("Usa: show | sync | open | note | search | web", file=sys.stderr)
    sys.exit(1)
