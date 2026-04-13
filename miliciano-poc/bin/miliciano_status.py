#!/usr/bin/env python3
import concurrent.futures
import json
from datetime import datetime
from shutil import which

from miliciano_constants import MILICIANO_VERSION
from miliciano_obsidian import OBSIDIAN_MILICIANO_NOTE, collect_obsidian_status
from miliciano_runtime import (
    PREREQ_COMMANDS,
    basic_runtime_status,
    collect_hermes_model_status,
    collect_local_ai_hardware,
    collect_nemoclaw_status,
    collect_nvidia_status,
    collect_ollama_status,
    collect_openclaw_model_status,
    detect_quota_signal,
    format_timestamp,
    recommend_ollama_models,
    run,
)
from miliciano_shell_input import shell_runtime_status
from miliciano_ui import BOLD, RESET, banner, panel, print_kv, rule, status_badge


def _probe_openclaw_gateway(openclaw_path):
    if not openclaw_path:
        return None
    return run(["openclaw", "health", "--json"], capture=True, timeout=4)


def _openclaw_auth_ok(model_status):
    if not model_status.get("model"):
        return False
    if model_status.get("quota_exhausted"):
        return False
    return bool(model_status.get("provider"))


def render_session_status(session_id=None, include_banner=True):
    if include_banner:
        banner()
    runtime = basic_runtime_status()
    hermes_path = which("hermes")
    openclaw_path = which("openclaw")
    nemoclaw_path = which("nemoclaw")

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            "gateway": executor.submit(_probe_openclaw_gateway, openclaw_path),
            "ollama": executor.submit(collect_ollama_status),
            "hardware": executor.submit(collect_local_ai_hardware),
            "hermes_model": executor.submit(collect_hermes_model_status),
            "openclaw_model": executor.submit(collect_openclaw_model_status),
            "obsidian": executor.submit(collect_obsidian_status),
        }
        health = futures["gateway"].result()
        ollama_status = futures["ollama"].result()
        local_hw = futures["hardware"].result()
        hermes_model = futures["hermes_model"].result()
        openclaw_model = futures["openclaw_model"].result()
        obsidian = futures["obsidian"].result()

    health_out = (health.stdout or "").strip() if health else ""
    gateway_ok = bool(health and health.returncode == 0 and '"ok":true' in health_out.lower().replace(" ", ""))
    auth_ok = _openclaw_auth_ok(openclaw_model)
    nemoclaw_ok = bool(nemoclaw_path and collect_nemoclaw_status().get("configured"))
    reasoning_ok = bool(hermes_path)
    execution_ok = bool(openclaw_path and gateway_ok and auth_ok)
    policy_ok = nemoclaw_ok
    ollama_recos = recommend_ollama_models(local_hw)
    nvidia = collect_nvidia_status()
    nemoclaw_model = collect_nemoclaw_status()
    shell_ui = shell_runtime_status()

    execution_limit_kind = "ready" if auth_ok else "pending"
    execution_limit_text = "auth local detectada" if auth_ok else "sin auth utilizable para OpenClaw"
    if openclaw_model.get("quota_exhausted"):
        execution_limit_kind = "error"
        execution_limit_text = "señal de cuota/límite agotado"

    reasoning_limit_kind = "error" if hermes_model["quota_exhausted"] else "info"
    reasoning_limit_text = hermes_model["last_error"] or "sin señal de cuota agotada"

    panel("PANEL OPERATIVO", [
        f"reasoning  {status_badge('ready' if reasoning_ok else 'pending')}",
        f"execution  {status_badge('ready' if execution_ok else 'pending')}",
        f"policy     {status_badge('ready' if policy_ok else 'pending')}",
        f"nvidia     {status_badge('ready' if nvidia['enabled'] and nvidia['api_key_present'] else 'pending')}",
        f"shell ui   {status_badge('ready' if shell_ui['available'] else 'pending')}",
    ])

    panel("RUNTIME BASE", [
        f"{cmd:<7} {(status_badge('ready') if runtime[cmd]['path'] else status_badge('error'))}  {runtime[cmd]['version'] or 'no detectado'}"
        for cmd in PREREQ_COMMANDS
    ])

    panel("STACK MILICIANO", [
        f"hermes    {(status_badge('ready') if hermes_path else status_badge('error'))}  {hermes_path or 'no encontrado'}",
        f"openclaw  {(status_badge('ready') if openclaw_path else status_badge('error'))}  {openclaw_path or 'no encontrado'}",
        f"nemoclaw  {(status_badge('ready') if nemoclaw_path else status_badge('pending'))}  {nemoclaw_path or 'no encontrado'}",
        f"shell     {(status_badge('ready') if shell_ui['available'] else status_badge('pending'))}  {shell_ui['detail']}",
    ])

    panel("EJECUCIÓN Y POLICY", [
        f"gateway openclaw  {(status_badge('ready') if gateway_ok else status_badge('error'))}",
        f"auth modelo       {(status_badge('ready') if auth_ok else status_badge('pending'))}",
        f"nemoclaw runtime  {(status_badge('ready') if nemoclaw_ok else status_badge('pending'))}",
    ])

    panel("INFERENCIA LOCAL", [
        f"ollama    {(status_badge('ready') if ollama_status['path'] else status_badge('pending'))}  {ollama_status['version'] or 'no instalado'}",
        f"api local {(status_badge('ready') if ollama_status['api_ok'] else status_badge('pending'))}  {ollama_status['api_detail']}",
        f"hardware  {local_hw['cpu'] or 'CPU n/d'} · RAM {local_hw['ram_gib'] or 'n/d'} GiB · GPU {local_hw['gpu'] or 'n/d'} · VRAM {local_hw['gpu_vram_gib'] or 'n/d'} GiB",
        f"sugerido  {ollama_recos[0][0]} · {ollama_recos[0][1]}",
    ])

    panel("MODELOS Y LÍMITES", [
        f"hermes    {status_badge('ready' if reasoning_ok else 'pending')}  {hermes_model['provider']}/{hermes_model['model']}",
        f"          plan={hermes_model['plan'] or 'n/d'} · auth={hermes_model['auth_mode'] or 'n/d'} · expira={format_timestamp(hermes_model['expires_at'])}",
        f"          límites {status_badge(reasoning_limit_kind)}  {reasoning_limit_text}",
        f"openclaw  {status_badge('ready' if auth_ok else 'pending')}  {openclaw_model['model']}",
        f"          plan={openclaw_model['plan'] or 'n/d'} · perfil={openclaw_model['email'] or 'n/d'} · expira={format_timestamp(openclaw_model['expires_at'], ms=True)}",
        f"          límites {status_badge(execution_limit_kind)}  {execution_limit_text}",
        f"          uso previo: errores={openclaw_model['error_count'] or 0} · último uso={format_timestamp(openclaw_model['last_used'], ms=True)} · último fallo={format_timestamp(openclaw_model['last_failure_at'], ms=True)}",
        f"nemoclaw {status_badge('ready' if policy_ok else 'pending')}  modelo reservado={nemoclaw_model['model'] or 'sin definir'}",
        f"nvidia    {status_badge('ready' if nvidia['enabled'] else 'pending')}  {nvidia['model']}",
    ])

    panel("OBSIDIAN", [
        f"vault     {status_badge('ready' if obsidian['present'] else 'pending')}  {obsidian['path']}",
        f"app       {status_badge('ready' if obsidian['app_available'] else 'pending')}  {obsidian.get('app_mode', 'none')}",
        f"notas     {obsidian['total_notes']}",
        f"miliciano {status_badge('ready' if obsidian['miliciano_exists'] else 'pending')}  {OBSIDIAN_MILICIANO_NOTE}",
        f"inbox     {status_badge('ready' if obsidian['inbox_exists'] else 'pending')}  Miliciano/Inbox.md",
    ])

    if session_id is not None:
        panel("SESIÓN ACTUAL", [
            f"session_id  {session_id or 'nueva'}",
            f"reasoning   {hermes_model['provider']}/{hermes_model['model']}",
            f"execution   {openclaw_model['model']}",
        ])

    if health_out and not gateway_ok:
        print_kv("detalle gateway", health_out)
    if detect_quota_signal(reasoning_limit_text):
        print_kv("detalle límite reasoning", reasoning_limit_text)


