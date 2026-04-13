#!/usr/bin/env python3
import os

from miliciano_runtime import collect_nvidia_status, load_miliciano_state, run, save_miliciano_state
from miliciano_setup_support import detect_openclaw_auth_state, download_and_verify_script
from miliciano_ui import BOLD, RESET, SOFT, VIOLET, YELLOW, activity_line


def maybe_configure_nvidia(ask_yes_no, nvidia_base_url, nvidia_default_model):
    nvidia_status = collect_nvidia_status()
    if not (os.sys.stdin.isatty() and os.sys.stdout.isatty()) or not nvidia_status["api_key_present"] or nvidia_status["enabled"]:
        return nvidia_status
    if ask_yes_no("¿Quieres activar ahora el fallback NVIDIA con este modelo?", default=False):
        state = load_miliciano_state()
        state.setdefault("nvidia", {})["enabled"] = True
        state["nvidia"]["api_key_present"] = True
        state["nvidia"]["base_url"] = nvidia_base_url
        state["nvidia"]["model"] = nvidia_status["model"] or nvidia_default_model
        state.setdefault("routing", {})["fallback"] = f"nvidia/{state['nvidia']['model']}"
        save_miliciano_state(state)
        nvidia_status = collect_nvidia_status()
        print(f"  \033[38;5;84mListo:\033[0m fallback NVIDIA activado.")
    return nvidia_status


def maybe_resolve_openclaw_auth(auto_mode, auth_can_offer_resolution, ask_yes_no):
    if auto_mode or not (os.sys.stdin.isatty() and os.sys.stdout.isatty()) or not auth_can_offer_resolution:
        return
    if not ask_yes_no("\n¿Quieres resolver ahora las credenciales de ejecución desde Miliciano?", default=True):
        return
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
        return

    try:
        if choice == "1":
            env_key = os.environ.get("OPENAI_API_KEY")
            if not env_key:
                print(f"  {YELLOW}No encontré OPENAI_API_KEY en esta sesión.{RESET}")
                return
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
            return
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}Configuración cancelada. Volviendo a Miliciano...{RESET}")
        return

    if auth_run is not None:
        auth_ok, _, _ = detect_openclaw_auth_state()
        if auth_ok:
            print(f"  \033[38;5;84mListo:\033[0m la auth quedó configurada.")
        else:
            print(f"  {YELLOW}Aún pendiente:{RESET} puedes reintentar el setup cuando quieras.")


def maybe_review_nemoclaw(auto_mode, nemoclaw_can_offer_resolution, ask_yes_no, nemoclaw_url, nemoclaw_wrapper, nemoclaw_on_path, nemoclaw_version_ok, nemoclaw_global_installed, nemoclaw_local_wrapper_exists, nemoclaw_global_bin):
    if auto_mode or not (os.sys.stdin.isatty() and os.sys.stdout.isatty()) or not nemoclaw_can_offer_resolution:
        return
    while True:
        if not ask_yes_no("\n¿Quieres revisar ahora Nemoclaw desde Miliciano?", default=True):
            print(f"  {SOFT}Nemoclaw sigue pendiente.{RESET}")
            break
        print(f"\n{VIOLET}{BOLD}Opciones para Nemoclaw:{RESET}")
        if nemoclaw_on_path or nemoclaw_global_installed or nemoclaw_local_wrapper_exists:
            print("  1) Diagnosticar el estado actual")
            print("  2) Reparar acceso en PATH / wrapper")
            print("  3) Limpiar wrapper roto de ~/.local/bin")
            print("  4) Dejarlo pendiente por ahora")
            max_choice = 4
        else:
            print("  1) Diagnosticar el estado actual")
            print("  2) Instalar desde NVIDIA (nvidia.com/nemoclaw)")
            print("  3) Reparar acceso en PATH / wrapper")
            print("  4) Limpiar wrapper roto de ~/.local/bin")
            print("  5) Dejarlo pendiente por ahora")
            max_choice = 5
        try:
            choice = input(f"Elige una opción [1-{max_choice}]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {YELLOW}Cancelado.{RESET}")
            break

        if choice == "1":
            print(f"  {YELLOW}Diagnóstico:{RESET} on_path: {'sí' if nemoclaw_on_path else 'no'} · global_bin: {'sí' if nemoclaw_global_installed else 'no'} · wrapper local: {'sí' if nemoclaw_local_wrapper_exists else 'no'}")
            if nemoclaw_on_path:
                print("  Comando operativo o parcialmente expuesto en PATH.")
            elif nemoclaw_global_installed:
                print(f"  Hay instalación global, pero el binario no quedó expuesto en PATH: {nemoclaw_global_bin}")
            elif nemoclaw_local_wrapper_exists:
                print(f"  Hay wrapper local, pero no está visible como comando: {nemoclaw_wrapper}")
            else:
                print("  No detecté instalación real de Nemoclaw en este sistema.")
            continue
        if choice == "2" and not (nemoclaw_on_path or nemoclaw_global_installed or nemoclaw_local_wrapper_exists):
            print(f"\n{VIOLET}{BOLD}Instalando Nemoclaw desde NVIDIA...{RESET}")
            print(f"{SOFT}Fuente oficial: {nemoclaw_url}{RESET}")
            try:
                script_path = download_and_verify_script(nemoclaw_url)
                try:
                    install_run = run(["bash", script_path])
                finally:
                    try:
                        os.remove(script_path)
                    except Exception:
                        pass
            except Exception as exc:
                print(f"❌ Error descargando instalador: {exc}")
                continue
            if install_run.returncode == 0:
                activity_line("Nemoclaw instalado desde NVIDIA", str(nemoclaw_wrapper))
                print(f"  \033[38;5;84mListo:\033[0m Nemoclaw quedó operativo.")
                break
            print(f"  {YELLOW}Nemoclaw aún no quedó operativo.{RESET}")
            continue
        if choice in {"2", "3"}:
            print(f"  {SOFT}Usa `miliciano repair` para reparar o limpiar wrappers de Nemoclaw.{RESET}")
            continue
        print(f"  {SOFT}Dejado pendiente.{RESET}")
        break
