#!/usr/bin/env python3
import sys

from miliciano_control_support import (
    add_openclaw_api_token,
    connect_nvidia_provider,
    disconnect_nvidia_provider,
    print_auth_overview,
    print_model_overview,
    print_permission_overview,
    print_route_overview,
    remove_openclaw_auth_profiles,
    set_hermes_model,
    set_nemoclaw_model,
    set_openclaw_model,
    set_route_target,
    update_permission_mode,
    use_route_target,
)
from miliciano_runtime import run
from miliciano_ui import BOLD, RESET, SOFT, YELLOW, banner, status_badge
from miliciano_validators import ValidationError, validate_provider, validate_route_name


def cmd_route(args):
    banner()
    if not args or args[0] in {"show", "status", "list"}:
        print_route_overview()
        return

    action = args[0].lower()
    if action == "set":
        if len(args) < 3:
            print("Uso: miliciano route set <reasoning|execution|fast|local|fallback> <modelo>", file=sys.stderr)
            sys.exit(1)
        try:
            role = validate_route_name(args[1])
        except ValidationError as exc:
            print(f"❌ Error: {exc}", file=sys.stderr)
            sys.exit(1)
        set_route_target(role, " ".join(args[2:]).strip())
        return
    if action == "use":
        if len(args) != 2:
            print("Uso: miliciano route use <reasoning|execution|fast|local|fallback>", file=sys.stderr)
            sys.exit(1)
        try:
            role = validate_route_name(args[1])
        except ValidationError as exc:
            print(f"❌ Error: {exc}", file=sys.stderr)
            sys.exit(1)
        use_route_target(role)
        return
    if action == "sync":
        from miliciano_runtime import load_miliciano_state, sync_openclaw_fallback_route
        ok, detail = sync_openclaw_fallback_route(load_miliciano_state())
        print(detail)
        if not ok:
            sys.exit(1)
        return

    print(f"Acción de routing desconocida: {action}", file=sys.stderr)
    print("Usa: show | set | use | sync", file=sys.stderr)
    sys.exit(1)


def cmd_auth(args):
    banner()
    if not args or args[0] in {"status", "show", "list"}:
        print_auth_overview()
        return

    action = args[0].lower()
    if action == "add":
        if len(args) < 3:
            print("Uso: miliciano auth add <hermes|openclaw> <provider> [token/api-key]", file=sys.stderr)
            sys.exit(1)
        target = args[1].lower()
        try:
            provider = validate_provider(args[2])
        except ValidationError as exc:
            print(f"❌ Error: {exc}", file=sys.stderr)
            sys.exit(1)
        secret = args[3] if len(args) > 3 else None
        if target == "hermes":
            cmd = ["hermes", "auth", "add", provider]
            if secret:
                cmd.extend(["--type", "api-key", "--api-key", secret])
            rc = run(cmd).returncode
        elif target == "openclaw":
            rc = add_openclaw_api_token(provider, secret).returncode if secret else run(["openclaw", "models", "auth", "login", "--provider", provider]).returncode
        else:
            print(f"Destino de auth desconocido: {target}", file=sys.stderr)
            sys.exit(1)
        if rc != 0:
            sys.exit(rc)
        print_auth_overview()
        return

    if action == "remove":
        if len(args) < 3:
            print("Uso: miliciano auth remove <hermes|openclaw> <provider|perfil> [target]", file=sys.stderr)
            sys.exit(1)
        target = args[1].lower()
        provider = args[2]
        if target == "hermes":
            if len(args) < 4:
                print("Uso: miliciano auth remove hermes <provider> <index|id|label>", file=sys.stderr)
                sys.exit(1)
            rc = run(["hermes", "auth", "remove", provider, args[3]]).returncode
            if rc != 0:
                sys.exit(rc)
        elif target == "openclaw":
            removed = remove_openclaw_auth_profiles(provider)
            if removed == 0:
                print("No encontré perfiles OpenClaw que coincidan.", file=sys.stderr)
                sys.exit(1)
            print(f"Eliminé {removed} perfil(es) de OpenClaw para {provider}")
        else:
            print(f"Destino de auth desconocido: {target}", file=sys.stderr)
            sys.exit(1)
        print_auth_overview()
        return

    if action == "reset":
        if len(args) != 3 or args[1].lower() != "hermes":
            print("Uso: miliciano auth reset hermes <provider>", file=sys.stderr)
            sys.exit(1)
        rc = run(["hermes", "auth", "reset", args[2]]).returncode
        if rc != 0:
            sys.exit(rc)
        print_auth_overview()
        return

    print(f"Acción de auth desconocida: {action}", file=sys.stderr)
    print("Usa: show | add | remove | reset", file=sys.stderr)
    sys.exit(1)


