#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from shutil import which

from miliciano_runtime import *
from miliciano_ui import *
from miliciano_obsidian import *

SOUL_TEMPLATE = """# Miliciano SOUL

Perfil mínimo del espacio personal de Miliciano.

- Producto: Miliciano
- Marca: Milytics
- Rol: CLI/chat táctico
- Objetivo: razonar, ejecutar y dejar trazabilidad
- Estado: este archivo se crea o repara durante setup/repair
"""


def ensure_miliciano_soul(profile_dir):
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    soul_path = profile_dir / "SOUL.md"
    if soul_path.exists():
        return False, f"SOUL.md presente en {soul_path}"
    soul_path.write_text(SOUL_TEMPLATE, encoding="utf-8")
    activity_line("SOUL.md creado", str(soul_path))
    return True, f"SOUL.md creado en {soul_path}"


def repair_nemoclaw_wrapper():
    wrapper = Path.home() / ".local" / "bin" / "nemoclaw"
    npm_prefix_res = run(["npm", "prefix", "-g"], capture=True, timeout=10)
    npm_prefix = (npm_prefix_res.stdout or "").strip().splitlines()[-1].strip() if npm_prefix_res and npm_prefix_res.returncode == 0 else ""
    npm_global_bin = Path(npm_prefix) / "bin" if npm_prefix else None
    global_candidate = (npm_global_bin / "nemoclaw") if npm_global_bin else None

    if not global_candidate or not global_candidate.exists():
        if wrapper.exists():
            return False, f"No detecté binario global de Nemoclaw para reparar {wrapper}"
        return False, "No detecté una instalación global de Nemoclaw"

    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper_content = """#!/usr/bin/env bash
set -euo pipefail
if command -v npm >/dev/null 2>&1; then
  NPM_PREFIX="$(npm prefix -g 2>/dev/null | tail -n 1)"
  if [ -n "$NPM_PREFIX" ] && [ -x "$NPM_PREFIX/bin/nemoclaw" ]; then
    exec "$NPM_PREFIX/bin/nemoclaw" "$@"
  fi
fi
if command -v nemoclaw >/dev/null 2>&1; then
  exec "$(command -v nemoclaw)" "$@"
fi
printf '[Nemoclaw] existe instalación, pero no está expuesta correctamente en PATH.\\n' >&2
exit 1
"""
    wrapper.write_text(wrapper_content, encoding="utf-8")
    os.chmod(wrapper, 0o755)
    activity_line("Wrapper de Nemoclaw reparado", str(wrapper))
    return True, f"Wrapper recreado en {wrapper}"


def repair_core_stack():
    state = load_miliciano_state(refresh=True)
    actions = []

    hermes_provider = state["hermes"]["provider"]
    hermes_model = state["hermes"]["model"]
    sync_hermes_global_config(hermes_provider, hermes_model)
    sync_hermes_profile_config(hermes_provider, hermes_model)
    actions.append(f"Hermes sincronizado en {hermes_provider}/{hermes_model}")

    profile_dir = Path(MILICIANO_HERMES_HOME)
    profile_dir.mkdir(parents=True, exist_ok=True)
    if Path(MILICIANO_HERMES_HOME).exists() and not Path(MILICIANO_HERMES_HOME).joinpath("SOUL.md").exists():
        created, detail = ensure_miliciano_soul(profile_dir)
        actions.append(detail)
    else:
        actions.append(f"SOUL.md presente en {Path(MILICIANO_HERMES_HOME) / 'SOUL.md'}")

    openclaw_path = which("openclaw")
    if openclaw_path:
        current_model = state["openclaw"]["model"]
        run(["openclaw", "models", "set", current_model], capture=True, timeout=12)
        ok, detail = sync_openclaw_fallback_route(state)
        actions.append(f"OpenClaw alineado a {current_model}")
        actions.append(detail)
    else:
        actions.append("OpenClaw no instalado; no pude re-alinear execution/fallback")

    repaired, nemo_detail = repair_nemoclaw_wrapper()
    actions.append(nemo_detail)
    if repaired:
        activity_line("Repair completado", "Nemoclaw / configs / fallback")
    return actions


