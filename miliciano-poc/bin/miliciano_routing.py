#!/usr/bin/env python3
from miliciano_constants import (
    DEFAULT_LOCAL_HERMES_PROVIDER,
    FAST_ROUTE_KEYWORDS,
    NVIDIA_BASE_URL,
    NVIDIA_DEFAULT_MODEL,
    NVIDIA_API_ENV_VARS,
    OPENCLAW_CONFIG_PATH,
    REASONING_ROUTE_KEYWORDS,
)
from miliciano_local import preferred_local_ollama_model
from miliciano_state import (
    get_hermes_selection,
    load_miliciano_state,
    make_model_spec,
)
from miliciano_system import read_json_file, run, split_provider_model


def resolve_hermes_model_spec(spec):
    normalized = (spec or "").strip().lower()
    if normalized in {"local", "ollama", "base-local", "default-local"}:
        local_model = preferred_local_ollama_model()
        if not local_model:
            raise ValueError("no hay modelos locales en Ollama; instala uno con `ollama pull` primero")
        return DEFAULT_LOCAL_HERMES_PROVIDER, local_model
    current_provider, _ = get_hermes_selection()
    return split_provider_model(spec, fallback_provider=current_provider)


def resolve_route_spec(role, spec):
    normalized = (spec or "").strip().lower()
    if normalized in {"none", "off", "disable", "disabled"}:
        if role in {"local", "fallback"}:
            return None
        raise ValueError(f"la ruta {role} no puede quedar vacía")
    if role == "execution":
        provider, model = split_provider_model(spec)
        return make_model_spec(provider, model)
    provider, model = resolve_hermes_model_spec(spec)
    return make_model_spec(provider, model)


def parse_openclaw_fallbacks_text(text):
    rows = []
    for raw_line in (text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if value and value != "none":
                rows.append(value)
    return rows


def collect_openclaw_fallbacks():
    from shutil import which

    if which("openclaw") is None:
        return []
    res = run(["openclaw", "models", "fallbacks", "list"], capture=True, timeout=8)
    if res.returncode != 0:
        return []
    return parse_openclaw_fallbacks_text(res.stdout or "")


def parse_hermes_route_spec(spec):
    return split_provider_model(spec)


def choose_route_for_prompt(prompt):
    text = (prompt or "").strip().lower()
    if not text:
        return "reasoning", "sin prompt; uso la ruta principal"

    reasoning_hits = [kw for kw in REASONING_ROUTE_KEYWORDS if kw in text]
    fast_hits = [kw for kw in FAST_ROUTE_KEYWORDS if kw in text]
    local_model = preferred_local_ollama_model()
    long_prompt = len(text) > 280

    if reasoning_hits or long_prompt:
        reason = reasoning_hits[0] if reasoning_hits else "prompt largo"
        return "reasoning", f"detecté una señal de profundidad ({reason})"
    if fast_hits and len(text) <= 280 and local_model:
        return "fast", f"detecté una tarea simple/rápida ({fast_hits[0]}) y hay local disponible ({local_model})"
    if len(text.split()) <= 18 and local_model:
        return "fast", f"prompt corto y hay local disponible ({local_model}); priorizo velocidad/costo"
    return "reasoning", "por defecto uso la ruta principal remota"


def resolve_hermes_route_for_prompt(prompt, forced_role=None):
    state = load_miliciano_state()
    if forced_role:
        requested_role = forced_role
        reason = f"ruta forzada por comando: {forced_role}"
    else:
        requested_role, reason = choose_route_for_prompt(prompt)

    role = requested_role
    spec = state.get("routing", {}).get(role)
    if not spec:
        role = "reasoning"
        spec = state.get("routing", {}).get("reasoning") or make_model_spec(state["hermes"]["provider"], state["hermes"]["model"])
        reason = f"{reason}; faltaba ruta {requested_role}, vuelvo a reasoning"

    provider, model = parse_hermes_route_spec(spec)
    return {
        "role": role,
        "provider": provider,
        "model": model,
        "spec": spec,
        "reason": reason,
    }


def sync_openclaw_fallback_route(state=None):
    from shutil import which

    if which("openclaw") is None:
        return False, "OpenClaw no instalado"
    state = state or load_miliciano_state()
    fallback_spec = state.get("routing", {}).get("fallback")
    current_execution = state.get("openclaw", {}).get("model")
    run(["openclaw", "models", "fallbacks", "clear"], capture=True, timeout=8)
    if not fallback_spec:
        return True, "fallback vacío; lista de respaldo limpiada"
    if fallback_spec == current_execution:
        return True, "fallback coincide con el modelo principal; lista limpiada"
    if fallback_spec.startswith("custom/") or fallback_spec.startswith("nvidia/"):
        return True, "fallback local/directo reservado en Miliciano; no se aplica a OpenClaw"
    add = run(["openclaw", "models", "fallbacks", "add", fallback_spec], capture=True, timeout=8)
    if add.returncode == 0:
        return True, f"fallback de OpenClaw sincronizado a {fallback_spec}"
    out = (add.stdout or "").strip()
    return False, out or f"no pude registrar fallback {fallback_spec} en OpenClaw"


def read_openclaw_primary_model():
    cfg = read_json_file(OPENCLAW_CONFIG_PATH) or {}
    return cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary")


def nvidia_defaults_from_env():
    return {
        "enabled": False,
        "api_key_present": any(__import__("os").environ.get(name) for name in NVIDIA_API_ENV_VARS),
        "base_url": NVIDIA_BASE_URL,
        "model": NVIDIA_DEFAULT_MODEL,
    }
