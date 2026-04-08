#!/usr/bin/env python3
from textwrap import dedent, wrap
import os

PURPLE = "\033[38;5;141m"
VIOLET = "\033[38;5;177m"
SOFT = "\033[38;5;183m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def terminal_width(default=94):
    try:
        return max(72, min(default, os.get_terminal_size().columns - 2))
    except OSError:
        return default


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
    width = terminal_width()
    print(rule(f" {title} ", "─", width))
    for row in rows:
        print(f"  {row}")
    print(rule(accent="─", width=width))


def banner():
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


def response_box(text, title=None):
    width = terminal_width()
    label = title or "Miliciano"
    print(rule(f" {label} ", "─", width))
    blocks = []
    for paragraph in str(text).splitlines() or [""]:
        if paragraph.strip() == "":
            blocks.append("")
            continue
        blocks.extend(wrap(paragraph, width=max(52, width - 2)))
    for line in blocks:
        print(f"  {line}")
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
    print(f"  {BOLD}miliciano setup{RESET}              revisa stack, prerequisitos y readiness")
    print(f"  {BOLD}miliciano status{RESET}             muestra estado de runtime, auth y backends")
    print(f"  {BOLD}miliciano model{RESET}              muestra o cambia el modelo activo")
    print(f"  {BOLD}miliciano route{RESET}              muestra o cambia el routing por rol")
    print(f"  {BOLD}miliciano auth{RESET}               muestra o gestiona credenciales/proveedores")
    print(f"  {BOLD}miliciano provider{RESET}           conecta/desconecta/activa providers")
    print(f"  {BOLD}miliciano obsidian{RESET}           muestra o sincroniza el cerebro en Obsidian")
    print(f"  {BOLD}miliciano doctor{RESET}             corre diagnóstico del stack")
    print(f"  {BOLD}miliciano think{RESET} \"pregunta\"    razonamiento operativo")
    print(f"  {BOLD}miliciano exec{RESET} \"tarea\"       ejecución con OpenClaw")
    print(f"  {BOLD}miliciano mission{RESET} \"objetivo\" planificación + traspaso a ejecución")
    print(f"  {BOLD}miliciano shell{RESET}              entra al chat táctico")
    print(rule(" RUTEO OPERATIVO ", "─", width))
    print("  reasoning -> ruta principal remota para pensar")
    print("  execution -> modelo principal para ejecutar herramientas")
    print("  fast      -> ruta rápida solo si hay local decente disponible")
    print("  local     -> base offline en Ollama, solo para uso explícito")
    print("  fallback  -> respaldo remoto cuando falle el principal")
    print(rule(accent="─", width=width))
