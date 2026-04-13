#!/usr/bin/env python3
import os
import stat

from miliciano_constants import (
    DEFAULT_HERMES_MODEL,
    DEFAULT_HERMES_PROVIDER,
    DEFAULT_LOCAL_BASE_URL,
    DEFAULT_LOCAL_CONTEXT_LENGTH,
    DEFAULT_LOCAL_HERMES_PROVIDER,
    DEFAULT_OPENCLAW_MODEL,
    HERMES_AUTH_PATH,
    MILICIANO_GLOBAL_HERMES_CONFIG,
    MILICIANO_PROFILE_CONFIG,
    MILICIANO_SECRETS_PATH,
    MILICIANO_STATE_PATH,
    NEMOCLAW_CREDENTIALS_PATH,
    NVIDIA_API_ENV_VARS,
    NVIDIA_BASE_URL,
    NVIDIA_DEPRECATED_MODEL_MAP,
    NVIDIA_DEFAULT_MODEL,
    OPENCLAW_AUTH_PATH,
    OPENCLAW_CONFIG_PATH,
)
from miliciano_local import preferred_local_ollama_model
from miliciano_system import (
    decode_jwt_payload,
    detect_quota_signal,
    read_json_file,
    write_json_file,
)


_STATE_CACHE = None


def default_hermes_target():
    local_model = preferred_local_ollama_model()
    if local_model:
        return {"provider": DEFAULT_LOCAL_HERMES_PROVIDER, "model": local_model}
    return {"provider": DEFAULT_HERMES_PROVIDER, "model": DEFAULT_HERMES_MODEL}


def make_model_spec(provider, model):
    return f"{provider}/{model}"


def resolve_nvidia_model(model):
    normalized = (model or "").strip() or NVIDIA_DEFAULT_MODEL
    if normalized.startswith("nvidia/"):
        return NVIDIA_DEPRECATED_MODEL_MAP.get(normalized, normalized)
    normalized = f"nvidia/{normalized}"
    return NVIDIA_DEPRECATED_MODEL_MAP.get(normalized, normalized)


def current_local_hermes_spec(model_name=None):
    local_name = model_name or preferred_local_ollama_model()
    if not local_name:
        return None
    return make_model_spec(DEFAULT_LOCAL_HERMES_PROVIDER, local_name)


def default_route_targets(hermes_provider, hermes_model, openclaw_model, local_model_name=None):
    reasoning_spec = make_model_spec(hermes_provider, hermes_model)
    local_spec = current_local_hermes_spec(local_model_name)
    return {
        "reasoning": reasoning_spec,
        "execution": openclaw_model,
        "fast": local_spec or reasoning_spec,
        "local": local_spec,
        "fallback": reasoning_spec,
    }


def default_miliciano_state():
    hermes_default = default_hermes_target()
    local_model_name = preferred_local_ollama_model()
    return {
        "hermes": hermes_default,
        "openclaw": {"model": DEFAULT_OPENCLAW_MODEL},
        "nemoclaw": {"model": None},
        "routing": default_route_targets(
            hermes_default["provider"],
            hermes_default["model"],
            DEFAULT_OPENCLAW_MODEL,
            local_model_name=local_model_name,
        ),
        "ollama": {
            "preferred_model": local_model_name,
            "auto_install": True,
        },
        "nvidia": {
            "enabled": False,
            "api_key_present": any(os.environ.get(name) for name in NVIDIA_API_ENV_VARS),
            "base_url": NVIDIA_BASE_URL,
            "model": resolve_nvidia_model(NVIDIA_DEFAULT_MODEL),
        },
        "preferences": {
            "shell_mode": "reasoning",
            "response_style": "tactical_markdown",
        },
    }


