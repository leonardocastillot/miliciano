#!/usr/bin/env python3
import json
import os
import shlex
import sys
import tempfile

from miliciano_constants import (
    ENV_PROVIDER_HINTS,
    HERMES_AUTH_PATH,
    NVIDIA_BASE_URL,
    OPENCLAW_AUTH_PATH,
    ROUTE_ROLE_LABELS,
)
from miliciano_runtime import (
    clear_nvidia_api_key,
    collect_nvidia_status,
    collect_openclaw_fallbacks,
    get_nvidia_api_key,
    get_permission_mode,
    load_miliciano_state,
    make_model_spec,
    need,
    preferred_local_ollama_model,
    read_json_file,
    resolve_hermes_model_spec,
    resolve_nvidia_model,
    resolve_route_spec,
    run,
    save_miliciano_state,
    set_nvidia_api_key,
    set_permission_mode,
    sync_hermes_global_config,
    sync_hermes_profile_config,
    sync_openclaw_fallback_route,
    write_json_file,
)
from miliciano_ui import BOLD, DIM, RESET, SOFT, YELLOW, panel, status_badge
from miliciano_validators import ValidationError, validate_api_key, validate_provider


def print_route_overview():
    state = load_miliciano_state()
    routes = state.get("routing", {})
    local_model = preferred_local_ollama_model()
    nvidia = collect_nvidia_status()
    openclaw_fallbacks = collect_openclaw_fallbacks()
    panel("ROUTING ACTIVO", [
        f"reasoning  {routes.get('reasoning')}",
        f"execution  {routes.get('execution')}",
        f"fast       {routes.get('fast')}",
        f"local      {routes.get('local') or 'sin definir'}",
        f"fallback   {routes.get('fallback') or 'sin definir'}",
        f"nvidia     {nvidia['model'] if nvidia['enabled'] else 'desactivado'}",
        f"credencial {nvidia['credential_source']}",
    ])
    panel("CAPA LOCAL Y REMOTA", [
        f"preferido  {state.get('ollama', {}).get('preferred_model') or 'sin definir'}",
        f"detectado  {local_model or 'sin modelos locales'}",
        f"fallbacks openclaw  {', '.join(openclaw_fallbacks) if openclaw_fallbacks else 'sin fallback remoto aplicado'}",
    ])
    print("Uso:")
    print("  miliciano route")
    print("  miliciano route set reasoning openai-codex/gpt-5.4")
    print("  miliciano route set fast local")
    print("  miliciano route set local qwen2.5:3b")
    print("  miliciano route set fallback anthropic/claude-sonnet-4")
    print("  miliciano route set fallback nvidia/llama-3.3-nemotron-super-49b-v1.5")
    print("  miliciano route use fast")
    print("  miliciano route sync")
    print(f"{DIM}Auto-routing: Miliciano prioriza reasoning remoto; fast solo se detecta una tarea simple y hay modelo local útil disponible.{RESET}")


def print_model_overview():
    state = load_miliciano_state()
    nvidia = collect_nvidia_status()
    panel("MODELOS ACTIVOS", [
        f"hermes    {state['hermes']['provider']}/{state['hermes']['model']}",
        f"openclaw  {state['openclaw']['model']}",
        f"nemoclaw  {state['nemoclaw']['model'] or 'sin definir'}",
        f"nvidia    {nvidia['model'] if nvidia['enabled'] else 'sin activar'}",
    ])
    print_route_overview()
    print("Uso:")
    print("  miliciano model")
    print("  miliciano model hermes local")
    print("  miliciano model hermes custom/qwen2.5:3b")
    print("  miliciano model hermes openai-codex/gpt-5.4")
    print("  miliciano model openclaw openai-codex/gpt-5.4")
    print("  miliciano model all openai-codex/gpt-5.4-mini")
    print("  miliciano model nemoclaw nemotron/local")
    print("  miliciano provider activate fallback nvidia/llama-3.3-nemotron-super-49b-v1.5")
    print(f"{DIM}Miliciano ya no piensa en un solo modelo: guarda rutas por rol y deja el local como base/fallback.{RESET}")
    print(f"{DIM}Nemoclaw aún no está integrado al camino de inferencia; el valor se guarda como reserva.{RESET}")


