#!/usr/bin/env python3
import re
from textwrap import dedent, wrap
import os
import json

PURPLE = "\033[38;5;141m"
VIOLET = "\033[38;5;177m"
SOFT = "\033[38;5;183m"
YELLOW = "\033[38;5;221m"
CYAN = "\033[38;5;117m"
CODE_BG = "\033[48;5;236m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.+?)\s*$")
CODE_FENCE_RE = re.compile(r"^(```|~~~)(.*)$")


def _load_preferences():
    try:
        config_path = os.path.expanduser("~/.config/miliciano/config.json")
        with open(config_path, "r") as f:
            state = json.load(f)
        return state.get("preferences", {})
    except Exception:
        return {}


def is_compact():
    """Check if output_mode is set to 'compact' in config."""
    mode = _load_preferences().get("output_mode", "debug")
    return mode == "compact"


def response_style():
    return _load_preferences().get("response_style", "tactical_markdown")


def terminal_width(default=None):
    try:
        columns = max(72, os.get_terminal_size().columns - 2)
        if default is None:
            return columns
        return max(72, min(default, columns))
    except OSError:
        return default or 94


def rule(label="", accent="═", width=None):
    width = width or terminal_width()
    if label:
        core = f" {label} "
        body = (accent * max(8, width - len(label) - 2))[: max(8, width - len(label) - 2)]
        return f"{VIOLET}{core}{body}{RESET}"
    return f"{VIOLET}{accent * width}{RESET}"


def split_columns(left, right="", width=None):
    width = width or terminal_width()
    raw = f"{left}"
    if right:
        pad = max(2, width - len(left) - len(right))
        raw = f"{left}{' ' * pad}{right}"
    return raw[:width]


def status_badge(kind):
    colors = {
        "ready": "\033[38;5;84m",
        "pending": "\033[38;5;221m",
        "error": "\033[38;5;203m",
        "info": "\033[38;5;117m",
    }
    labels = {
        "ready": "READY",
        "pending": "PENDING",
        "error": "ERROR",
        "info": "INFO",
    }
    color = colors.get(kind, SOFT)
    label = labels.get(kind, kind.upper())
    return f"{color}[{label}]{RESET}"


def print_kv(label, value, indent=2):
    print(f"{' ' * indent}{SOFT}{label}:{RESET} {value}")


def panel(title, rows):
    """Display panel with title and rows. Compact mode: skip decorative borders."""
    if is_compact():
        # Compact: just title + rows, no boxes
        print(f"\n== {title} ==")
        for row in rows:
            print(f"- {row}")
    else:
        # Normal: full panel with borders
        width = terminal_width()
        print(rule(f" {title} ", "─", width))
        for row in rows:
            print(f"  {row}")
        print(rule(accent="─", width=width))


def banner():
    """Display Miliciano banner. Compact mode: single line."""
    if is_compact():
        # Compact: 1-line banner
        print(f"{VIOLET}{BOLD}Miliciano{RESET} {DIM}|{RESET} partner tecnológico by Milytics")
    else:
        # Normal: full ASCII art
        width = terminal_width()
        art = dedent(f"""
        {PURPLE}{BOLD}███╗   ███╗██╗██╗     ██╗ ██████╗██╗ █████╗ ███╗   ██╗ ██████╗{RESET}
        {PURPLE}{BOLD}████╗ ████║██║██║     ██║██╔════╝██║██╔══██╗████╗  ██║██╔═══██╗{RESET}
        {VIOLET}{BOLD}██╔████╔██║██║██║     ██║██║     ██║███████║██╔██╗ ██║██║   ██║{RESET}
        {VIOLET}{BOLD}██║╚██╔╝██║██║██║     ██║██║     ██║██╔══██║██║╚██╗██║██║   ██║{RESET}
        {SOFT}{BOLD}██║ ╚═╝ ██║██║███████╗██║╚██████╗██║██║  ██║██║ ╚████║╚██████╔╝{RESET}
        {SOFT}{BOLD}╚═╝     ╚═╝╚═╝╚══════╝╚═╝ ╚═════╝╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝{RESET}
        """).strip()
        print(rule(accent="═", width=width))
        print(art, flush=True)
        print(f"{VIOLET}{BOLD}Miliciano{RESET} {DIM}·{RESET} {SOFT}tu partner tecnológico by Milytics{RESET}")
        print(f"{DIM}Interfaz táctica de razonamiento y ejecución{RESET}")
        print(rule(accent="─", width=width))