def cmd_provider(args):
    banner()
    if not args or args[0] in {"status", "show", "list"}:
        print_auth_overview()
        print_route_overview()
        return

    action = args[0].lower()
    if action in {"connect", "add"}:
        if len(args) >= 2 and args[1].lower() == "nvidia":
            if len(args) != 3:
                print("Uso: miliciano provider connect nvidia <api-key>", file=sys.stderr)
                sys.exit(1)
            connect_nvidia_provider(args[2])
            return
        if len(args) < 3:
            print("Uso: miliciano provider connect <hermes|openclaw> <provider> [secret]", file=sys.stderr)
            sys.exit(1)
        cmd_auth(["add", args[1], args[2], *args[3:]])
        return
    if action in {"remove", "disconnect"}:
        if len(args) == 2 and args[1].lower() == "nvidia":
            disconnect_nvidia_provider()
            return
        if len(args) < 3:
            print("Uso: miliciano provider disconnect <hermes|openclaw> <provider> [target]", file=sys.stderr)
            sys.exit(1)
        cmd_auth(["remove", args[1], args[2], *args[3:]])
        return
    if action in {"activate", "use"}:
        if len(args) < 3:
            print("Uso: miliciano provider activate <reasoning|execution|fast|local|fallback> <provider/modelo|local>", file=sys.stderr)
            sys.exit(1)
        set_route_target(args[1], " ".join(args[2:]).strip())
        return
    if action == "reset":
        if len(args) != 3 or args[1].lower() != "hermes":
            print("Uso: miliciano provider reset hermes <provider>", file=sys.stderr)
            sys.exit(1)
        cmd_auth(["reset", args[1], args[2]])
        return

    print(f"Acción de provider desconocida: {action}", file=sys.stderr)
    print("Usa: show | connect | disconnect | activate | reset", file=sys.stderr)
    sys.exit(1)


def cmd_model(args):
    banner()
    if not args or args[0] in {"show", "status"}:
        print_model_overview()
        return

    target = args[0].lower()
    spec = " ".join(args[1:]).strip()
    if not spec:
        print("Falta modelo. Ejemplo: miliciano model hermes local", file=sys.stderr)
        sys.exit(1)

    if target == "hermes":
        set_hermes_model(spec)
        return
    if target == "openclaw":
        rc = set_openclaw_model(spec)
        if rc != 0:
            sys.exit(rc)
        return
    if target in {"all", "both"}:
        set_hermes_model(spec)
        rc = set_openclaw_model(spec)
        if rc != 0:
            sys.exit(rc)
        return
    if target == "nemoclaw":
        set_nemoclaw_model(spec)
        return

    print(f"Objetivo de modelo desconocido: {target}", file=sys.stderr)
    print("Usa: hermes | openclaw | all | nemoclaw", file=sys.stderr)
    sys.exit(1)


def cmd_permission(args):
    if not args:
        print_permission_overview()
        return
    try:
        update_permission_mode(args[0].strip().lower())
    except Exception as exc:
        print(f"{YELLOW}Error al cambiar modo: {exc}{RESET}", file=sys.stderr)
        sys.exit(1)


def cmd_tools(args):
    if not args or args[0] in ("list", "ls"):
        try:
            from miliciano_registry import check_all_health, list_tools
            tools = list_tools()
            health_map = {h["name"]: h for h in check_all_health(parallel=True)}
            print(f"\n{BOLD}Registered Tools:{RESET}\n")
            for tool in tools:
                name = tool["name"]
                status = health_map.get(name, {}).get("status", "unknown")
                badge = status_badge("ready" if status == "ready" else "pending" if status == "disabled" else "error")
                print(f"  {name:15} {badge:20} type={tool.get('type', 'unknown'):6} enabled={tool.get('enabled', True)}")
                if tool.get("capabilities"):
                    print(f"    {SOFT}capabilities: {', '.join(tool['capabilities'])}{RESET}")
                if tool.get("routes"):
                    print(f"    {SOFT}routes: {', '.join(tool['routes'])}{RESET}")
                if status == "error":
                    print(f"    {SOFT}error: {health_map.get(name, {}).get('message', '')}{RESET}")
                print()
        except ImportError:
            print(f"{YELLOW}Error: miliciano_registry module not found{RESET}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"{YELLOW}Error listing tools: {exc}{RESET}", file=sys.stderr)
            sys.exit(1)
        return

    if args[0] == "health":
        try:
            from miliciano_registry import check_all_health
            print(f"\n{BOLD}Tool Health Status:{RESET}\n")
            for health in check_all_health(parallel=True):
                status = health["status"]
                badge = status_badge("ready" if status == "ready" else "pending" if status == "disabled" else "error")
                print(f"  {health['name']:15} {badge:20} {health.get('message', '')}")
            print()
        except ImportError:
            print(f"{YELLOW}Error: miliciano_registry module not found{RESET}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"{YELLOW}Error checking health: {exc}{RESET}", file=sys.stderr)
            sys.exit(1)
        return

    if args[0] == "info" and len(args) > 1:
        tool_name = args[1]
        try:
            from miliciano_registry import check_tool_health, load_registry
            config = load_registry()["tools"].get(tool_name)
            if not config:
                print(f"{YELLOW}Tool not found: {tool_name}{RESET}", file=sys.stderr)
                sys.exit(1)
            health = check_tool_health(tool_name)
            print(f"\n{BOLD}Tool: {tool_name}{RESET}\n")
            print(f"  Type:         {config.get('type', 'unknown')}")
            print(f"  Enabled:      {config.get('enabled', True)}")
            print(f"  Status:       {health['status']} - {health.get('message', '')}")
            if config.get("binary"):
                print(f"  Binary:       {config['binary']}")
            if config.get("base_url"):
                print(f"  Base URL:     {config['base_url']}")
            if config.get("capabilities"):
                print(f"  Capabilities: {', '.join(config['capabilities'])}")
            if config.get("routes"):
                print(f"  Routes:       {', '.join(config['routes'])}")
            if config.get("requires_env"):
                print(f"  Requires env: {', '.join(config['requires_env'])}")
            print()
        except ImportError:
            print(f"{YELLOW}Error: miliciano_registry module not found{RESET}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"{YELLOW}Error getting tool info: {exc}{RESET}", file=sys.stderr)
            sys.exit(1)
        return

    print(f"{YELLOW}Unknown tools subcommand: {args[0]}{RESET}", file=sys.stderr)
    print("Usage: miliciano tools [list|health|info <name>]", file=sys.stderr)
    sys.exit(1)