def cmd_setup():
    from pathlib import Path
    from shutil import which

    GREEN = "\033[38;5;84m"
    YELLOW = "\033[38;5;221m"
    RED = "\033[38;5;203m"
    CYAN = "\033[38;5;117m"

    BOX_WIDTH = 74

    def box_top(title="SETUP MILICIANO", subtitle="Ctrl+C para salir del setup"):
        print(f"{VIOLET}{'═' * BOX_WIDTH}{RESET}")
        print(split_columns(f"{BOLD}{title}{RESET}", f"{SOFT}{subtitle}{RESET}", BOX_WIDTH))
        print(f"{VIOLET}{'─' * BOX_WIDTH}{RESET}")

    def box_rule():
        print(f"{VIOLET}{'─' * BOX_WIDTH}{RESET}")

    def box_line(text=""):
        lines = wrap(text, width=BOX_WIDTH) if text else [""]
        for line in lines:
            print(line)

    def box_bottom():
        print(f"{VIOLET}{'═' * BOX_WIDTH}{RESET}")

    def status_label(ok, already=False):
        if ok:
            return f"{GREEN}LISTO{RESET}"
        return f"{YELLOW}PENDIENTE{RESET}"

    def step_title(n, title):
        box_rule()
        box_line(f"PASO {n}. {title}")

    def ask_yes_no(question, default=True):
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        suffix = " [Y/n] " if default else " [y/N] "
        while True:
            try:
                answer = input(question + suffix).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False
            if not answer:
                return default
            if answer in {"y", "yes", "s", "si", "sí"}:
                return True
            if answer in {"n", "no"}:
                return False
            print("Responde y/s o n.")

    banner()
    box_top("SETUP MILICIANO", "Ctrl+C para salir del setup")
    box_line("Setup de Miliciano")
    box_line("Este comando revisa el stack, aplica lo que puede automáticamente y, si lo corres otra vez, te dice qué ya estaba instalado y qué falta.")
    box_rule()
    box_line("Cargando información del entorno...")
    box_line("• Reparando configuración base de Miliciano")
    for action in repair_core_stack():
        box_line(f"• {action}")
    box_line("• Revisando prerequisitos base del sistema")

    runtime = basic_runtime_status()
    runtime_ready = all(runtime[cmd]["path"] for cmd in PREREQ_COMMANDS)
    docker_ready = runtime["docker"]["path"] is not None
    local_hw = collect_local_ai_hardware()
    ollama_status = collect_ollama_status()
    ollama_recos = recommend_ollama_models(local_hw)
    local_base_model = ollama_recos[0][0]
    local_model_ready = bool(ollama_status["path"] and ollama_status["api_ok"] and ollama_status["models"])
    box_line("• Revisando perfil e identidad de Miliciano")

    profile_dir = Path(MILICIANO_HERMES_HOME)
    soul_path = profile_dir / "SOUL.md"

    hermes_installed = which("hermes") is not None
    hermes_already = hermes_installed

    profile_preexisting = profile_dir.exists()
    profile_ok = profile_preexisting
    profile_detail = f"Perfil detectado en {profile_dir}" if profile_ok else "No existe el perfil miliciano"
    profile_action = "Sin cambios"
    if hermes_installed and not profile_ok:
        create = run(["hermes", "profile", "create", "miliciano", "--clone", "--no-alias"], capture=True)
        if create.returncode == 0 and profile_dir.exists():
            profile_ok = True
            profile_detail = f"Perfil creado en {profile_dir}"
            profile_action = "Creado automáticamente"
        else:
            create_out = (create.stdout or "").strip()
            profile_action = "No se pudo crear automáticamente"
            if create_out:
                profile_detail = create_out.splitlines()[-1]

    soul_preexisting = soul_path.exists()
    soul_ok = soul_preexisting
    soul_detail = "SOUL.md presente" if soul_ok else "Falta SOUL.md del perfil"
    soul_action = "Sin cambios"

    openclaw_installed = which("openclaw") is not None
    openclaw_already = openclaw_installed

    nemoclaw_wrapper = Path.home() / ".local" / "bin" / "nemoclaw"
    npm_prefix_res = run(["npm", "prefix", "-g"], capture=True, timeout=10)
    npm_prefix = (npm_prefix_res.stdout or "").strip().splitlines()[-1].strip() if npm_prefix_res and npm_prefix_res.returncode == 0 else ""
    npm_global_bin = Path(npm_prefix) / "bin" if npm_prefix else None
    nemoclaw_global_bin = (npm_global_bin / "nemoclaw") if npm_global_bin else None
    nemoclaw_on_path = which("nemoclaw") is not None
    nemoclaw_path = which("nemoclaw")
    nemoclaw_version_probe = run(["nemoclaw", "--version"], capture=True, timeout=6) if nemoclaw_on_path else None
    nemoclaw_version_ok = bool(nemoclaw_version_probe and nemoclaw_version_probe.returncode == 0)
    nemoclaw_global_installed = bool(nemoclaw_global_bin and nemoclaw_global_bin.exists())
    nemoclaw_local_wrapper_exists = nemoclaw_wrapper.exists()
    nemoclaw_installed_anywhere = nemoclaw_on_path or nemoclaw_global_installed or nemoclaw_local_wrapper_exists
    nemoclaw_ok = False
    nemoclaw_detail = "No encontrado"
    nemoclaw_action = "Sin cambios"
    if nemoclaw_on_path and nemoclaw_version_ok:
        nemoclaw_ok = True
        nemoclaw_detail = f"Operativo ({nemoclaw_path})"
    elif nemoclaw_on_path:
        nemoclaw_detail = f"Comando encontrado en PATH, pero falla `nemoclaw --version` ({nemoclaw_path})"
        nemoclaw_action = "Revisar wrapper o binario real"
    elif nemoclaw_global_installed:
        nemoclaw_detail = f"Instalado globalmente, pero sin comando expuesto en PATH ({nemoclaw_global_bin})"
        nemoclaw_action = "Reparar wrapper o PATH"
    elif nemoclaw_local_wrapper_exists:
        nemoclaw_detail = f"Wrapper local presente pero el comando no quedó visible en PATH ({nemoclaw_wrapper})"
        nemoclaw_action = "Recrear wrapper o ajustar PATH"

    box_line("• Revisando motor de ejecución y conectividad")

    gateway_was_up = False
    gateway_ok = False
    gateway_detail = "OpenClaw no instalado"
    gateway_action = "Sin cambios"
    if openclaw_installed:
        health = run(["openclaw", "health", "--json"], capture=True)
        normalized = (health.stdout or "").lower().replace(" ", "")
        if health.returncode == 0 and '"ok":true' in normalized:
            gateway_ok = True
            gateway_was_up = True
            gateway_detail = "Gateway local respondiendo"
        else:
            start = run(["openclaw", "gateway", "start"], capture=True)
            gateway_action = "Intenté levantar el gateway"
            health = run(["openclaw", "health", "--json"], capture=True)
            normalized = (health.stdout or "").lower().replace(" ", "")
            if health.returncode == 0 and '"ok":true' in normalized:
                gateway_ok = True
                gateway_detail = "Gateway levantado durante este setup"
                gateway_action = "Gateway levantado"
            else:
                gateway_detail = "Gateway no responde"
                start_out = (start.stdout or "").strip()
                if start_out:
                    gateway_detail += f" ({start_out.splitlines()[-1]})"

    auth_ok = False
    auth_detail = "OpenClaw no instalado"
    auth_action = "Revisión solamente"
    if openclaw_installed:
        model_status = run(["openclaw", "models", "status", "--plain"], capture=True)
        current_model = (model_status.stdout or "").strip()
        auth_store_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
        auth_store_text = auth_store_path.read_text() if auth_store_path.exists() else ""
        if "openai-codex" in auth_store_text and current_model.startswith("openai/"):
            fix_model = run(["openclaw", "models", "set", "openai-codex/gpt-5.4"], capture=True)
            if fix_model.returncode == 0:
                activity_line("Modelo por defecto ajustado", "~/.openclaw/openclaw.json")
                auth_action = "Ajusté el modelo por defecto a openai-codex/gpt-5.4"
                current_model = "openai-codex/gpt-5.4"
        probe = run(["openclaw", "agent", "--agent", "main", "--message", "Responde solo OK"], capture=True)
        out = (probe.stdout or "")
        if probe.returncode == 0 and "No API key found for provider" not in out and "FailoverError:" not in out:
            auth_ok = True
            auth_detail = f"Auth de modelo lista ({current_model or 'modelo operativo'})"
            if auth_action == "Revisión solamente":
                auth_action = "Ya estaba configurada"
        else:
            auth_detail = "Falta auth de modelo en OpenClaw"
            if auth_action == "Revisión solamente":
                auth_action = "Requiere paso manual"

    step_title(1, "Prerequisitos base del sistema")
    box_line(f"Estado: {status_label(runtime_ready, runtime_ready)}")
    for cmd in PREREQ_COMMANDS:
        path = runtime[cmd]["path"]
        version = runtime[cmd]["version"]
        if path:
            detail = version or "Instalado"
            box_line(f"- {cmd}: OK · {detail}")
        else:
            box_line(f"- {cmd}: FALTA")
    if not runtime_ready:
        box_line("Siguiente paso: completar node, npm, curl y docker antes de cerrar el setup base")

    step_title(2, "Hermes")
    box_line(f"Estado: {status_label(hermes_installed, hermes_already)}")
    box_line(f"Detalle: {'Hermes instalado' if hermes_installed else 'Falta instalar Hermes'}")
    if not hermes_installed:
        box_line("Siguiente paso: instalar/configurar Hermes antes de continuar")

    step_title(3, "Perfil de Miliciano")
    box_line(f"Estado: {status_label(profile_ok, profile_preexisting)}")
    box_line(f"Detalle: {profile_detail}")
    box_line(f"Acción: {profile_action}")

    step_title(4, "Identidad pública")
    box_line(f"Estado: {status_label(soul_ok, soul_preexisting)}")
    box_line(f"Detalle: {soul_detail}")
    box_line(f"Acción: {soul_action}")

    step_title(5, "OpenClaw")
    box_line(f"Estado: {status_label(openclaw_installed, openclaw_already)}")
    box_line(f"Detalle: {'OpenClaw instalado' if openclaw_installed else 'Falta instalar OpenClaw'}")
    if not openclaw_installed:
        box_line("Siguiente paso: instalar OpenClaw")

    step_title(6, "Gateway de OpenClaw")
    box_line(f"Estado: {status_label(gateway_ok, gateway_was_up)}")
    box_line(f"Detalle: {gateway_detail}")
    box_line(f"Acción: {gateway_action}")

    auth_can_offer_resolution = (not auth_ok and openclaw_installed and gateway_ok)

    step_title(7, "Auth del modelo para ejecución")
    box_line(f"Estado: {status_label(auth_ok, auth_ok)}")
    box_line(f"Detalle: {auth_detail}")
    box_line(f"Acción: {auth_action}")
    if auth_can_offer_resolution:
        box_line("Siguiente paso: configurar credenciales de ejecución desde Miliciano")

    nemoclaw_can_offer_resolution = not nemoclaw_ok

    step_title(8, "Firewall / policy (Nemoclaw)")
    box_line(f"Estado: {status_label(nemoclaw_ok, nemoclaw_ok)}")
    box_line(f"Detalle: {nemoclaw_detail}")
    box_line(f"Acción: {nemoclaw_action}")
    box_line(f"Docker para Nemo: {'OK' if docker_ready else 'PENDIENTE'}")
    if not nemoclaw_ok:
        box_line("Siguiente paso: revisar o reparar el acceso de Nemoclaw desde Miliciano")
        box_line("Nota: Miliciano puede funcionar sin Nemoclaw en esta fase")

    step_title(9, "Inferencia local con Ollama")
    box_line(f"Estado: {status_label(local_model_ready, local_model_ready)}")
    box_line(f"Detalle: {ollama_status['version'] or 'Ollama no instalado'}")
    box_line(f"API local: {ollama_status['api_detail']}")
    box_line(
        f"Hardware: RAM {local_hw['ram_gib'] or 'n/d'} GiB · GPU {local_hw['gpu'] or 'n/d'} · VRAM {local_hw['gpu_vram_gib'] or 'n/d'} GiB"
    )
    box_line("Base operativa: Miliciano debe partir con al menos un modelo local en Ollama.")
    box_line("Escalamiento: después puedes sumar un proveedor pagado y dejar el local como fallback/base.")
    box_line("Recomendaciones para este equipo:")
    for model_name, reason in ollama_recos:
        box_line(f"- {model_name}: {reason}")
    if ollama_status["models"]:
        box_line(f"Modelos locales ya descargados: {', '.join(ollama_status['models'][:4])}")
    else:
        box_line("Modelos locales ya descargados: ninguno")
        if ollama_status["path"] and ollama_status["api_ok"]:
            box_line(f"Siguiente paso: descargar ahora {local_base_model} para dejar la base local lista")

    nvidia_status = collect_nvidia_status()

    step_title(10, "Fallback NVIDIA (opcional)")
    box_line(f"Estado: {status_label(nvidia_status['api_key_present'] or nvidia_status['enabled'], nvidia_status['enabled'])}")
    box_line(f"Detalle: {'API key detectada' if nvidia_status['api_key_present'] else 'Sin API key de NVIDIA configurada'}")
    box_line(f"Base URL: {nvidia_status['base_url']}")
    box_line(f"Modelo: {nvidia_status['model'] or 'sin definir'}")
    box_line("Nota: este fallback es opcional y solo se activa si lo habilitas en tu configuración local.")
    if sys.stdin.isatty() and sys.stdout.isatty() and nvidia_status["api_key_present"] and not nvidia_status["enabled"]:
        if ask_yes_no("¿Quieres activar ahora el fallback NVIDIA con este modelo?", default=False):
            state = load_miliciano_state()
            state.setdefault("nvidia", {})["enabled"] = True
            state["nvidia"]["api_key_present"] = True
            state["nvidia"]["base_url"] = NVIDIA_BASE_URL
            state["nvidia"]["model"] = nvidia_status["model"] or NVIDIA_DEFAULT_MODEL
            state.setdefault("routing", {})["fallback"] = f"nvidia/{state['nvidia']['model']}"
            save_miliciano_state(state)
            nvidia_status = collect_nvidia_status(refresh=True)
            print(f"  {GREEN}Listo:{RESET} fallback NVIDIA activado.")

    step_title(11, "Resumen")
    reasoning_ok = hermes_installed and profile_ok and soul_ok
    execution_ok = openclaw_installed and gateway_ok and auth_ok
    local_inference_ok = local_model_ready
    box_line(f"- reasoning: {'sí' if reasoning_ok else 'no'}")
    box_line(f"- execution: {'sí' if execution_ok else 'no'}")
    box_line(f"- firewall/policy: {'sí' if nemoclaw_ok else 'no'}")
    box_line(f"- inferencia local base: {'sí' if local_inference_ok else 'no'}")
    if auth_ok and auth_action == "Configurada durante este setup":
        box_line("- auth: configurada durante este setup")
    box_rule()
    box_line(f"runtime    {status_badge('ready' if runtime_ready else 'pending')}")
    box_line(f"reasoning  {status_badge('ready' if reasoning_ok else 'pending')}")
    box_line(f"execution  {status_badge('ready' if execution_ok else 'pending')}")
    box_line(f"local base {status_badge('ready' if local_inference_ok else 'pending')}")
    box_line(f"policy     {status_badge('ready' if nemoclaw_ok else 'pending')}")

    step_title(12, "Próximo paso recomendado")
    if not hermes_installed:
        box_line("- Completar la instalación base de Miliciano")
    elif not profile_ok or not soul_ok:
        box_line("- Completar la identidad y perfil de Miliciano")
    elif not openclaw_installed:
        box_line("- Resolver el motor de ejecución dentro del setup")
    elif not gateway_ok:
        box_line("- Reintentar el arranque del gateway desde Miliciano")
    elif not auth_ok:
        box_line("- Resolver las credenciales de ejecución dentro de Miliciano")
    elif not ollama_status["path"] or not ollama_status["api_ok"]:
        box_line(f"- Dejar Ollama operativo y partir con {local_base_model}")
    elif not ollama_status["models"]:
        box_line(f"- Descargar {local_base_model} en Ollama antes de hablar con Miliciano")
    elif not nemoclaw_ok:
        box_line("- Resolver la capa policy/firewall de Nemoclaw dentro de Miliciano")
    else:
        box_line("- Stack listo. Ya puedes usar Miliciano con base local y escalar a proveedor pagado cuando quieras")
    box_bottom()

    if sys.stdin.isatty() and sys.stdout.isatty() and ollama_status["path"] and ollama_status["api_ok"] and not ollama_status["models"]:
        if ask_yes_no(f"\nNo hay modelos locales en Ollama. ¿Quieres descargar ahora {local_base_model} como base de Miliciano?", default=True):
            pull = pull_ollama_model(local_base_model)
            if pull.returncode == 0:
                print(f"  {GREEN}Listo:{RESET} {local_base_model} quedó descargado en Ollama.")
                ollama_status = collect_ollama_status()
                local_model_ready = bool(ollama_status["models"])
            else:
                out = (pull.stdout or "").strip()
                print(f"  {YELLOW}No pude descargar {local_base_model}.{RESET}")
                if out:
                    print(out)

    if sys.stdin.isatty() and sys.stdout.isatty() and auth_can_offer_resolution:
        if ask_yes_no("\n¿Quieres resolver ahora las credenciales de ejecución desde Miliciano?", default=True):
            print(f"\n{VIOLET}{BOLD}Métodos disponibles:{RESET}")
            print("  1) Reutilizar la API de OpenAI detectada en esta sesión")
            print("  2) OAuth de OpenAI Codex")
            print("  3) Pegar token manualmente")
            print("  4) Login con GitHub Copilot")
            print("  5) Cancelar por ahora")
            try:
                choice = input("Elige una opción [1-5]: ").strip() or "1"
            except (EOFError, KeyboardInterrupt):
                print(f"\n  {YELLOW}Cancelado.{RESET}")
                choice = "5"

            try:
                if choice == "1":
                    env_key = os.environ.get("OPENAI_API_KEY")
                    if env_key:
                        print(f"\n{VIOLET}{BOLD}Reutilizando la credencial OpenAI detectada...{RESET}")
                        auth_cmd = (
                            "python3 - <<'PY'\n"
                            "import os, pty, sys\n"
                            "pid, fd = pty.fork()\n"
                            "if pid == 0:\n"
                            "    os.execvp('openclaw', ['openclaw','models','auth','paste-token','--provider','openai'])\n"
                            "buf = b''\n"
                            "token = (os.environ.get('OPENAI_API_KEY','') + '\\n').encode()\n"
                            "sent = False\n"
                            "while True:\n"
                            "    try:\n"
                            "        data = os.read(fd, 1024)\n"
                            "    except OSError:\n"
                            "        break\n"
                            "    if not data:\n"
                            "        break\n"
                            "    os.write(1, data)\n"
                            "    buf += data.lower()\n"
                            "    if (b'token' in buf or b'paste' in buf or b'api key' in buf) and not sent:\n"
                            "        os.write(fd, token)\n"
                            "        sent = True\n"
                            "_, status = os.waitpid(pid, 0)\n"
                            "sys.exit(os.waitstatus_to_exitcode(status))\n"
                            "PY"
                        )
                        auth_run = run(["bash", "-lc", auth_cmd])
                    else:
                        print(f"  {YELLOW}No encontré OPENAI_API_KEY en esta sesión.{RESET}")
                        auth_run = None
                elif choice == "2":
                    print(f"\n{VIOLET}{BOLD}Abriendo OAuth de OpenAI Codex...{RESET}")
                    auth_run = run(["openclaw", "models", "auth", "login", "--provider", "openai-codex"])
                elif choice == "3":
                    print(f"\n{VIOLET}{BOLD}Abriendo asistente para pegar token manualmente...{RESET}")
                    auth_run = run(["openclaw", "models", "auth", "paste-token"])
                elif choice == "4":
                    print(f"\n{VIOLET}{BOLD}Abriendo login de GitHub Copilot...{RESET}")
                    auth_run = run(["openclaw", "models", "auth", "login-github-copilot"])
                else:
                    auth_run = None
            except KeyboardInterrupt:
                print(f"\n  {YELLOW}Configuración cancelada. Volviendo a Miliciano...{RESET}")
                auth_run = None

            if auth_run is not None:
                probe = run(["openclaw", "agent", "--agent", "main", "--message", "Responde solo OK"], capture=True)
                out = (probe.stdout or "")
                if probe.returncode == 0 and "No API key found for provider" not in out and "FailoverError:" not in out:
                    print(f"  {GREEN}Listo:{RESET} la auth quedó configurada.")
                    auth_ok = True
                else:
                    print(f"  {YELLOW}Aún pendiente:{RESET} seguimos dentro de Miliciano; puedes reintentar el setup cuando quieras.")

    if sys.stdin.isatty() and sys.stdout.isatty() and nemoclaw_can_offer_resolution:
        while True:
            if not ask_yes_no("\n¿Quieres revisar ahora Nemoclaw desde Miliciano?", default=True):
                print(f"  {SOFT}Nemoclaw sigue pendiente.{RESET}")
                break
            print(f"\n{VIOLET}{BOLD}Opciones para Nemoclaw:{RESET}")
            print("  1) Diagnosticar el estado actual")
            if nemoclaw_installed_anywhere:
                print("  2) Reparar acceso en PATH / wrapper")
                print("  3) Limpiar wrapper roto de ~/.local/bin")
                print("  4) Dejarlo pendiente por ahora")
                max_choice = 4
            else:
                print("  2) Instalar desde NVIDIA (nvidia.com/nemoclaw)")
                print("  3) Reparar acceso en PATH / wrapper")
                print("  4) Limpiar wrapper roto de ~/.local/bin")
                print("  5) Dejarlo pendiente por ahora")
                max_choice = 5
            try:
                nemo_choice = input(f"Elige una opción [1-{max_choice}]: ").strip() or "1"
            except (EOFError, KeyboardInterrupt):
                print(f"\n  {YELLOW}Cancelado.{RESET}")
                nemo_choice = str(max_choice)

            if nemo_choice == "1":
                print(f"  {YELLOW}Diagnóstico:{RESET} on_path: {'sí' if nemoclaw_on_path else 'no'} · global_bin: {'sí' if nemoclaw_global_installed else 'no'} · wrapper local: {'sí' if nemoclaw_local_wrapper_exists else 'no'}")
                if nemoclaw_on_path:
                    probe_out = (nemoclaw_version_probe.stdout or "").strip() if nemoclaw_version_probe else ""
                    if nemoclaw_version_ok:
                        print(f"  Comando operativo en PATH: {nemoclaw_path}")
                    else:
                        print(f"  El comando existe pero `nemoclaw --version` falló: {probe_out or 'sin salida'}")
                elif nemoclaw_global_installed:
                    print(f"  Hay instalación global, pero el binario no quedó expuesto en PATH: {nemoclaw_global_bin}")
                elif nemoclaw_local_wrapper_exists:
                    print(f"  Hay wrapper local, pero no está visible como comando: {nemoclaw_wrapper}")
                else:
                    print("  No detecté instalación real de Nemoclaw en este sistema.")
                continue
            elif nemo_choice == "2" and not nemoclaw_installed_anywhere:
                print(f"\n{VIOLET}{BOLD}Instalando Nemoclaw desde NVIDIA...{RESET}")
                print(f"{SOFT}Fuente oficial: https://www.nvidia.com/nemoclaw.sh{RESET}")
                install_cmd = "curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash"
                install_run = run(["bash", "-lc", install_cmd])
                if install_run.returncode == 0:
                    nemoclaw_on_path = which("nemoclaw") is not None
                    if nemoclaw_on_path:
                        check = run(["nemoclaw", "--version"], capture=True)
                        if check.returncode == 0:
                            activity_line("Nemoclaw instalado desde NVIDIA", str(nemoclaw_wrapper))
                            nemoclaw_ok = True
                            nemoclaw_detail = f"Operativo ({which('nemoclaw')})"
                            nemoclaw_action = "Instalado desde NVIDIA"
                            print(f"  {GREEN}Listo:{RESET} Nemoclaw quedó operativo.")
                            break
                print(f"  {YELLOW}Nemoclaw aún no quedó operativo.{RESET} Revisa la salida del instalador o vuelve a intentar.")
                continue
            elif nemo_choice == "2" and nemoclaw_installed_anywhere:
                try:
                    if nemoclaw_on_path and nemoclaw_version_ok:
                        print(f"  {GREEN}Nemoclaw ya está operativo.{RESET} No hace falta reinstalar.")
                        break
                    nemoclaw_wrapper.parent.mkdir(parents=True, exist_ok=True)
                    wrapper_content = f'''#!/usr/bin/env bash
if command -v npm >/dev/null 2>&1; then
  NPM_PREFIX="$(npm prefix -g 2>/dev/null | tail -n 1)"
  if [ -n "$NPM_PREFIX" ] && [ -x "$NPM_PREFIX/bin/nemoclaw" ]; then
    exec "$NPM_PREFIX/bin/nemoclaw" "$@"
  fi
fi
if [ -x "$(command -v nemoclaw 2>/dev/null)" ]; then
  exec "$(command -v nemoclaw)" "$@"
fi
printf '[Nemoclaw] existe instalación, pero no está expuesta correctamente en PATH.\n' >&2
printf '[Nemoclaw] intenta ejecutar: npm prefix -g && ls -l "$NPM_PREFIX/bin/nemoclaw"\n' >&2
exit 1
'''
                    nemoclaw_wrapper.write_text(wrapper_content)
                    os.chmod(nemoclaw_wrapper, 0o755)
                    activity_line("Wrapper de acceso recreado", str(nemoclaw_wrapper))
                    print(f"  {GREEN}Listo:{RESET} recreé el wrapper en PATH para Nemoclaw.")
                    nemoclaw_on_path = True
                    nemoclaw_action = "Wrapper recreado"
                    nemoclaw_detail = f"Comando expuesto por wrapper local ({nemoclaw_wrapper})"
                except Exception as e:
                    print(f"  {YELLOW}No pude recrear el wrapper:{RESET} {e}")
                continue
            elif nemo_choice == "3":
                try:
                    if os.path.lexists(nemoclaw_wrapper):
                        os.remove(nemoclaw_wrapper)
                        activity_line("Wrapper roto eliminado", str(nemoclaw_wrapper))
                        print(f"  {GREEN}Listo:{RESET} eliminé el wrapper roto {nemoclaw_wrapper}.")
                        nemoclaw_on_path = False
                        nemoclaw_action = "Wrapper eliminado"
                        if nemoclaw_global_installed:
                            nemoclaw_detail = f"Instalado globalmente, pero sin comando expuesto en PATH ({nemoclaw_global_bin})"
                        else:
                            nemoclaw_detail = "No encontrado"
                    else:
                        print(f"  {YELLOW}Nada que limpiar:{RESET} no encontré wrapper en {nemoclaw_wrapper}.")
                except Exception as e:
                    print(f"  {YELLOW}No pude limpiar el wrapper:{RESET} {e}")
                continue
            else:
                print(f"  {SOFT}Dejado pendiente.{RESET}")
                break

    setup_complete = reasoning_ok and execution_ok and local_model_ready
    if sys.stdin.isatty() and sys.stdout.isatty() and setup_complete:
        if ask_yes_no("\n¿Quieres entrar ahora al chat de Miliciano?", default=False):
            interactive_chat()