def session_frame(title="SESIÓN MILICIANO ACTIVA", subtitle="Ctrl+C o /exit para volver al terminal"):
    width = terminal_width()
    print(rule(f" {title} ", "═", width))
    print(split_columns(f"{BOLD}Modo:{RESET} chat operativo", f"{SOFT}{subtitle}{RESET}", width))
    print(rule(accent="─", width=width))


def shell_status_bar(mode, engine=None, detail=None, width=None):
    width = width or terminal_width()
    mode_label = (mode or "reasoning").upper()
    engine_label = engine or "Hermes"
    left = f"{BOLD}modo{RESET} {YELLOW}{mode_label}{RESET} {DIM}|{RESET} {BOLD}motor{RESET} {engine_label}"
    right = detail or "Ctrl+T / Shift+Tab / Alt+M cambia modo"
    return split_columns(left, f"{DIM}{right}{RESET}", width)


def response_meta_line(result, mode=None):
    result = result or {}
    provider = result.get("provider") or "n/d"
    model = result.get("model") or "n/d"
    route_used = result.get("route_used") or mode or "n/d"
    transport_mode = result.get("transport_mode")
    payload_chars = result.get("payload_chars")
    parts = [f"modo {route_used}", f"motor {provider}/{model}"]
    if transport_mode:
        parts.append(f"envío {transport_mode}")
    if payload_chars:
        parts.append(f"payload {payload_chars} chars")
    session_id = result.get("session_id")
    if session_id and transport_mode == "resumed":
        parts.append(f"sesión {session_id}")
    print(f"{DIM}↳ {' · '.join(parts)}{RESET}")


def _contains_ansi(text):
    return bool(ANSI_RE.search(str(text)))


def _visible_len(text):
    return len(ANSI_RE.sub("", text))


def _wrap_plain_text(text, width, indent="", subsequent_indent=None):
    clean = str(text)
    if clean == "":
        return [indent.rstrip()]
    return wrap(
        clean,
        width=max(8, width),
        initial_indent=indent,
        subsequent_indent=subsequent_indent if subsequent_indent is not None else indent,
        replace_whitespace=False,
        drop_whitespace=True,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [indent + clean]


def _wrap_ansi_text(text, width, indent="", subsequent_indent=None):
    lines = []
    for raw in str(text).splitlines() or [""]:
        if raw.strip() == "":
            lines.append(indent.rstrip())
            continue
        if _contains_ansi(raw):
            lines.append(f"{indent}{raw}")
            continue
        lines.extend(_wrap_plain_text(raw, width, indent=indent, subsequent_indent=subsequent_indent))
    return lines


def _soft_wrap_code_line(text, width):
    if width <= 0:
        return [text]
    if _visible_len(text) <= width:
        return [text]
    chunks = []
    raw = str(text)
    while raw:
        chunks.append(raw[:width])
        raw = raw[width:]
    return chunks


def _parse_response_blocks(text):
    lines = str(text).splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == "":
            i += 1
            continue

        fence_match = CODE_FENCE_RE.match(stripped)
        if fence_match:
            fence = fence_match.group(1)
            info = fence_match.group(2).strip()
            code_lines = []
            i += 1
            while i < len(lines):
                current = lines[i]
                if current.strip().startswith(fence):
                    i += 1
                    break
                code_lines.append(current)
                i += 1
            blocks.append({"type": "code", "lines": code_lines, "info": info})
            continue

        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading_match.group(1)),
                    "text": heading_match.group(2),
                }
            )
            i += 1
            continue

        if set(stripped) == {"-"} and len(stripped) >= 3:
            blocks.append({"type": "rule"})
            i += 1
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines):
                current = lines[i].strip()
                if not current.startswith(">"):
                    break
                quote_lines.append(current[1:].lstrip())
                i += 1
            blocks.append({"type": "quote", "lines": quote_lines})
            continue

        if LIST_RE.match(line):
            items = []
            current_item = None
            while i < len(lines):
                current = lines[i]
                if current.strip() == "":
                    break
                if CODE_FENCE_RE.match(current.strip()) or HEADING_RE.match(current.strip()) or (set(current.strip()) == {"-"} and len(current.strip()) >= 3):
                    break
                list_match = LIST_RE.match(current)
                if list_match:
                    current_item = {
                        "marker": list_match.group(2),
                        "text_lines": [list_match.group(3)],
                    }
                    items.append(current_item)
                elif current_item is not None:
                    current_item["text_lines"].append(current.strip())
                else:
                    break
                i += 1
            blocks.append({"type": "list", "items": items})
            continue

        paragraph_lines = []
        while i < len(lines):
            current = lines[i]
            current_stripped = current.strip()
            if current_stripped == "":
                break
            if (
                CODE_FENCE_RE.match(current_stripped)
                or HEADING_RE.match(current_stripped)
                or current_stripped.startswith(">")
                or LIST_RE.match(current)
                or (set(current_stripped) == {"-"} and len(current_stripped) >= 3)
            ):
                break
            paragraph_lines.append(current_stripped)
            i += 1
        blocks.append({"type": "paragraph", "text": " ".join(paragraph_lines)})

    return blocks


