#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from shutil import which

from miliciano_agent import run_shell
from miliciano_constants import MILICIANO_HERMES_HOME, NVIDIA_BASE_URL, NVIDIA_DEFAULT_MODEL
from miliciano_obsidian import collect_obsidian_status
from miliciano_shell_input import shell_runtime_status
from miliciano_runtime import (
    PREREQ_COMMANDS,
    collect_nvidia_status,
    collect_ollama_status,
    load_miliciano_state,
    pull_ollama_model,
    run,
    save_miliciano_state,
)
from miliciano_setup_local import ensure_ollama_ready
from miliciano_setup_interactive import (
    maybe_configure_nvidia,
    maybe_resolve_openclaw_auth,
    maybe_review_nemoclaw,
)
from miliciano_setup_support import (
    TRUSTED_SOURCES,
    current_local_stack_snapshot,
    detect_openclaw_auth_state,
    download_and_verify_script,
    ensure_miliciano_soul,
    ensure_policy_config,
    repair_core_stack,
    repair_nemoclaw_wrapper,
    start_openclaw_gateway_detached,
    wait_for_openclaw_gateway_ready,
)
from miliciano_ui import (
    BOLD,
    RESET,
    SOFT,
    VIOLET,
    YELLOW,
    activity_line,
    banner,
    split_columns,
    status_badge,
)
from miliciano_validators import validate_install_url, ValidationError
from textwrap import wrap


