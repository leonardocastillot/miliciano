#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime

from miliciano_constants import OBSIDIAN_MILICIANO_NOTE
from miliciano_system import strip_terminal_noise


MILICIANO_OBSIDIAN_DIR = "Miliciano"
MEMORY_FOLDERS = {
    "query": os.path.join(MILICIANO_OBSIDIAN_DIR, "Queries"),
    "decision": os.path.join(MILICIANO_OBSIDIAN_DIR, "Decisions"),
    "execution": os.path.join(MILICIANO_OBSIDIAN_DIR, "Executions"),
    "session": os.path.join(MILICIANO_OBSIDIAN_DIR, "Sessions"),
}


def obsidian_memory_enabled():
    return os.environ.get("MILICIANO_OBSIDIAN_AUTOSAVE", "1").strip().lower() not in {"0", "false", "no", "off"}


def normalize_obsidian_text(text, max_chars=2200):
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
    if source in {"mission", "mission_plan"} or any(word in low for word in ("decidir", "decisión", "decision", "recomienda", "conviene", "elige", "compare", "comparar", "plan")):
        return "decision"
    if source == "exec":
        return "execution"
    if source == "session":
        return "session"
    return "query"


def ensure_vault_structure(vault_path):
    os.makedirs(vault_path, exist_ok=True)
    os.makedirs(os.path.join(vault_path, MILICIANO_OBSIDIAN_DIR), exist_ok=True)
    for folder in MEMORY_FOLDERS.values():
        os.makedirs(os.path.join(vault_path, folder), exist_ok=True)
    return vault_path


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def write_if_changed(path, content):
    current = read_text(path)
    if current == content:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return True


def append_unique_line(path, line, header):
    existing = read_text(path)
    if line in existing:
        return False
    body = f"{header}\n\n{line}\n" if not existing else existing.rstrip() + "\n" + line + "\n"
    write_if_changed(path, body)
    return True


def obsidian_inbox_path(vault_path):
    return os.path.join(vault_path, MILICIANO_OBSIDIAN_DIR, "Inbox.md")


def obsidian_root_note_path(vault_path):
    return os.path.join(vault_path, OBSIDIAN_MILICIANO_NOTE)


def memory_folder_for_kind(vault_path, kind):
    return os.path.join(vault_path, MEMORY_FOLDERS.get(kind, MEMORY_FOLDERS["query"]))


def active_note_path(vault_path, kind):
    mapping = {
        "query": os.path.join(vault_path, MILICIANO_OBSIDIAN_DIR, "Query - current.md"),
        "decision": os.path.join(vault_path, MILICIANO_OBSIDIAN_DIR, "Decision - current.md"),
        "execution": os.path.join(vault_path, MILICIANO_OBSIDIAN_DIR, "Execution - current.md"),
        "session": os.path.join(vault_path, MILICIANO_OBSIDIAN_DIR, "Session - current.md"),
    }
    return mapping[kind]


def build_memory_note(title, prompt_text, response_text, route=None, session_id=None, extra=None):
    route_spec = route.get("spec") if isinstance(route, dict) else None
    route_role = route.get("role") if isinstance(route, dict) else None
    route_reason = route.get("reason") if isinstance(route, dict) else None
    lines = [
        f"# {title}",
        "",
        "## Prompt",
        prompt_text,
        "",
        "## Respuesta",
        response_text or "Sin respuesta aún.",
        "",
        "## Ruta",
        f"- Rol: {route_role or 'n/d'}",
        f"- Especificación: {route_spec or 'n/d'}",
        f"- Motivo: {route_reason or 'n/d'}",
    ]
    if session_id:
        lines.extend(["", "## Sesión", f"- {session_id}"])
    if extra:
        lines.extend(["", "## Extra", normalize_obsidian_text(extra, max_chars=1200)])
    lines.extend(["", "## Enlaces", f"- [[{OBSIDIAN_MILICIANO_NOTE[:-3]}]]", f"- [[{MILICIANO_OBSIDIAN_DIR}/Inbox]]"])
    return "\n".join(lines).rstrip() + "\n"


def save_memory_entry(vault_path, prompt, response=None, route=None, source="consulta", session_id=None, extra=None, sync_callback=None):
    if not obsidian_memory_enabled() or not should_capture_obsidian(prompt):
        return None

    ensure_vault_structure(vault_path)
    kind = obsidian_memory_kind(prompt, source=source)
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    file_stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    prompt_text = normalize_obsidian_text(prompt, max_chars=1800)
    response_text = normalize_obsidian_text(response or "", max_chars=3200)
    folder = memory_folder_for_kind(vault_path, kind)
    title = f"{kind.title()} - {file_stamp}"
    history_path = os.path.join(folder, f"{title}.md")
    current_path = active_note_path(vault_path, kind)
    body = build_memory_note(title, prompt_text, response_text, route=route, session_id=session_id, extra=extra)

    current_active = read_text(current_path)
    if prompt_text and prompt_text in current_active and response_text and response_text in current_active:
        return current_path

    write_if_changed(history_path, body)
    write_if_changed(current_path, build_memory_note(f"{kind.title()} actual", prompt_text, response_text, route=route, session_id=session_id, extra=extra))

    inbox_line = f"- {stamp} · [{kind}] {prompt_text[:140]}"
    if response_text:
        inbox_line += f" → {response_text[:120].replace(chr(10), ' ')}"
    append_unique_line(obsidian_inbox_path(vault_path), inbox_line, "# Miliciano Inbox")
    if sync_callback:
        sync_callback()
    return history_path