def _render_response_blocks(blocks, width, compact=False, tactical=True):
    inner_width = max(24, width - 2)
    lines = []
    for index, block in enumerate(blocks):
        if index > 0:
            lines.append("")

        if block["type"] == "heading":
            marker = "#" * block["level"] if compact else ""
            palette = {1: YELLOW, 2: CYAN, 3: SOFT}
            color = palette.get(block["level"], SOFT) if tactical else ""
            prefix = f"{marker} " if marker else ""
            rendered = f"{prefix}{block['text']}".strip()
            style = f"{BOLD}{color}" if tactical else ""
            suffix = RESET if tactical else ""
            lines.append(f"{style}{rendered}{suffix}")
            continue

        if block["type"] == "rule":
            accent = "─" if compact else "━"
            color = DIM if compact else VIOLET
            lines.append(f"{color}{accent * inner_width}{RESET}" if tactical else accent * inner_width)
            continue

        if block["type"] == "quote":
            prefix = f"{DIM}│{RESET} " if tactical else "> "
            quote_width = max(12, inner_width - 2)
            quote_text = "\n".join(block["lines"]).strip()
            if _contains_ansi(quote_text):
                lines.extend(_wrap_ansi_text(quote_text, quote_width, indent=prefix, subsequent_indent=prefix))
            else:
                lines.extend(_wrap_plain_text(quote_text, quote_width, indent=prefix, subsequent_indent=prefix))
            continue

        if block["type"] == "list":
            marker_color = SOFT if compact else CYAN
            item_width = max(12, inner_width - 4)
            for item in block["items"]:
                marker = item["marker"] if item["marker"].endswith(".") else "•"
                prefix = f"{marker} "
                if tactical:
                    prefix = f"{marker_color}{prefix}{RESET}"
                text = " ".join(part.strip() for part in item["text_lines"] if part.strip())
                if _contains_ansi(text):
                    lines.extend(
                        _wrap_ansi_text(
                            text,
                            item_width,
                            indent=prefix,
                            subsequent_indent="  ",
                        )
                    )
                else:
                    lines.extend(
                        _wrap_plain_text(
                            text,
                            item_width,
                            indent=prefix,
                            subsequent_indent="  ",
                        )
                    )
            continue

        if block["type"] == "code":
            edge = "│" if compact else "▌"
            info = f" {block['info']}" if block.get("info") else ""
            if not compact:
                top = f"{DIM}{'┌' + '─' * max(6, inner_width - 1)}{RESET}"
                lines.append(top[: len(top)])
            if info:
                lines.append(f"{DIM}{edge}{RESET}{DIM}{info}{RESET}")
            code_width = max(12, inner_width - 3)
            for raw in block["lines"] or [""]:
                wrapped_chunks = _soft_wrap_code_line(raw, code_width)
                for chunk in wrapped_chunks:
                    if tactical:
                        lines.append(f"{DIM}{edge}{RESET}{CODE_BG} {chunk.ljust(code_width)} {RESET}")
                    else:
                        lines.append(f"{edge} {chunk}")
            if not compact:
                bottom = f"{DIM}{'└' + '─' * max(6, inner_width - 1)}{RESET}"
                lines.append(bottom[: len(bottom)])
            continue

        text = block["text"]
        if _contains_ansi(text):
            lines.extend(_wrap_ansi_text(text, inner_width))
        else:
            lines.extend(_wrap_plain_text(text, inner_width))

    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _render_plain_response(text, width):
    blocks = []
    for paragraph in str(text).splitlines() or [""]:
        if paragraph.strip() == "":
            blocks.append("")
            continue
        blocks.extend(_wrap_ansi_text(paragraph, max(24, width - 2)))
    return blocks


