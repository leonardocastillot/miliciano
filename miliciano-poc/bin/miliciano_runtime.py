#!/usr/bin/env python3
import base64
import html
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from textwrap import dedent, wrap

from miliciano_ui import *


MILICIANO_PREAMBLE = (
    "Responde como Miliciano, tu partner tecnológico by Milytics. "
    "No te presentes como Hermes salvo que te pregunten por la arquitectura interna. "
    "Responde en español si el usuario habla en español. "
    "Sé claro, ejecutivo, útil y orientado a la acción. "
    "Optimiza tokens: responde corto, sin repetir ideas, sin introducciones innecesarias. "
    "Usa solo el mínimo texto útil para resolver la tarea."
)

MILICIANO_HERMES_HOME = os.path.expanduser("~/.hermes/profiles/miliciano")
MILICIANO_GLOBAL_HERMES_CONFIG = os.path.expanduser("~/.hermes/config.yaml")
MILICIANO_PROFILE_CONFIG = os.path.join(MILICIANO_HERMES_HOME, "config.yaml")
MILICIANO_STATE_DIR = os.path.expanduser("~/.config/miliciano")
MILICIANO_STATE_PATH = os.path.join(MILICIANO_STATE_DIR, "config.json")
OPENCLAW_CONFIG_PATH = os.path.expanduser("~/.openclaw/openclaw.json")
OPENCLAW_AUTH_PATH = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
HERMES_AUTH_PATH = os.path.join(MILICIANO_HERMES_HOME, "auth.json")
NEMOCLAW_CREDENTIALS_PATH = os.path.expanduser("~/.nemoclaw/credentials.json")

DEFAULT_HERMES_PROVIDER = "openai-codex"
DEFAULT_HERMES_MODEL = "gpt-5.4"
DEFAULT_OPENCLAW_MODEL = "openai-codex/gpt-5.4"
DEFAULT_LOCAL_HERMES_PROVIDER = "custom"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_LOCAL_CONTEXT_LENGTH = 16384

ROUTE_ROLE_LABELS = {
    "reasoning": "motor principal de razonamiento",
    "execution": "motor principal de ejecución",
    "fast": "ruta rápida y barata",
    "local": "base local/offline",
    "fallback": "respaldo cuando falle el principal",
}

ENV_PROVIDER_HINTS = {
    "openai": "OPENAI_API_KEY",
    "openai-codex": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "google": "GOOGLE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
}

NVIDIA_API_ENV_VARS = ("NVIDIA_API_KEY", "NVAPI_API_KEY", "NVAPI")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_DEFAULT_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"

OBSIDIAN_DEFAULT_VAULT = os.path.expanduser("~/Documents/Obsidian Vault")
OBSIDIAN_MILICIANO_NOTE = "Miliciano Cerebro.md"
OBSIDIAN_GRAPH_HOST = "127.0.0.1"
OBSIDIAN_GRAPH_PORT = int(os.environ.get("MILICIANO_OBSIDIAN_PORT", "8765"))

FAST_ROUTE_KEYWORDS = {
    "resume", "resumir", "summary", "summarize", "traduc", "translate", "rewrite", "rephrase",
    "corrige", "corregir", "fix grammar", "gramática", "grammar", "mejora redacción", "redacta",
    "clasifica", "classify", "extrae", "extract", "lista", "list", "titulos", "títulos",
    "short", "corto", "breve", "one sentence", "una frase", "bullet", "bullets",
}

REASONING_ROUTE_KEYWORDS = {
    "arquitectura", "architecture", "plan", "strategy", "estrategia", "roadmap", "debug", "bug",
    "error", "stack trace", "investiga", "analyze", "analiza", "compare", "compara", "diseña",
    "design", "implement", "refactor", "código", "code", "tests", "test", "seguridad",
    "security", "agent", "workflow", "integración", "integration", "multi-step", "multi step",
}

PREREQ_COMMANDS = ["node", "npm", "curl", "docker"]


_STATE_CACHE = None
_OLLAMA_STATUS_CACHE = None
_PREFERRED_LOCAL_OLLAMA_MODEL_CACHE = None


def base_env():
    env = os.environ.copy()
    env.setdefault("HERMES_HOME", MILICIANO_HERMES_HOME)
    return env