def read_hermes_profile_config():
    provider = None
    model = None
    try:
        with open(MILICIANO_PROFILE_CONFIG, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if line.startswith("provider:"):
                    provider = line.split(":", 1)[1].strip()
                elif line.startswith("default:"):
                    model = line.split(":", 1)[1].strip()
    except FileNotFoundError:
        return {}
    return {"provider": provider, "model": model}


def read_openclaw_primary_model():
    cfg = read_json_file(OPENCLAW_CONFIG_PATH) or {}
    return cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary")


def load_miliciano_state(refresh=False):
    global _STATE_CACHE
    if not refresh and _STATE_CACHE is not None:
        return _STATE_CACHE

    state = default_miliciano_state()
    stored = read_json_file(MILICIANO_STATE_PATH) or {}
    for section, values in stored.items():
        if isinstance(values, dict) and section in state:
            state[section].update({k: v for k, v in values.items() if v is not None})

    hermes_cfg = read_hermes_profile_config()
    if hermes_cfg.get("provider"):
        state["hermes"]["provider"] = hermes_cfg["provider"]
    if hermes_cfg.get("model"):
        state["hermes"]["model"] = hermes_cfg["model"]

    openclaw_model = read_openclaw_primary_model()
    if openclaw_model:
        state["openclaw"]["model"] = openclaw_model

    state.setdefault("routing", {})
    state.setdefault("ollama", {})
    state.setdefault("nvidia", {})
    state.setdefault("preferences", {})

    local_model_name = preferred_local_ollama_model()
    for role, value in default_route_targets(
        state["hermes"]["provider"],
        state["hermes"]["model"],
        state["openclaw"]["model"],
        local_model_name=local_model_name,
    ).items():
        state["routing"].setdefault(role, value)

    state["ollama"].setdefault("preferred_model", local_model_name)
    state["ollama"].setdefault("auto_install", True)
    state["nvidia"].setdefault("enabled", False)
    state["nvidia"].setdefault("api_key_present", any(os.environ.get(name) for name in NVIDIA_API_ENV_VARS))
    state["nvidia"].setdefault("base_url", NVIDIA_BASE_URL)
    state["nvidia"]["model"] = resolve_nvidia_model(state["nvidia"].get("model"))
    for role, value in list(state["routing"].items()):
        if value in NVIDIA_DEPRECATED_MODEL_MAP:
            state["routing"][role] = NVIDIA_DEPRECATED_MODEL_MAP[value]
    state["preferences"].setdefault("shell_mode", "reasoning")
    state["preferences"].setdefault("response_style", "tactical_markdown")
    _STATE_CACHE = state
    return state


def save_miliciano_state(state):
    global _STATE_CACHE
    write_json_file(MILICIANO_STATE_PATH, state)
    _STATE_CACHE = state


def read_miliciano_secrets():
    return read_json_file(MILICIANO_SECRETS_PATH) or {}


def write_miliciano_secrets(secrets):
    os.makedirs(os.path.dirname(MILICIANO_SECRETS_PATH), exist_ok=True)
    write_json_file(MILICIANO_SECRETS_PATH, secrets)
    try:
        os.chmod(MILICIANO_SECRETS_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def get_nvidia_api_key():
    for env_name in NVIDIA_API_ENV_VARS:
        value = os.environ.get(env_name)
        if value:
            return value.strip(), f"env:{env_name}"
    secret = ((read_miliciano_secrets().get("nvidia") or {}).get("api_key") or "").strip()
    if secret:
        return secret, "local"
    return None, None


def set_nvidia_api_key(api_key):
    secrets = read_miliciano_secrets()
    secrets.setdefault("nvidia", {})["api_key"] = api_key.strip()
    write_miliciano_secrets(secrets)


def clear_nvidia_api_key():
    secrets = read_miliciano_secrets()
    nvidia_secret = secrets.get("nvidia") or {}
    nvidia_secret.pop("api_key", None)
    if nvidia_secret:
        secrets["nvidia"] = nvidia_secret
    else:
        secrets.pop("nvidia", None)
    write_miliciano_secrets(secrets)


def get_hermes_selection():
    state = load_miliciano_state()
    return state["hermes"]["provider"], state["hermes"]["model"]


def get_openclaw_selection():
    return load_miliciano_state()["openclaw"]["model"]


def get_route_selection(role):
    return load_miliciano_state().get("routing", {}).get(role)


def sync_hermes_profile_config(provider, model):
    os.makedirs(os.path.dirname(MILICIANO_PROFILE_CONFIG), exist_ok=True)
    with open(MILICIANO_PROFILE_CONFIG, "w", encoding="utf-8") as fh:
        fh.write("model:\n")
        fh.write(f"  provider: {provider}\n")
        fh.write(f"  default: {model}\n")
        if provider == "custom":
            fh.write(f"  base_url: {DEFAULT_LOCAL_BASE_URL}\n")
            fh.write(f"  context_length: {DEFAULT_LOCAL_CONTEXT_LENGTH}\n")


def sync_hermes_global_config(provider, model):
    try:
        with open(MILICIANO_GLOBAL_HERMES_CONFIG, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        lines = []

    if not lines:
        lines = [
            "model:\n",
            f"  default: {model}\n",
            f"  provider: {provider}\n",
            "  api_mode: chat_completions\n",
            "  base_url: https://chatgpt.com/backend-api/codex\n",
        ]
    else:
        updated = []
        seen_model = False
        seen_default = False
        seen_provider = False
        for raw_line in lines:
            stripped = raw_line.strip()
            if stripped.startswith("default:"):
                updated.append(f"  default: {model}\n")
                seen_default = True
            elif stripped.startswith("provider:"):
                updated.append(f"  provider: {provider}\n")
                seen_provider = True
            else:
                updated.append(raw_line)
                if stripped == "model:":
                    seen_model = True
        if not seen_model:
            updated.insert(0, "model:\n")
        if not seen_default:
            insert_at = 1 if updated and updated[0].strip() == "model:" else 0
            updated.insert(insert_at, f"  default: {model}\n")
        if not seen_provider:
            insert_at = 1 if updated and updated[0].strip() == "model:" else 0
            if seen_default and insert_at < len(updated) and updated[insert_at].lstrip().startswith("default:"):
                insert_at += 1
            updated.insert(insert_at, f"  provider: {provider}\n")
        lines = updated

    os.makedirs(os.path.dirname(MILICIANO_GLOBAL_HERMES_CONFIG), exist_ok=True)
    with open(MILICIANO_GLOBAL_HERMES_CONFIG, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def collect_hermes_model_status():
    provider, model = get_hermes_selection()
    auth = read_json_file(HERMES_AUTH_PATH) or {}
    active_provider = auth.get("active_provider") or provider
    provider_entry = (auth.get("providers") or {}).get(active_provider, {})
    tokens = provider_entry.get("tokens") or {}
    payload = decode_jwt_payload(tokens.get("access_token"))
    auth_claims = payload.get("https://api.openai.com/auth", {})
    pool = (auth.get("credential_pool") or {}).get(active_provider, [])
    last_profile = pool[0] if pool else {}
    quota_exhausted = detect_quota_signal(last_profile.get("last_error_message")) or (
        (last_profile.get("last_status") or "").lower() not in {"", "ok"}
        and detect_quota_signal(last_profile.get("last_error_reason") or last_profile.get("last_status"))
    )
    return {
        "provider": provider,
        "model": model,
        "active_provider": active_provider,
        "auth_mode": provider_entry.get("auth_mode"),
        "plan": auth_claims.get("chatgpt_plan_type"),
        "expires_at": payload.get("exp"),
        "last_refresh": provider_entry.get("last_refresh"),
        "request_count": last_profile.get("request_count"),
        "last_status": last_profile.get("last_status"),
        "last_error": last_profile.get("last_error_message") or last_profile.get("last_error_reason"),
        "quota_exhausted": quota_exhausted,
    }


def collect_openclaw_model_status():
    cfg = read_json_file(OPENCLAW_CONFIG_PATH) or {}
    auth = read_json_file(OPENCLAW_AUTH_PATH) or {}
    current_model = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary") or get_openclaw_selection()
    provider = current_model.split("/", 1)[0] if "/" in current_model else current_model
    provider_stats = auth.get("usageStats") or {}
    last_good = (auth.get("lastGood") or {}).get(provider)
    current_profile = ((auth.get("profiles") or {}).get(last_good) if last_good else None) or {}
    stats = provider_stats.get(last_good, {}) if last_good else {}
    payload = decode_jwt_payload(current_profile.get("access"))
    auth_claims = payload.get("https://api.openai.com/auth", {})
    return {
        "model": current_model,
        "provider": provider,
        "plan": auth_claims.get("chatgpt_plan_type"),
        "email": current_profile.get("email"),
        "expires_at": current_profile.get("expires"),
        "last_used": stats.get("lastUsed"),
        "last_failure_at": stats.get("lastFailureAt"),
        "error_count": stats.get("errorCount"),
        "quota_exhausted": False,
    }


def collect_nemoclaw_status():
    cfg = load_miliciano_state()["nemoclaw"]
    credentials = read_json_file(NEMOCLAW_CREDENTIALS_PATH) or {}
    return {
        "model": cfg.get("model"),
        "configured": bool(credentials),
    }


def collect_nvidia_status():
    state = load_miliciano_state()
    nvidia_state = state.get("nvidia", {})
    api_key, source = get_nvidia_api_key()
    api_key_present = bool(nvidia_state.get("api_key_present") or api_key)
    return {
        "enabled": bool(nvidia_state.get("enabled")),
        "api_key_present": api_key_present,
        "credential_source": source or "missing",
        "base_url": nvidia_state.get("base_url") or NVIDIA_BASE_URL,
        "model": resolve_nvidia_model(nvidia_state.get("model") or NVIDIA_DEFAULT_MODEL),
    }