def cmd_setup(args=None):
    from pathlib import Path
    from shutil import which

    args = args or []
    dry_run = "--dry-run" in args
    auto_mode = (
        any(flag in args for flag in {"--auto", "--yes", "-y", "--noninteractive"})
        or os.environ.get("MILICIANO_SETUP_AUTO", "0").strip().lower() in {"1", "true", "yes", "on"}
        or not (sys.stdin.isatty() and sys.stdout.isatty())
    )

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
    if dry_run:
        box_line("Modo dry-run: mostraré diagnóstico y reparaciones previstas sin cambiar el sistema.")
    box_rule()
    box_line("Cargando información del entorno...")
    box_line("• Reparando configuración base de Miliciano")
    for action in repair_core_stack(auto_install=auto_mode, dry_run=dry_run):
        box_line(f"• {action}")
    box_line("• Revisando prerequisitos base del sistema")

    snapshot = current_local_stack_snapshot()
    runtime = snapshot["runtime"]
    runtime_ready = snapshot["runtime_ready"]
    python_system = snapshot["python_system"]
    docker_ready = snapshot["docker_ready"]
    local_hw = snapshot["local_hw"]
    ollama_status = snapshot["ollama_status"]
    ollama_recos = snapshot["ollama_recos"]
    local_base_model = snapshot["local_base_model"]
    local_model_ready = snapshot["local_model_ready"]
    box_line("• Revisando perfil e identidad de Miliciano")
    shell_ui = shell_runtime_status()

    profile_dir = Path(MILICIANO_HERMES_HOME)
    soul_path = profile_dir / "SOUL.md"

    hermes_installed = which("hermes") is not None
    hermes_already = hermes_installed

    profile_preexisting = profile_dir.exists()
    profile_ok = profile_preexisting
    profile_detail = f"Perfil detectado en {profile_dir}" if profile_ok else "No existe el perfil miliciano"
    profile_action = "Sin cambios"
    if hermes_installed and not profile_ok:
        if dry_run:
            create = None
            profile_action = "Dry-run: se crearía automáticamente"
        else:
            create = run(["hermes", "profile", "create", "miliciano", "--clone", "--no-alias"], capture=True)
        if create and create.returncode == 0 and profile_dir.exists():
            profile_ok = True
            profile_detail = f"Perfil creado en {profile_dir}"
            profile_action = "Creado automáticamente"
        elif create:
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
            if dry_run:
                gateway_action = "Dry-run: intentaría levantar el gateway con `openclaw gateway --force`"
                gateway_detail = "Gateway no estaba listo al momento del diagnóstico"
            else:
                starter = start_openclaw_gateway_detached()
                gateway_action = "Intenté levantar el gateway con `openclaw gateway --force`"
                if isinstance(starter, Exception):
                    gateway_detail = f"No pude iniciar el gateway: {starter}"
                else:
                    gateway_ok, gateway_detail = wait_for_openclaw_gateway_ready()
                    if gateway_ok:
                        gateway_action = "Gateway levantado"
                    else:
                        gateway_detail = f"Gateway no responde ({gateway_detail})"

    auth_ok = False
    auth_detail = "OpenClaw no instalado"
    auth_action = "Revisión solamente"
    if openclaw_installed:
        model_status = run(["openclaw", "models", "status", "--plain"], capture=True)
        current_model = (model_status.stdout or "").strip()
        auth_store_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
        auth_store_text = auth_store_path.read_text() if auth_store_path.exists() else ""
        if "openai-codex" in auth_store_text and current_model.startswith("openai/"):
            if dry_run:
                auth_action = "Dry-run: ajustaría el modelo por defecto a openai-codex/gpt-5.4"
            else:
                fix_model = run(["openclaw", "models", "set", "openai-codex/gpt-5.4"], capture=True)
                if fix_model.returncode == 0:
                    activity_line("Modelo por defecto ajustado", "~/.openclaw/openclaw.json")
                    auth_action = "Ajusté el modelo por defecto a openai-codex/gpt-5.4"
                    current_model = "openai-codex/gpt-5.4"
        auth_ok, auth_detail, auth_snapshot = detect_openclaw_auth_state()
        if auth_ok and auth_action == "Revisión solamente":
            auth_action = "Ya estaba configurada"
        elif auth_action == "Revisión solamente":
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

    step_title(1.5, "Runtime Python local")
    box_line(f"Estado: {status_label(python_system['ok'], python_system['ok'])}")
    box_line(f"Detalle: {python_system['detail']}")
    if python_system["missing"]:
        box_line("Siguiente paso: dejar Python con pip/venv/ensurepip antes de instalar dependencias locales del shell.")

    step_title(1.6, "Shell interactivo")
    box_line(f"Estado: {status_label(shell_ui['available'], shell_ui['available'])}")
    box_line(f"Detalle: {shell_ui['detail']}")
    if not shell_ui["available"]:
        box_line(f"Siguiente paso: {shell_ui.get('action') or 'reparar runtime Python local'}")

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
        openclaw_install_cmd = os.environ.get("MILICIANO_OPENCLAW_INSTALL_CMD", "").strip()
        openclaw_install_url = os.environ.get("MILICIANO_OPENCLAW_INSTALL_URL", "").strip()
        if auto_mode:
            box_line("Intentando instalar OpenClaw automáticamente...")
            if openclaw_install_cmd:
                # WARNING: Custom install commands from env vars are dangerous
                # Only basic validation - users must ensure command is safe
                if any(dangerous in openclaw_install_cmd.lower() for dangerous in ["rm -rf", "curl |", "wget |", "eval"]):
                    box_line("❌ Error: Install command contains dangerous patterns")
                    box_line(f"Rejected command: {openclaw_install_cmd}")
                    return False, "Comando de instalación rechazado por seguridad"
                install_run = run(["bash", "-lc", openclaw_install_cmd], capture=True, timeout=600)
            elif openclaw_install_url:
                # Validate URL before using
                try:
                    validated_url = validate_install_url(openclaw_install_url)
                    box_line(f"Descargando desde: {validated_url}")
                    script_path = download_and_verify_script(validated_url)
                    try:
                        install_run = run(["bash", script_path], capture=True, timeout=600)
                    finally:
                        try:
                            os.remove(script_path)
                        except:
                            pass
                except ValidationError as e:
                    box_line(f"❌ Error: {e}")
                    return False, f"URL de instalación no confiable: {openclaw_install_url}"
            else:
                install_run = run(["bash", "-lc", "npm install -g openclaw"], capture=True, timeout=600)
                if install_run.returncode != 0:
                    install_run = run(["bash", "-lc", "npm install -g openclaw@latest"], capture=True, timeout=600)
            if install_run.returncode == 0 and which("openclaw"):
                openclaw_installed = True
                openclaw_already = True
                box_line("OpenClaw quedó instalado.")
                health = run(["openclaw", "health", "--json"], capture=True)
                normalized = (health.stdout or "").lower().replace(" ", "")
                if health.returncode == 0 and '\"ok\":true' in normalized:
                    gateway_ok = True
                    gateway_was_up = True
                    gateway_detail = "Gateway local respondiendo"
                else:
                    starter = start_openclaw_gateway_detached()
                    gateway_action = "Intenté levantar el gateway con `openclaw gateway --force`"
                    if isinstance(starter, Exception):
                        gateway_detail = f"No pude iniciar el gateway: {starter}"
                    else:
                        gateway_ok, gateway_detail = wait_for_openclaw_gateway_ready()
                        if gateway_ok:
                            gateway_action = "Gateway levantado"
                        else:
                            gateway_detail = f"Gateway no responde ({gateway_detail})"
            else:
                out = (install_run.stdout or "").strip()
                if out:
                    box_line(out)
                box_line("OpenClaw sigue pendiente; falló la instalación automática.")
        else:
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

    # Setup policy configuration
    if dry_run:
        box_line("Política: [dry-run] verificaría o crearía ~/.config/miliciano/policy.yaml")
    else:
        policy_created, policy_msg = ensure_policy_config()
        box_line(f"Política: {policy_msg}")

    if not nemoclaw_ok:
        box_line("Siguiente paso: revisar o reparar el acceso de Nemoclaw desde Miliciano")
        box_line("Nota: Miliciano puede funcionar sin Nemoclaw en esta fase")
        box_line("Nota: Política de seguridad activa con fallback simple si Nemoclaw no disponible")

    ollama_status = (
        collect_ollama_status()
        if dry_run
        else ensure_ollama_ready(box_line, local_base_model, auto_mode, download_and_verify_script, TRUSTED_SOURCES)
    )
    local_model_ready = bool(ollama_status["path"] and ollama_status["api_ok"] and ollama_status["models"])

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
        if auto_mode and ollama_status["path"] and ollama_status["api_ok"]:
            box_line(f"Siguiente paso: descargar ahora {local_base_model} para dejar la base local lista")

    nvidia_status = collect_nvidia_status()

    step_title(10, "Fallback NVIDIA (opcional)")
    box_line(f"Estado: {status_label(nvidia_status['api_key_present'] or nvidia_status['enabled'], nvidia_status['enabled'])}")
    box_line(f"Detalle: {'API key detectada' if nvidia_status['api_key_present'] else 'Sin API key de NVIDIA configurada'}")
    box_line(f"Base URL: {nvidia_status['base_url']}")
    box_line(f"Modelo: {nvidia_status['model'] or 'sin definir'}")
    box_line("Nota: este fallback es opcional y solo se activa si lo habilitas en tu configuración local.")
    if not dry_run:
        nvidia_status = maybe_configure_nvidia(ask_yes_no, NVIDIA_BASE_URL, NVIDIA_DEFAULT_MODEL)

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

    if not auto_mode and sys.stdin.isatty() and sys.stdout.isatty() and ollama_status["path"] and ollama_status["api_ok"] and not ollama_status["models"]:
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

    if not dry_run:
        maybe_resolve_openclaw_auth(auto_mode, auth_can_offer_resolution, ask_yes_no)
        maybe_review_nemoclaw(
            auto_mode,
            nemoclaw_can_offer_resolution,
            ask_yes_no,
            TRUSTED_SOURCES["nemoclaw"]["url"],
            nemoclaw_wrapper,
            nemoclaw_on_path,
            nemoclaw_version_ok,
            nemoclaw_global_installed,
            nemoclaw_local_wrapper_exists,
            nemoclaw_global_bin,
        )

    setup_complete = reasoning_ok and execution_ok and local_model_ready
    if not dry_run and sys.stdin.isatty() and sys.stdout.isatty() and setup_complete:
        if ask_yes_no("\n¿Quieres entrar ahora al chat de Miliciano?", default=False):
            run_shell()


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
    box_line("Este comando no instala el stack completo del sistema, pero sí repara dependencias Python locales, wrappers y sincronización de rutas.")
    box_line("Si setup ya dejó todo bien, repair solo confirmará y alineará los componentes que puedan haberse roto.")
    box_line("")
    for action in repair_core_stack():
        box_line(f"• {action}")
    box_line("")
    box_line(f"Siguiente paso: usa {GREEN}miliciano status{RESET} para leer el estado y {GREEN}miliciano doctor{RESET} si quieres diagnóstico profundo.")
    box_line(f"Si falta algún binario externo, {YELLOW}repair{RESET} no inventa instalaciones del sistema operativo.")
    box_bottom()


def cmd_bootstrap(args=None):
    args = list(args or [])
    if not any(flag in args for flag in {"--auto", "--yes", "-y", "--noninteractive"}):
        args.append("--auto")
    cmd_setup(args)