def run(cmd, capture=False, env=None, timeout=None):
    effective_env = env or base_env()
    try:
        if capture:
            return subprocess.run(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=effective_env,
                timeout=timeout,
            )
        return subprocess.run(cmd, env=effective_env, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or exc.output or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(cmd, 124, out, None)


def run_with_spinner(cmd, label, env=None):
    effective_env = env or base_env()
    proc = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=effective_env)
    stop = threading.Event()

    def spinner():
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        beats = ["activo", "procesando", "pensando", "resolviendo"]
        i = 0
        while not stop.is_set():
            frame = frames[i % len(frames)]
            beat = beats[(i // 6) % len(beats)]
            text = f"{VIOLET}{frame}{RESET} {BOLD}Miliciano{RESET} · {label} · {SOFT}{beat}{RESET}"
            sys.stdout.write("\r" + text)
            sys.stdout.flush()
            time.sleep(0.09)
            i += 1
        sys.stdout.write("\r" + " " * 96 + "\r")
        sys.stdout.flush()

    t = threading.Thread(target=spinner, daemon=True)
    t.start()
    out = ""
    try:
        out, _ = proc.communicate()
    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            out, _ = proc.communicate(timeout=2)
        except Exception:
            pass
        raise
    finally:
        stop.set()
        t.join(timeout=1)
    return subprocess.CompletedProcess(cmd, proc.returncode, out or "", None)


def run_openclaw_agent(message):
    res = run_with_spinner(["openclaw", "agent", "--agent", "main", "--message", message], "Ejecutando con OpenClaw")
    out = (res.stdout or "").strip()
    print(out)
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


def need(cmd):
    from shutil import which
    if which(cmd) is None:
        print(f"Falta comando requerido: {cmd}", file=sys.stderr)
        sys.exit(1)


def capture_version(cmd):
    try:
        res = run(cmd, capture=True)
    except FileNotFoundError:
        return None
    out = (res.stdout or "").strip()
    if res.returncode != 0 or not out:
        return None
    return out.splitlines()[0]


def read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def write_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=True)
        fh.write("\n")


def default_hermes_target():
    local_model = preferred_local_ollama_model()
    if local_model:
        return {
            "provider": DEFAULT_LOCAL_HERMES_PROVIDER,
            "model": local_model,
        }
    return {
        "provider": DEFAULT_HERMES_PROVIDER,
        "model": DEFAULT_HERMES_MODEL,
    }


def make_model_spec(provider, model):
    return f"{provider}/{model}"


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
        "hermes": {
            "provider": hermes_default["provider"],
            "model": hermes_default["model"],
        },
        "openclaw": {
            "model": DEFAULT_OPENCLAW_MODEL,
        },
        "nemoclaw": {
            "model": None,
        },
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
            "model": NVIDIA_DEFAULT_MODEL,
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
    return (
        cfg.get("agents", {})
        .get("defaults", {})
        .get("model", {})
        .get("primary")
    )


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

    if not isinstance(state.get("routing"), dict):
        state["routing"] = {}
    if not isinstance(state.get("ollama"), dict):
        state["ollama"] = {}
    if not isinstance(state.get("nvidia"), dict):
        state["nvidia"] = {}

    local_model_name = preferred_local_ollama_model()
    route_defaults = default_route_targets(
        state["hermes"]["provider"],
        state["hermes"]["model"],
        state["openclaw"]["model"],
        local_model_name=local_model_name,
    )
    for role, value in route_defaults.items():
        state["routing"].setdefault(role, value)

    state["ollama"].setdefault("preferred_model", local_model_name)
    state["ollama"].setdefault("auto_install", True)
    state["nvidia"].setdefault("enabled", False)
    state["nvidia"].setdefault("api_key_present", any(os.environ.get(name) for name in NVIDIA_API_ENV_VARS))
    state["nvidia"].setdefault("base_url", NVIDIA_BASE_URL)
    state["nvidia"].setdefault("model", NVIDIA_DEFAULT_MODEL)
    _STATE_CACHE = state
    return state


def save_miliciano_state(state):
    global _STATE_CACHE
    write_json_file(MILICIANO_STATE_PATH, state)
    _STATE_CACHE = state


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
            line = raw_line.rstrip("\n")
            stripped = line.strip()
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


def strip_terminal_noise(text):
    import re

    cleaned = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text or "")
    cleaned = re.sub(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]+", " ", cleaned)
    cleaned = re.sub(r"\?25[hl]", "", cleaned)
    filtered = []
    for raw_line in cleaned.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            filtered.append("")
            continue
        if all(ch in " ?[]0123456789l" for ch in line):
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()