def set_hermes_model(spec, update_route=True):
    provider, model = resolve_hermes_model_spec(spec)
    state = load_miliciano_state()
    state["hermes"]["provider"] = provider
    state["hermes"]["model"] = model
    if update_route:
        state.setdefault("routing", {})["reasoning"] = make_model_spec(provider, model)
    if provider == "custom":
        state.setdefault("ollama", {})["preferred_model"] = model
    if provider == "nvidia":
        api_model = resolve_nvidia_model(model)
        nvidia_state = state.setdefault("nvidia", {})
        nvidia_state["enabled"] = True
        api_key, _ = get_nvidia_api_key()
        nvidia_state["api_key_present"] = bool(api_key)
        nvidia_state["base_url"] = NVIDIA_BASE_URL
        nvidia_state["model"] = api_model
        save_miliciano_state(state)
        print(f"Fallback NVIDIA configurado en {api_model}")
        return
    save_miliciano_state(state)
    sync_hermes_global_config(provider, model)
    sync_hermes_profile_config(provider, model)
    print(f"Hermes configurado en {provider}/{model}")


def set_openclaw_model(spec, update_route=True):
    need("openclaw")
    res = run(["openclaw", "models", "set", spec], capture=True)
    out = (res.stdout or "").strip()
    if res.returncode != 0:
        print(out or "No pude cambiar el modelo de OpenClaw.", file=sys.stderr)
        return res.returncode
    state = load_miliciano_state()
    state["openclaw"]["model"] = spec
    if update_route:
        state.setdefault("routing", {})["execution"] = spec
    save_miliciano_state(state)
    print(f"OpenClaw configurado en {spec}")
    return 0


def set_nemoclaw_model(spec):
    state = load_miliciano_state()
    state["nemoclaw"]["model"] = spec
    save_miliciano_state(state)
    print(f"Nemoclaw reservado en {spec}")
    print("Nemoclaw todavía no participa en el camino de inferencia de Miliciano.")


def set_route_target(role, spec):
    role = role.lower()
    if role not in ROUTE_ROLE_LABELS:
        raise ValueError(f"ruta desconocida: {role}")
    normalized = resolve_route_spec(role, spec)
    if role == "reasoning":
        set_hermes_model(normalized, update_route=True)
        return
    if role == "execution":
        rc = set_openclaw_model(normalized, update_route=True)
        if rc != 0:
            sys.exit(rc)
        return

    state = load_miliciano_state()
    state.setdefault("routing", {})[role] = normalized
    if role == "local" and normalized and normalized.startswith("custom/"):
        state.setdefault("ollama", {})["preferred_model"] = normalized.split("/", 1)[1]
    if normalized and normalized.startswith("nvidia/"):
        normalized = resolve_nvidia_model(normalized)
        state["routing"][role] = normalized
        nvidia_state = state.setdefault("nvidia", {})
        nvidia_state["enabled"] = True
        api_key, _ = get_nvidia_api_key()
        nvidia_state["api_key_present"] = bool(api_key)
        nvidia_state["base_url"] = NVIDIA_BASE_URL
        nvidia_state["model"] = normalized
        save_miliciano_state(state)
    print(f"Ruta {role} actualizada a {normalized or 'sin definir'}")
    if role == "fallback":
        ok, detail = sync_openclaw_fallback_route(state)
        print(f"[{'OK' if ok else 'WARN'}] {detail}")