def cmd_status(args=None):
    args = args or []
    refresh = "--refresh" in args or "-r" in args
    if refresh:
        try:
            from miliciano_cache import cache_invalidate
            for key in ("ollama_status", "local_hardware", "runtime_status"):
                cache_invalidate(key)
        except ImportError:
            pass
    render_session_status()


def cmd_doctor():
    banner()
    panel("DOCTOR", [
        f"hermes          {status_badge('info')} diagnóstico del core",
        f"openclaw        {status_badge('info')} diagnóstico del motor de ejecución",
        f"security audit  {status_badge('info')} revisión profunda de seguridad",
    ])
    print(f"{BOLD}Hermes doctor{RESET}")
    print(rule(accent="─"))
    run(["hermes", "doctor"])
    print()
    print(f"{BOLD}OpenClaw doctor{RESET}")
    print(rule(accent="─"))
    if which("openclaw"):
        run(["openclaw", "doctor"])
    else:
        print("OpenClaw no encontrado; omitiendo diagnóstico.")
    print()
    print(f"{BOLD}OpenClaw security audit{RESET}")
    print(rule(accent="─"))
    if which("openclaw"):
        run(["openclaw", "security", "audit", "--deep"])
    else:
        print("OpenClaw no encontrado; omitiendo security audit.")