def response_box(text, title=None):
    width = terminal_width()
    label = title or "Miliciano"
    compact = is_compact()
    tactical = response_style() == "tactical_markdown"

    if compact:
        print(f"\n== {label} ==")
    else:
        print(rule(f" {label} ", "─", width))

    if tactical and not _contains_ansi(text):
        body_lines = _render_response_blocks(_parse_response_blocks(text), width, compact=compact, tactical=True)
    else:
        body_lines = _render_plain_response(text, width)

    for line in body_lines:
        if compact:
            print(line)
        else:
            print(f"  {line}" if line else "")

    if not compact:
        print(rule(accent="─", width=width))


def activity_line(message, file_path=None):
    line = f"{SOFT}┊ {message}{RESET}"
    if file_path:
        line += f" {DIM}· {file_path}{RESET}"
    print(line)


def usage():
    banner()
    width = terminal_width()
    print(rule(" COMANDOS ", "─", width))
    print(f"  {BOLD}miliciano{RESET}                    abre la consola interactiva")
    print(f"  {BOLD}miliciano setup{RESET}              instala y deja configurado el stack base")
    print(f"  {BOLD}miliciano bootstrap{RESET}          alias operativo de setup --auto")
    print(f"  {BOLD}miliciano status{RESET}             solo muestra el estado actual, sin cambios")
    print(f"  {BOLD}miliciano repair{RESET}             repara wrappers, PATH y sincronización local")
    print(f"  {BOLD}miliciano model{RESET}              muestra o cambia el modelo activo")
    print(f"  {BOLD}miliciano route{RESET}              muestra o cambia el routing por rol")
    print(f"  {BOLD}miliciano auth{RESET}               muestra o gestiona credenciales/proveedores")
    print(f"  {BOLD}miliciano provider{RESET}           conecta/desconecta/activa providers")
    print(f"  {BOLD}miliciano obsidian{RESET}           muestra o sincroniza el cerebro en Obsidian")
    print(f"  {BOLD}miliciano doctor{RESET}             corre diagnóstico profundo del stack")
    print(f"  {BOLD}miliciano think{RESET} \"pregunta\"    razonamiento operativo")
    print(f"  {BOLD}miliciano exec{RESET} \"tarea\"       ejecución con OpenClaw")
    print(f"  {BOLD}miliciano mission{RESET} \"objetivo\" planificación + traspaso a ejecución")
    print(f"  {BOLD}miliciano shell{RESET}              entra al chat táctico (Shift+Tab/Ctrl+T/Alt+M: reasoning|plan|unrestricted)")
    print(rule(" RUTEO OPERATIVO ", "─", width))
    print("  reasoning -> ruta principal remota para pensar")
    print("  execution -> modelo principal para ejecutar herramientas")
    print("  fast      -> ruta rápida solo si hay local decente disponible")
    print("  local     -> base offline en Ollama, solo para uso explícito")
    print("  fallback  -> respaldo remoto cuando falle el principal")
    print(rule(accent="─", width=width))