def connect_nvidia_provider(secret):
    api_key = validate_api_key(secret, provider="nvidia")
    set_nvidia_api_key(api_key)
    state = load_miliciano_state()
    nvidia_state = state.setdefault("nvidia", {})
    nvidia = collect_nvidia_status()
    nvidia_state["enabled"] = True
    nvidia_state["api_key_present"] = True
    nvidia_state["base_url"] = nvidia.get("base_url") or NVIDIA_BASE_URL
    nvidia_state["model"] = nvidia.get("model")
    save_miliciano_state(state)
    print("Credencial NVIDIA guardada en ~/.config/miliciano/secrets.json")


def disconnect_nvidia_provider():
    clear_nvidia_api_key()
    state = load_miliciano_state()
    nvidia_state = state.setdefault("nvidia", {})
    nvidia_state["api_key_present"] = False
    save_miliciano_state(state)
    print("Credencial NVIDIA eliminada del storage local de Miliciano")


def use_route_target(role):
    role = role.lower()
    state = load_miliciano_state()
    spec = state.get("routing", {}).get(role)
    if not spec:
        print(f"La ruta {role} no está definida.", file=sys.stderr)
        sys.exit(1)
    if role == "execution":
        rc = set_openclaw_model(spec, update_route=False)
        if rc != 0:
            sys.exit(rc)
        return
    set_hermes_model(spec, update_route=False)
    print(f"Ruta {role} aplicada al motor de razonamiento")


def collect_auth_overview():
    hermes_auth = read_json_file(HERMES_AUTH_PATH) or {}
    hermes_pool = hermes_auth.get("credential_pool") or {}
    hermes_rows = []
    for provider in sorted(hermes_pool):
        entries = hermes_pool.get(provider) or []
        labels = [entry.get("label") or entry.get("id") or entry.get("auth_mode") or "credencial" for entry in entries[:3]]
        suffix = f" +{len(entries) - 3}" if len(entries) > 3 else ""
        hermes_rows.append({"provider": provider, "count": len(entries), "labels": ", ".join(labels) + suffix if labels else "sin etiquetas"})

    openclaw_auth = read_json_file(OPENCLAW_AUTH_PATH) or {}
    openclaw_profiles = openclaw_auth.get("profiles") or {}
    grouped = {}
    for profile_id, entry in openclaw_profiles.items():
        grouped.setdefault(entry.get("provider") or "unknown", []).append((profile_id, entry))

    openclaw_rows = []
    for provider in sorted(grouped):
        rows = grouped[provider]
        labels = [entry.get("email") or profile_id for profile_id, entry in rows[:3]]
        suffix = f" +{len(rows) - 3}" if len(rows) > 3 else ""
        openclaw_rows.append({"provider": provider, "count": len(rows), "labels": ", ".join(labels) + suffix if labels else "sin etiquetas"})

    env_rows = [{"provider": provider, "env": env_name, "present": bool(os.environ.get(env_name))} for provider, env_name in ENV_PROVIDER_HINTS.items()]
    return {"hermes_active": hermes_auth.get("active_provider"), "hermes_rows": hermes_rows, "openclaw_rows": openclaw_rows, "env_rows": env_rows}


def print_auth_overview():
    overview = collect_auth_overview()
    hermes_rows = overview["hermes_rows"] or [{"provider": "ninguno", "count": 0, "labels": "sin credenciales"}]
    openclaw_rows = overview["openclaw_rows"] or [{"provider": "ninguno", "count": 0, "labels": "sin perfiles"}]
    panel("AUTH HERMES", [f"activo    {overview['hermes_active'] or 'n/d'}", *[f"{row['provider']:<12} {row['count']} credencial(es) · {row['labels']}" for row in hermes_rows]])
    panel("AUTH OPENCLAW", [*[f"{row['provider']:<12} {row['count']} perfil(es) · {row['labels']}" for row in openclaw_rows]])
    panel("SEÑALES DE ENTORNO", [f"{row['provider']:<12} {status_badge('ready' if row['present'] else 'pending')}  {row['env']}" for row in overview["env_rows"]])
    print("Uso:")
    print("  miliciano auth")
    print("  miliciano auth add hermes openrouter")
    print("  miliciano auth add hermes openrouter sk-tu-key")
    print("  miliciano auth add openclaw openai-codex")
    print("  miliciano auth remove hermes openrouter 1")
    print("  miliciano auth remove openclaw openai-codex")
    print("  miliciano auth reset hermes openrouter")
    print("  miliciano provider")
    print("  miliciano provider connect hermes openrouter sk-tu-key")
    print("  miliciano provider activate reasoning openai-codex/gpt-5.4")