def health_check_json():
    hermes_path = which("hermes")
    openclaw_path = which("openclaw")
    nemoclaw_path = which("nemoclaw")
    ollama_status = collect_ollama_status()
    openclaw_model = collect_openclaw_model_status()
    gateway = _probe_openclaw_gateway(openclaw_path)
    gateway_ok = bool(gateway and gateway.returncode == 0 and '"ok":true' in ((gateway.stdout or "").lower().replace(" ", "")))
    auth_ok = _openclaw_auth_ok(openclaw_model)
    nemoclaw_status = collect_nemoclaw_status()

    status = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": MILICIANO_VERSION,
        "healthy": all([bool(hermes_path), gateway_ok, auth_ok]),
        "components": {
            "hermes": {"status": "healthy" if hermes_path else "unhealthy", "available": hermes_path is not None, "path": hermes_path},
            "openclaw": {"status": "healthy" if (gateway_ok and auth_ok) else "unhealthy", "available": openclaw_path is not None, "gateway_ok": gateway_ok, "auth_ok": auth_ok, "path": openclaw_path},
            "nemoclaw": {"status": "healthy" if nemoclaw_status.get("configured") else "unhealthy", "available": nemoclaw_path is not None, "path": nemoclaw_path},
            "ollama": {"status": "healthy" if (ollama_status.get("path") and ollama_status.get("api_ok")) else "unavailable", "available": ollama_status.get("path") is not None, "api_ok": ollama_status.get("api_ok", False), "version": ollama_status.get("version"), "models": ollama_status.get("models", [])},
        },
        "capabilities": {
            "reasoning": bool(hermes_path),
            "execution": gateway_ok and auth_ok,
            "policy": bool(nemoclaw_status.get("configured")),
            "local_inference": bool(ollama_status.get("path") and ollama_status.get("api_ok")),
        },
    }
    return status


def cmd_health_json():
    status = health_check_json()
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0 if status["healthy"] else 1
