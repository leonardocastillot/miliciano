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
        "warn": "\033[38;5;214m",
    }
    labels = {
        "ready": "READY",
        "pending": "PENDING",
        "error": "ERROR",
        "info": "INFO",
        "warn": "WARN",
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
    print(f"  {BOLD}miliciano{RESET}                    abre la home diaria de Miliciano")
    print(f"  {BOLD}miliciano home{RESET}               abre la home diaria")
    print(f"  {BOLD}miliciano start{RESET}              alias de home")
    print(f"  {BOLD}miliciano day{RESET}                abre el comando diario de hoy")
    print(f"  {BOLD}miliciano today{RESET}              alias de day")
    print(f"  {BOLD}miliciano about{RESET}              muestra el pitch de producto")
    print(f"  {BOLD}miliciano task{RESET}               gestiona tu bandeja diaria de trabajo")
    print(f"  {BOLD}miliciano tasks{RESET}              alias de task")
    print(f"  {BOLD}miliciano jobs{RESET}               administra automatizaciones persistentes")
    print(f"  {BOLD}miliciano jobs scheduler{RESET}      corre jobs vencidos ahora o en loop")
    print(f"  {BOLD}miliciano setup{RESET}              revisa y repara el stack base")
    print(f"  {BOLD}miliciano shell{RESET}              entra al chat táctico")
    print(f"  {BOLD}miliciano setup --dry-run{RESET}    muestra el plan de correcciones sin aplicar cambios")
    print(f"  {BOLD}miliciano bootstrap{RESET}          instalación integral: prereqs + setup --auto")
    print(f"  {BOLD}miliciano bootstrap --dry-run{RESET} plan completo de instalación sin tocar el sistema")
    print(f"  {BOLD}miliciano status{RESET}             solo muestra el estado actual, sin cambios")
    print(f"  {BOLD}miliciano ask{RESET} \"pedido\"      entrada principal orquestada del partner")
    print(f"  {BOLD}miliciano boundary{RESET} \"pedido\" activación explícita del path outward / seguro")
    print(f"  {BOLD}miliciano trace{RESET}              muestra la última decisión del orquestador")
    print(f"  {BOLD}miliciano mode{RESET}               muestra o cambia modos de salida, costo y permisos")
    print(f"  {BOLD}miliciano identity{RESET}           muestra o cambia nombre, persona y estilo del partner")
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
    print(f"  {BOLD}miliciano shell{RESET}              entra al chat táctico")
    print(rule(" RUTEO OPERATIVO ", "─", width))
    print("  reasoning -> ruta principal remota para pensar")
    print("  execution -> modelo principal para ejecutar herramientas")
    print("  fast      -> ruta rápida solo si hay local decente disponible")
    print("  local     -> base offline en Ollama, solo para uso explícito")
    print("  fallback  -> respaldo remoto cuando falle el principal")
    print(rule(" MODOS DE PRODUCTO ", "─", width))
    print("  output    -> simple | operator | debug")
    print("  route     -> cheap | balanced | max")
    print("  permission -> plan | ask | accept-edits | execute | restricted-boundary")
    print(rule(accent="─", width=width))