def remove_openclaw_auth_profiles(target):
    auth = read_json_file(OPENCLAW_AUTH_PATH) or {}
    profiles = auth.get("profiles") or {}
    usage = auth.get("usageStats") or {}
    last_good = auth.get("lastGood") or {}
    matches = []
    for profile_id, entry in profiles.items():
        provider = entry.get("provider") or ""
        email = entry.get("email") or ""
        if target in {profile_id, provider, email}:
            matches.append(profile_id)
    if not matches:
        return 0
    for profile_id in matches:
        provider = (profiles.get(profile_id) or {}).get("provider")
        profiles.pop(profile_id, None)
        usage.pop(profile_id, None)
        if provider and last_good.get(provider) == profile_id:
            last_good.pop(provider, None)
    auth["profiles"] = profiles
    auth["usageStats"] = usage
    auth["lastGood"] = last_good
    write_json_file(OPENCLAW_AUTH_PATH, auth)
    return len(matches)


def add_openclaw_api_token(provider, token):
    try:
        validated_provider = validate_provider(provider)
    except ValidationError as exc:
        print(f"❌ Error: {exc}", file=sys.stderr)
        sys.exit(1)

    script = tempfile.NamedTemporaryFile("w", delete=False, suffix=".sh")
    try:
        script.write("#!/usr/bin/env bash\n")
        script.write(f"printf '%s\\n' {json.dumps(token)} | openclaw models auth paste-token --provider {shlex.quote(validated_provider)}\n")
        script.close()
        os.chmod(script.name, 0o700)
        return run(["bash", script.name])
    finally:
        try:
            os.remove(script.name)
        except Exception:
            pass


def print_permission_overview():
    mode = get_permission_mode()
    mode_labels = {
        "execute": "Ejecución directa sin confirmación (bypass total)",
        "confirm": "Confirmación solo para operaciones peligrosas",
        "strict": "Confirmación requerida para TODA ejecución",
    }
    print(f"\n{BOLD}Modo de permisos actual:{RESET} {mode}")
    print(f"{SOFT}{mode_labels.get(mode, 'desconocido')}{RESET}\n")
    print(f"{BOLD}Modos disponibles:{RESET}")
    for name, label in mode_labels.items():
        indicator = "●" if name == mode else "○"
        print(f"  {indicator} {name:10} - {label}")
    print(f"\n{SOFT}Cambiar modo: miliciano permission <execute|confirm|strict>{RESET}")


def update_permission_mode(new_mode):
    if new_mode not in ("execute", "confirm", "strict"):
        print(f"{YELLOW}Modo inválido: {new_mode}{RESET}", file=sys.stderr)
        print("Usa: execute | confirm | strict", file=sys.stderr)
        sys.exit(1)
    set_permission_mode(new_mode)
    emoji = {"execute": "🚀", "confirm": "⚠️", "strict": "🔒"}.get(new_mode, "✓")
    print(f"{emoji} {BOLD}Modo de permisos actualizado:{RESET} {new_mode}")
    if new_mode == "execute":
        print(f"{SOFT}Las ejecuciones de agentes ocurrirán sin confirmación.{RESET}")
    elif new_mode == "confirm":
        print(f"{SOFT}Se pedirá confirmación solo para operaciones potencialmente peligrosas.{RESET}")
    else:
        print(f"{SOFT}Se pedirá confirmación antes de CADA ejecución de agente.{RESET}")
