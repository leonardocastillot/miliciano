#!/usr/bin/env python3
import sys

from miliciano_constants import *
from miliciano_local import *
from miliciano_routing import *
from miliciano_state import *
from miliciano_system import *
from miliciano_ui import *


def get_permission_mode():
    state = load_miliciano_state()
    mode = state.get("preferences", {}).get("permission_mode", "execute")
    if mode not in ("execute", "confirm", "strict"):
        return "execute"
    return mode


def set_permission_mode(mode):
    if mode not in ("execute", "confirm", "strict"):
        raise ValueError(f"Invalid permission mode: {mode}. Must be execute, confirm, or strict.")
    state = load_miliciano_state()
    state.setdefault("preferences", {})["permission_mode"] = mode
    save_miliciano_state(state)


def ask_permission(message, action_type="execution"):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return True

    print(f"\n{YELLOW}[Permiso requerido]{RESET} {action_type}")
    print(f"{SOFT}Mensaje:{RESET} {message[:200]}{'...' if len(message) > 200 else ''}")

    while True:
        try:
            response = input(f"\n{BOLD}¿Permitir ejecución?{RESET} [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nOperación cancelada.")
            return False

        if response in ("", "y", "yes", "si", "s"):
            return True
        if response in ("n", "no"):
            return False
        print(f"{YELLOW}Respuesta no válida. Usa Y (sí) o n (no).{RESET}")


def basic_runtime_status():
    try:
        from miliciano_cache import cache_get, cache_set
        cached = cache_get("runtime_status", ttl_seconds=300)
        if cached is not None:
            return cached
    except ImportError:
        cache_set = None

    from shutil import which

    info = {}
    for cmd in PREREQ_COMMANDS:
        path = which(cmd)
        version = None
        if path:
            if cmd == "node":
                version = capture_version(["node", "-v"])
            elif cmd == "npm":
                version = capture_version(["npm", "-v"])
            elif cmd == "curl":
                version = capture_version(["curl", "--version"])
            elif cmd == "docker":
                version = capture_version(["docker", "--version"])
        info[cmd] = {"path": path, "version": version}

    if cache_set:
        cache_set("runtime_status", info)
    return info


def _check_policy_if_requested(message, check_policy):
    if not check_policy:
        return {"allowed": True, "reason": "policy_check_skipped"}

    from miliciano_policy import PolicyViolation, SimplePolicy, create_policy_engine

    action = {
        "type": "openclaw_agent",
        "agent": "main",
        "message": message,
        "command": message,
    }
    engine = create_policy_engine()
    if not engine.enabled and engine.policy_mode != "disabled":
        return SimplePolicy(mode=engine.policy_mode).check_command(message)
    try:
        result = engine.check_action(action)
    except PolicyViolation:
        try:
            result = SimplePolicy(mode=engine.policy_mode).check_command(message)
        except PolicyViolation as exc:
            engine.audit_log(action, {"allowed": False, "reason": str(exc)}, {"success": False, "blocked": True})
            raise
    return result


def run_openclaw_agent(message, check_policy=False):
    perm_mode = get_permission_mode()

    if perm_mode == "strict":
        if not ask_permission(message, "ejecución de agente"):
            print(f"{YELLOW}[Permiso denegado]{RESET} Ejecución cancelada por el usuario.")
            return 1, "Ejecución cancelada: permiso denegado"
    elif perm_mode == "confirm":
        risky_patterns = ["rm ", "delete", "drop", "truncate", "format", "sudo", "eval", "exec"]
        if any(pattern in message.lower() for pattern in risky_patterns):
            if not ask_permission(message, "ejecución potencialmente peligrosa"):
                print(f"{YELLOW}[Permiso denegado]{RESET} Ejecución cancelada por el usuario.")
                return 1, "Ejecución cancelada: operación peligrosa denegada"

    policy_result = {"allowed": True, "reason": "policy_not_requested"}
    if check_policy:
        from miliciano_policy import PolicyViolation

        try:
            policy_result = _check_policy_if_requested(message, check_policy=True)
        except PolicyViolation as exc:
            print(f"{YELLOW}[Bloqueado por política]{RESET} {exc}", file=sys.stderr)
            return 1, f"Bloqueado por política: {exc}"

    command = ["openclaw", "agent", "--agent", "main", "--message", message]
    if sys.stdin.isatty() and sys.stdout.isatty():
        res = run_with_spinner(command, "Ejecutando con OpenClaw")
    else:
        res = run(command, capture=True, timeout=agent_timeout())
    out = (res.stdout or "").strip()
    print(out)

    if check_policy:
        from miliciano_policy import create_policy_engine

        create_policy_engine().audit_log(
            {"type": "openclaw_agent", "agent": "main", "message": message},
            policy_result,
            {"success": res.returncode == 0, "returncode": res.returncode},
        )

    bad_markers = [
        "FailoverError:",
        "No API key found for provider",
        "pairing required",
    ]
    if any(marker in out for marker in bad_markers):
        print("\n[Miliciano] OpenClaw no quedó listo para ejecutar agentes.", file=sys.stderr)
        print("[Miliciano] Falta configurar auth del modelo en OpenClaw.", file=sys.stderr)
        print("[Miliciano] Sugerencia: openclaw models auth add", file=sys.stderr)
        return 1, out
    return res.returncode, out