def cmd_repair():
    GREEN = "\033[38;5;84m"
    YELLOW = "\033[38;5;221m"
    BOX_WIDTH = 74

    def box_top(title="REPAIR MILICIANO", subtitle="Corrige wrappers, configs y sincronización"):
        print(f"{VIOLET}{'═' * BOX_WIDTH}{RESET}")
        print(split_columns(f"{BOLD}{title}{RESET}", f"{SOFT}{subtitle}{RESET}", BOX_WIDTH))
        print(f"{VIOLET}{'─' * BOX_WIDTH}{RESET}")

    def box_line(text=""):
        lines = wrap(text, width=BOX_WIDTH) if text else [""]
        for line in lines:
            print(line)

    def box_bottom():
        print(f"{VIOLET}{'═' * BOX_WIDTH}{RESET}")

    banner()
    box_top()
    box_line("Repair de Miliciano")
    box_line("Este comando no instala el stack completo: repara la configuración local, wrappers y sincronización de rutas.")
    box_line("Si setup ya dejó todo bien, repair solo confirmará y alineará los componentes que puedan haberse roto.")
    box_line("")
    for action in repair_core_stack():
        box_line(f"• {action}")
    box_line("")
    box_line(f"Siguiente paso: usa {GREEN}miliciano status{RESET} para leer el estado y {GREEN}miliciano doctor{RESET} si quieres diagnóstico profundo.")
    box_line(f"Si falta algún binario externo, {YELLOW}repair{RESET} no inventa instalaciones del sistema operativo.")
    box_bottom()