def decode_jwt_payload(token):
    if not token or "." not in token:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}


def format_timestamp(ts, ms=False):
    if ts in (None, "", 0):
        return "n/d"
    try:
        seconds = ts / 1000 if ms else ts
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return "n/d"


def format_iso_timestamp(value):
    if not value:
        return "n/d"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return value


def format_remaining_ms(value):
    if value in (None, "", 0):
        return "n/d"
    try:
        total_seconds = max(0, int(value // 1000))
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes or not parts:
            parts.append(f"{minutes}m")
        return " ".join(parts)
    except Exception:
        return "n/d"


def split_provider_model(spec, fallback_provider=None):
    value = (spec or "").strip()
    if not value:
        raise ValueError("modelo vacío")
    if "/" in value:
        provider, model = value.split("/", 1)
        provider = provider.strip()
        model = model.strip()
        if provider and model:
            return provider, model
    if fallback_provider:
        return fallback_provider, value
    raise ValueError("usa el formato provider/modelo o especifica un provider actual")


def detect_quota_signal(text):
    normalized = (text or "").lower()
    markers = [
        "quota",
        "rate limit",
        "rate_limit",
        "429",
        "insufficient",
        "billing",
        "credit",
        "capacity",
        "exhaust",
    ]
    return any(marker in normalized for marker in markers)


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
    current_model = (
        cfg.get("agents", {})
        .get("defaults", {})
        .get("model", {})
        .get("primary")
        or get_openclaw_selection()
    )
    provider = current_model.split("/", 1)[0] if "/" in current_model else current_model
    provider_stats = ((auth.get("usageStats") or {}))
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


def basic_runtime_status():
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
    return info


def read_meminfo():
    data = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                key, _, value = line.partition(":")
                amount = value.strip().split()[0] if value.strip() else None
                if amount and amount.isdigit():
                    data[key] = int(amount)
    except FileNotFoundError:
        return {}
    return data


def kib_to_gib(value):
    if value in (None, 0):
        return None
    return round(value / 1024 / 1024, 1)


def collect_local_ai_hardware():
    meminfo = read_meminfo()
    total_ram_gib = kib_to_gib(meminfo.get("MemTotal"))
    total_swap_gib = kib_to_gib(meminfo.get("SwapTotal"))

    gpu_name = None
    gpu_vram_gib = None
    from shutil import which

    nvidia_path = which("nvidia-smi")
    if nvidia_path:
        nvidia = run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture=True,
            timeout=5,
        )
        if nvidia.returncode == 0:
            first = ((nvidia.stdout or "").strip().splitlines() or [""])[0]
            if "," in first:
                name, mem_mb = [part.strip() for part in first.split(",", 1)]
                gpu_name = name or None
                try:
                    gpu_vram_gib = round(int(mem_mb) / 1024, 1)
                except ValueError:
                    gpu_vram_gib = None

    cpu_name = None
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as fh:
            for raw_line in fh:
                if raw_line.startswith("model name"):
                    cpu_name = raw_line.split(":", 1)[1].strip()
                    break
    except FileNotFoundError:
        pass

    return {
        "cpu": cpu_name,
        "ram_gib": total_ram_gib,
        "swap_gib": total_swap_gib,
        "gpu": gpu_name,
        "gpu_vram_gib": gpu_vram_gib,
    }


def collect_ollama_status(refresh=False):
    global _OLLAMA_STATUS_CACHE
    if not refresh and _OLLAMA_STATUS_CACHE is not None:
        return _OLLAMA_STATUS_CACHE

    from shutil import which

    path = which("ollama")
    version = capture_version(["ollama", "--version"]) if path else None
    api_ok = False
    api_detail = "Ollama no instalado"
    models = []

    if path:
        curl_path = which("curl")
        if not curl_path:
            api_detail = "CLI presente, pero falta curl para consultar la API local"
        else:
            probe = run(["curl", "-fsS", "http://127.0.0.1:11434/api/tags"], capture=True, timeout=5)
            out = (probe.stdout or "").strip()
            if probe.returncode == 0 and '"models"' in out:
                api_ok = True
                api_detail = "API local respondiendo en 127.0.0.1:11434"
                try:
                    payload = json.loads(out)
                    models = [item.get("name") for item in payload.get("models", []) if item.get("name")]
                except Exception:
                    models = []
            else:
                api_detail = "CLI presente, pero la API local no responde"

    _OLLAMA_STATUS_CACHE = {
        "path": path,
        "version": version,
        "api_ok": api_ok,
        "api_detail": api_detail,
        "models": models,
    }
    return _OLLAMA_STATUS_CACHE


def preferred_local_ollama_model(refresh=False):
    global _PREFERRED_LOCAL_OLLAMA_MODEL_CACHE
    if not refresh and _PREFERRED_LOCAL_OLLAMA_MODEL_CACHE is not None:
        return _PREFERRED_LOCAL_OLLAMA_MODEL_CACHE

    status = collect_ollama_status(refresh=refresh)
    if not status["models"]:
        _PREFERRED_LOCAL_OLLAMA_MODEL_CACHE = None
        return None
    priority = [
        "qwen2.5:3b",
        "gemma3:4b",
        "llama3.2:3b",
        "hermes3:3b",
        "gemma3:1b",
    ]
    for candidate in priority:
        if candidate in status["models"]:
            _PREFERRED_LOCAL_OLLAMA_MODEL_CACHE = candidate
            return candidate
    _PREFERRED_LOCAL_OLLAMA_MODEL_CACHE = status["models"][0]
    return _PREFERRED_LOCAL_OLLAMA_MODEL_CACHE


def collect_nvidia_status():
    state = load_miliciano_state()
    nvidia_state = state.get("nvidia", {})
    api_key_present = bool(nvidia_state.get("api_key_present") or any(os.environ.get(name) for name in NVIDIA_API_ENV_VARS))
    return {
        "enabled": bool(nvidia_state.get("enabled")),
        "api_key_present": api_key_present,
        "base_url": nvidia_state.get("base_url") or NVIDIA_BASE_URL,
        "model": nvidia_state.get("model") or NVIDIA_DEFAULT_MODEL,
    }




def recommend_ollama_models(hardware):
    ram_gib = hardware.get("ram_gib") or 0
    gpu_vram_gib = hardware.get("gpu_vram_gib") or 0

    if gpu_vram_gib >= 8 and ram_gib >= 24:
        return [
            ("qwen2.5:7b", "mejor salto de calidad local para razonamiento/código"),
            ("gemma3:4b", "rápido y estable para uso diario"),
            ("hermes3:8b", "útil si priorizas estilo asistente por sobre velocidad"),
        ]
    if gpu_vram_gib >= 4 and ram_gib >= 16:
        return [
            ("qwen2.5:3b", "mejor base local para este equipo: más sólido que hermes3:3b"),
            ("gemma3:4b", "más calidad, pero algo más pesado"),
            ("llama3.2:3b", "alternativa equilibrada para tareas generales"),
            ("hermes3:3b", "sirve como fallback ligero si ya lo tienes"),
        ]
    if ram_gib >= 12:
        return [
            ("qwen2.5:3b", "usable con CPU/offload; buena relación calidad/recursos"),
            ("gemma3:1b", "la opción más liviana para mantener fluidez"),
            ("hermes3:3b", "válido como respaldo, pero menos consistente"),
        ]
    return [
        ("gemma3:1b", "la opción más realista para este hardware"),
        ("qwen2.5:1.5b", "alternativa pequeña si priorizas velocidad"),
    ]


def pull_ollama_model(model_name):
    return run_with_spinner(["ollama", "pull", model_name], f"Descargando {model_name} en Ollama")


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
    provider, model = split_provider_model(spec)
    return provider, model


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
    requested_role = forced_role or choose_route_for_prompt(prompt)[0]
    role = requested_role
    reason = None
    if forced_role:
        reason = f"ruta forzada por comando: {forced_role}"
    else:
        _, reason = choose_route_for_prompt(prompt)
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
