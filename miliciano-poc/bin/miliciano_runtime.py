#!/usr/bin/env python3
import base64
import codecs
import html
import json
import os
import platform
import pty
import re
import select
import subprocess
import sys
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from textwrap import dedent, wrap

from miliciano_ui import *


MILICIANO_PREAMBLE = None

MILICIANO_HERMES_HOME = os.path.expanduser("~/.hermes/profiles/miliciano")
MILICIANO_GLOBAL_HERMES_CONFIG = os.path.expanduser("~/.hermes/config.yaml")
MILICIANO_PROFILE_CONFIG = os.path.join(MILICIANO_HERMES_HOME, "config.yaml")
MILICIANO_STATE_DIR = os.path.expanduser("~/.config/miliciano")
MILICIANO_STATE_PATH = os.path.join(MILICIANO_STATE_DIR, "config.json")
MILICIANO_JOBS_PATH = os.path.join(MILICIANO_STATE_DIR, "jobs.json")
MILICIANO_ORCHESTRATION_REPORT_PATH = os.path.join(MILICIANO_STATE_DIR, "orchestration-report.json")
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

OUTPUT_MODES = {"simple", "operator", "debug"}
ROUTE_MODES = {"cheap", "balanced", "max"}
PERMISSION_MODES = {"plan", "ask", "accept-edits", "execute", "restricted-boundary"}

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

REQUIRED_SYSTEM_COMMANDS = ["python3", "node", "npm", "curl"]
OPTIONAL_SYSTEM_COMMANDS = ["docker", "git", "tar", "zstd"]
PREREQ_COMMANDS = REQUIRED_SYSTEM_COMMANDS + OPTIONAL_SYSTEM_COMMANDS


_STATE_CACHE = None
_OLLAMA_STATUS_CACHE = None
_PREFERRED_LOCAL_OLLAMA_MODEL_CACHE = None

PERSONA_PRESETS = {
    "operator": {
        "label": "operator",
        "tone": "directo, ejecutivo y orientado a resolver",
        "style": "prioriza claridad, acción y seguimiento",
    },
    "guardian": {
        "label": "guardian",
        "tone": "calmado, confiable y muy cuidadoso con riesgo",
        "style": "prioriza seguridad, validación y trazabilidad",
    },
    "builder": {
        "label": "builder",
        "tone": "creativo, técnico y obsesionado con construir",
        "style": "prioriza iteración, diseño y shipping rápido",
    },
    "concierge": {
        "label": "concierge",
        "tone": "cercano, amable y resolutivo",
        "style": "prioriza comodidad, guía y experiencia humana",
    },
}

IDENTITY_ENV_VARS = {
    "partner_name": "MILICIANO_PARTNER_NAME",
    "persona_key": "MILICIANO_PERSONA",
    "owner_name": "MILICIANO_OWNER_NAME",
    "language": "MILICIANO_LANGUAGE",
    "interaction_style": "MILICIANO_INTERACTION_STYLE",
}


def find_miliciano_project_file(start_dir=None):
    current = os.path.abspath(start_dir or os.getcwd())
    while True:
        candidate = os.path.join(current, "MILICIANO.md")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def load_miliciano_project_instructions(start_dir=None, max_lines=120, max_chars=5000):
    path = find_miliciano_project_file(start_dir=start_dir)
    if not path:
        return {"path": None, "present": False, "content": ""}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()[:max_lines]
    except Exception:
        return {"path": path, "present": True, "content": ""}
    content = "".join(lines).strip()
    if len(content) > max_chars:
        content = content[:max_chars].rstrip() + "\n..."
    return {"path": path, "present": True, "content": content}


def base_env():
    env = os.environ.copy()
    env.setdefault("HERMES_HOME", MILICIANO_HERMES_HOME)
    local_bin = os.path.expanduser("~/.local/bin")
    current_path = env.get("PATH", "")
    if local_bin not in current_path.split(":"):
        env["PATH"] = f"{local_bin}:{current_path}" if current_path else local_bin
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


def run_with_live_output(cmd, label, env=None):
    effective_env = env or base_env()
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        env=effective_env,
        close_fds=True,
    )
    os.close(slave_fd)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    chunks = []
    buffer = ""
    label_printed = False
    try:
        while True:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd in ready:
                try:
                    data = os.read(master_fd, 1024)
                except OSError:
                    data = b""
                if not data:
                    if proc.poll() is not None:
                        break
                    continue
                text = decoder.decode(data)
                if text:
                    if not label_printed:
                        print(rule(f" Miliciano · {label} ", "─"), flush=True)
                        label_printed = True
                    chunks.append(text)
                    sys.stdout.write(text)
                    sys.stdout.flush()
            if proc.poll() is not None and not ready:
                break
        remainder = decoder.decode(b"", final=True)
        if remainder:
            chunks.append(remainder)
            sys.stdout.write(remainder)
            sys.stdout.flush()
    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
        raise
    finally:
        try:
            os.close(master_fd)
        except Exception:
            pass
    out = "".join(chunks)
    if label_printed and not out.endswith("\n"):
        sys.stdout.write("\n")
        sys.stdout.flush()
    return subprocess.CompletedProcess(cmd, proc.returncode, out, None)


def run_openclaw_agent(message, stream_output=False):
    runner = run_with_live_output if stream_output else run_with_spinner
    res = runner(["openclaw", "agent", "--agent", "main", "--message", message], "Ejecutando con OpenClaw")
    out = (res.stdout or "").strip()
    if not stream_output:
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
        "preferences": {
            "output_mode": "simple",
            "route_mode": "balanced",
            "permission_mode": "ask",
        },
        "identity": {
            "partner_name": "Miliciano",
            "persona_key": "operator",
            "language": "es",
            "interaction_style": "directo y útil",
            "owner_name": None,
        },
        "jobs": {},
        "tasks": {},
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




def normalize_miliciano_state(state):
    if not isinstance(state.get("routing"), dict):
        state["routing"] = {}
    if not isinstance(state.get("ollama"), dict):
        state["ollama"] = {}
    if not isinstance(state.get("nvidia"), dict):
        state["nvidia"] = {}
    if not isinstance(state.get("preferences"), dict):
        state["preferences"] = {}
    if not isinstance(state.get("identity"), dict):
        state["identity"] = {}
    if not isinstance(state.get("jobs"), dict):
        state["jobs"] = {}
    if not isinstance(state.get("tasks"), dict):
        state["tasks"] = {}

    fallback = state.get("routing", {}).get("fallback")
    if isinstance(fallback, str) and fallback.startswith("nvidia/nvidia/"):
        state["routing"]["fallback"] = fallback.replace("nvidia/nvidia/", "nvidia/", 1)

    local_model_name = preferred_local_ollama_model()
    local_spec = current_local_hermes_spec(local_model_name)
    if local_spec:
        state["routing"].setdefault("local", local_spec)
        reasoning_spec = make_model_spec(state["hermes"]["provider"], state["hermes"]["model"])
        current_fast = state["routing"].get("fast")
        if current_fast in {None, "", reasoning_spec} and state.get("ollama", {}).get("auto_install", True):
            state["routing"]["fast"] = local_spec
        state["ollama"].setdefault("preferred_model", local_model_name)

    prefs = state["preferences"]
    if prefs.get("output_mode") not in OUTPUT_MODES:
        prefs["output_mode"] = "simple"
    if prefs.get("route_mode") not in ROUTE_MODES:
        prefs["route_mode"] = "balanced"
    if prefs.get("permission_mode") not in PERMISSION_MODES:
        prefs["permission_mode"] = "ask"

    identity = state["identity"]
    identity.setdefault("partner_name", "Miliciano")
    if identity.get("persona_key") not in PERSONA_PRESETS:
        identity["persona_key"] = "operator"
    identity.setdefault("language", "es")
    identity.setdefault("interaction_style", "directo y útil")
    identity.setdefault("owner_name", None)

    return state

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

    state = normalize_miliciano_state(state)

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


def _set_preference(name, value, allowed_values):
    if value not in allowed_values:
        raise ValueError(f"valor inválido para {name}: {value}")
    state = load_miliciano_state(refresh=True)
    state.setdefault("preferences", {})[name] = value
    save_miliciano_state(state)
    return value


def get_output_mode():
    return load_miliciano_state().get("preferences", {}).get("output_mode", "simple")


def set_output_mode(mode):
    return _set_preference("output_mode", mode, OUTPUT_MODES)


def get_route_mode():
    return load_miliciano_state().get("preferences", {}).get("route_mode", "balanced")


def set_route_mode(mode):
    return _set_preference("route_mode", mode, ROUTE_MODES)


def get_permission_mode():
    return load_miliciano_state().get("preferences", {}).get("permission_mode", "ask")


def set_permission_mode(mode):
    return _set_preference("permission_mode", mode, PERMISSION_MODES)


def identity_env_defaults():
    defaults = {}
    for key, env_name in IDENTITY_ENV_VARS.items():
        value = os.environ.get(env_name, "").strip()
        if value:
            defaults[key] = value
    return defaults


def seed_partner_identity_from_env(persist=False):
    state = load_miliciano_state(refresh=True)
    identity = state.setdefault("identity", {})
    defaults = identity_env_defaults()
    changed = False
    for key, value in defaults.items():
        if key == "persona_key" and value not in PERSONA_PRESETS:
            continue
        if not identity.get(key):
            identity[key] = value
            changed = True
    if changed or persist:
        save_miliciano_state(state)
    return get_partner_identity()


def get_partner_identity():
    state = load_miliciano_state()
    identity = dict(state.get("identity", {}))
    defaults = identity_env_defaults()
    for key, value in defaults.items():
        if key == "persona_key" and value not in PERSONA_PRESETS:
            continue
        identity.setdefault(key, value)
    preset = PERSONA_PRESETS.get(identity.get("persona_key") or "operator", PERSONA_PRESETS["operator"])
    identity["persona"] = preset
    return identity


def set_partner_identity(partner_name=None, persona_key=None, language=None, interaction_style=None, owner_name=None):
    state = load_miliciano_state(refresh=True)
    identity = state.setdefault("identity", {})
    if partner_name is not None:
        identity["partner_name"] = partner_name.strip() or "Miliciano"
    if persona_key is not None:
        if persona_key not in PERSONA_PRESETS:
            raise ValueError(f"persona inválida: {persona_key}")
        identity["persona_key"] = persona_key
    if language is not None:
        identity["language"] = language.strip() or "es"
    if interaction_style is not None:
        identity["interaction_style"] = interaction_style.strip() or "directo y útil"
    if owner_name is not None:
        identity["owner_name"] = owner_name.strip() or None
    save_miliciano_state(state)
    return get_partner_identity()


def load_miliciano_jobs(refresh=False):
    state = load_miliciano_state(refresh=refresh)
    jobs = state.get("jobs") or {}
    if not isinstance(jobs, dict):
        jobs = {}
    return jobs


def save_miliciano_jobs(jobs):
    state = load_miliciano_state(refresh=True)
    state["jobs"] = jobs or {}
    save_miliciano_state(state)
    return state["jobs"]


def load_miliciano_tasks(refresh=False):
    state = load_miliciano_state(refresh=refresh)
    tasks = state.get("tasks") or {}
    if not isinstance(tasks, dict):
        tasks = {}
    return tasks


def save_miliciano_tasks(tasks):
    state = load_miliciano_state(refresh=True)
    state["tasks"] = tasks or {}
    save_miliciano_state(state)
    return state["tasks"]


def create_miliciano_task(title, note="", status="pending", priority="medium"):
    tasks = load_miliciano_tasks(refresh=True)
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    tasks[task_id] = {
        "id": task_id,
        "title": (title or "Task Miliciano").strip(),
        "note": (note or "").strip(),
        "status": status if status in {"pending", "in_progress", "completed", "cancelled"} else "pending",
        "priority": priority if priority in {"low", "medium", "high"} else "medium",
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "done_at": None,
    }
    save_miliciano_tasks(tasks)
    return tasks[task_id]


def update_miliciano_task(task_id, **fields):
    tasks = load_miliciano_tasks(refresh=True)
    task = tasks.get(task_id)
    if not task:
        raise KeyError(task_id)
    for key, value in fields.items():
        if value is not None:
            task[key] = value
    task["updated_at"] = int(time.time())
    if task.get("status") in {"completed", "cancelled"} and not task.get("done_at"):
        task["done_at"] = int(time.time())
    tasks[task_id] = task
    save_miliciano_tasks(tasks)
    return task


def remove_miliciano_task(task_id):
    tasks = load_miliciano_tasks(refresh=True)
    if task_id not in tasks:
        return False
    tasks.pop(task_id, None)
    save_miliciano_tasks(tasks)
    return True


def list_miliciano_tasks():
    tasks = load_miliciano_tasks()
    return [tasks[k] for k in sorted(tasks.keys())]


def list_open_miliciano_tasks():
    return [task for task in list_miliciano_tasks() if task.get("status") not in {"completed", "cancelled"}]


def summarize_miliciano_task(task):
    return f"{task.get('id')} · {task.get('status')} · {task.get('priority')} · {task.get('title')}"


def task_priority_score(task):
    priority = task.get("priority") or "medium"
    status = task.get("status") or "pending"
    priority_score = {"high": 0, "medium": 1, "low": 2}.get(priority, 1)
    status_score = {"in_progress": 0, "pending": 1, "cancelled": 2, "completed": 3}.get(status, 1)
    return (status_score, priority_score, task.get("created_at") or 0)


def sort_open_miliciano_tasks(tasks=None):
    tasks = tasks if tasks is not None else list_open_miliciano_tasks()
    return sorted(tasks, key=task_priority_score)


def complete_miliciano_task(task_id):
    return update_miliciano_task(task_id, status="completed")


def cron_field_matches(field, value, min_value, max_value):

    if field in {"*", "?"}:
        return True
    if field.startswith("*/"):
        try:
            step = int(field[2:])
            return step > 0 and value % step == 0
        except ValueError:
            return False

    matched = False
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        if part == "*":
            return True
        if "/" in part:
            base, step_text = part.split("/", 1)
            try:
                step = int(step_text)
            except ValueError:
                continue
            if step <= 0:
                continue
            if base == "*":
                if value % step == 0:
                    matched = True
            elif "-" in base:
                start_text, end_text = base.split("-", 1)
                try:
                    start = int(start_text)
                    end = int(end_text)
                except ValueError:
                    continue
                if start <= value <= end and (value - start) % step == 0:
                    matched = True
            else:
                try:
                    start = int(base)
                except ValueError:
                    continue
                if value >= start and (value - start) % step == 0:
                    matched = True
            continue
        if "-" in part:
            try:
                start_text, end_text = part.split("-", 1)
                start = int(start_text)
                end = int(end_text)
            except ValueError:
                continue
            if start <= value <= end:
                matched = True
            continue
        try:
            if int(part) == value:
                matched = True
        except ValueError:
            continue
    return matched


def parse_schedule_spec(schedule):
    schedule = (schedule or "").strip().lower()
    if not schedule:
        return {"kind": "manual", "raw": schedule}
    if schedule.startswith("every "):
        body = schedule[6:].strip()
        match = re.fullmatch(r"(\d+)\s*([mhd])", body)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            multiplier = {"m": 60, "h": 3600, "d": 86400}[unit]
            return {"kind": "interval", "seconds": amount * multiplier, "raw": schedule}
    if re.fullmatch(r"(\d+)\s*([mhd])", schedule):
        amount = int(re.fullmatch(r"(\d+)\s*([mhd])", schedule).group(1))
        unit = re.fullmatch(r"(\d+)\s*([mhd])", schedule).group(2)
        multiplier = {"m": 60, "h": 3600, "d": 86400}[unit]
        return {"kind": "interval", "seconds": amount * multiplier, "raw": schedule}

    parts = schedule.split()
    if len(parts) == 5:
        return {"kind": "cron", "fields": parts, "raw": schedule}
    return {"kind": "manual", "raw": schedule}


def schedule_due(job, now_ts=None):
    now = datetime.fromtimestamp(now_ts or time.time(), tz=timezone.utc).astimezone()
    spec = parse_schedule_spec(job.get("schedule"))
    last_run_at = job.get("last_run_at")
    if spec["kind"] == "manual":
        return False
    if spec["kind"] == "interval":
        if last_run_at is None:
            return True
        return (now.timestamp() - float(last_run_at)) >= spec["seconds"]
    if spec["kind"] == "cron":
        minute, hour, dom, month, dow = spec["fields"]
        cron_dow = (now.weekday() + 1) % 7
        if not (
            cron_field_matches(minute, now.minute, 0, 59)
            and cron_field_matches(hour, now.hour, 0, 23)
            and cron_field_matches(dom, now.day, 1, 31)
            and cron_field_matches(month, now.month, 1, 12)
            and cron_field_matches(dow, cron_dow, 0, 7)
        ):
            return False
        if last_run_at is None:
            return True
        last = datetime.fromtimestamp(float(last_run_at), tz=timezone.utc).astimezone()
        return not (
            last.year == now.year
            and last.month == now.month
            and last.day == now.day
            and last.hour == now.hour
            and last.minute == now.minute
        )
    return False


def create_miliciano_job(title, schedule, prompt, target="ask", enabled=True, repeat=None):
    jobs = load_miliciano_jobs(refresh=True)
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    jobs[job_id] = {
        "id": job_id,
        "title": (title or "Job Miliciano").strip(),
        "schedule": (schedule or "").strip(),
        "prompt": (prompt or "").strip(),
        "target": target,
        "enabled": bool(enabled),
        "repeat": repeat,
        "created_at": int(time.time()),
        "last_run_at": None,
        "last_status": None,
        "last_result": None,
    }
    save_miliciano_jobs(jobs)
    return jobs[job_id]


def update_miliciano_job(job_id, **fields):
    jobs = load_miliciano_jobs(refresh=True)
    job = jobs.get(job_id)
    if not job:
        raise KeyError(job_id)
    for key, value in fields.items():
        if value is not None:
            job[key] = value
    jobs[job_id] = job
    save_miliciano_jobs(jobs)
    return job


def remove_miliciano_job(job_id):
    jobs = load_miliciano_jobs(refresh=True)
    if job_id not in jobs:
        return False
    jobs.pop(job_id, None)
    save_miliciano_jobs(jobs)
    return True


def list_miliciano_jobs():
    jobs = load_miliciano_jobs()
    return [jobs[k] for k in sorted(jobs.keys())]


def list_due_miliciano_jobs(now_ts=None):
    return [job for job in list_miliciano_jobs() if job.get("enabled", True) and schedule_due(job, now_ts=now_ts)]


def render_job_summary(job):
    status = "on" if job.get("enabled") else "off"
    return f"{job.get('id')} · {status} · {job.get('schedule') or 'sin cron'} · {job.get('title') or 'sin título'}"


def run_miliciano_job(job_id):
    from miliciano_exec import orchestrate_partner_request

    jobs = load_miliciano_jobs(refresh=True)
    job = jobs.get(job_id)
    if not job:
        raise KeyError(job_id)
    target = (job.get("target") or "ask").lower()
    prompt = job.get("prompt") or job.get("title") or ""
    if not prompt:
        raise ValueError("job sin prompt")
    if target == "exec":
        rc, clean, _ = orchestrate_partner_request(prompt, force_mode="execution")
    elif target == "mission":
        rc, clean, _ = orchestrate_partner_request(prompt, force_mode="hybrid")
    elif target == "boundary":
        rc, clean, _ = orchestrate_partner_request(prompt, force_mode="external")
    elif target == "think":
        rc, clean, _ = orchestrate_partner_request(prompt, force_mode="reasoning")
    else:
        rc, clean, _ = orchestrate_partner_request(prompt)
    job["last_run_at"] = int(time.time())
    job["last_status"] = rc
    job["last_result"] = clean
    jobs[job_id] = job
    save_miliciano_jobs(jobs)
    return rc, clean, job


def run_due_miliciano_jobs(now_ts=None, limit=None):
    due = list_due_miliciano_jobs(now_ts=now_ts)
    results = []
    for job in due[: limit or len(due)]:
        try:
            rc, clean, updated = run_miliciano_job(job["id"])
            results.append({"id": job["id"], "title": job.get("title"), "rc": rc, "output": clean, "job": updated})
        except Exception as exc:
            results.append({"id": job["id"], "title": job.get("title"), "rc": 1, "output": str(exc), "job": job})
    return results


def scheduler_loop(interval_seconds=60, quiet=False):
    interval_seconds = max(10, int(interval_seconds or 60))
    while True:
        results = run_due_miliciano_jobs()
        if results and not quiet:
            for result in results:
                title = result.get("title") or result["id"]
                print(f"[scheduler] {title}: rc={result['rc']}")
                if result.get("output"):
                    print(result["output"])
        time.sleep(interval_seconds)


def render_partner_preamble():
    identity = get_partner_identity()
    persona = identity.get("persona") or PERSONA_PRESETS["operator"]
    partner_name = identity.get("partner_name") or "Miliciano"
    owner_name = identity.get("owner_name")
    owner_line = f"Tu operador principal es {owner_name}. " if owner_name else ""
    language = identity.get("language") or "es"
    language_line = "Responde en español. " if language.startswith("es") else "Respond in English. "
    interaction_style = identity.get("interaction_style") or "directo y útil"
    return (
        f"Responde como {partner_name}, un partner tecnológico by Milytics. "
        "No te presentes como Hermes salvo que te pregunten por la arquitectura interna. "
        f"{language_line}"
        f"Tu tono debe ser {persona['tone']}. "
        f"Tu estilo operativo debe ser {persona['style']}. "
        f"Tu estilo de interacción debe sentirse {interaction_style}. "
        f"{owner_line}"
        "Optimiza tokens: responde corto, sin repetir ideas, sin introducciones innecesarias. "
        "Usa solo el mínimo texto útil para resolver la tarea."
    )


def get_miliciano_preamble():
    return render_partner_preamble()


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


def build_orchestration_decision(intent, target, reason, needs_execution=False, needs_policy=False, needs_external=False):
    return {
        "intent": intent,
        "target": target,
        "reason": reason,
        "needs_execution": needs_execution,
        "needs_policy": needs_policy,
        "needs_external": needs_external,
    }


def build_policy_result(verdict, reason, requires_confirmation=False, mode=None, next_step=None, allowed_actions=None):
    return {
        "verdict": verdict,
        "reason": reason,
        "requires_confirmation": requires_confirmation,
        "mode": mode,
        "next_step": next_step,
        "allowed_actions": allowed_actions or [],
    }


def build_execution_report(target, outcome, summary, verified=False):
    return {
        "target": target,
        "outcome": outcome,
        "summary": summary,
        "verified": verified,
    }


def detect_sensitive_action(prompt):
    text = (prompt or "").lower()
    markers = [
        "sudo",
        "rm -rf",
        "delete",
        "borrar",
        "credential",
        "secret",
        "token",
        "api key",
        "expose",
        "publish",
        "webhook",
        "deploy",
        "firewall",
    ]
    return [marker for marker in markers if marker in text]


def detect_externalization_intent(prompt):
    text = (prompt or "").lower()
    markers = [
        "extern",
        "afuera",
        "public",
        "webhook",
        "agent",
        "servicio",
        "service",
        "whatsapp",
        "telegram",
        "discord",
        "expose",
        "endpoint",
        "api pública",
    ]
    return [marker for marker in markers if marker in text]


def classify_orchestration_intent(prompt, forced_mode=None):
    if forced_mode in {"reasoning", "execution", "hybrid", "external"}:
        return build_orchestration_decision(
            intent=forced_mode,
            target=("hermes" if forced_mode == "reasoning" else "openclaw" if forced_mode == "execution" else "hybrid" if forced_mode == "hybrid" else "nemoclaw"),
            reason=f"modo forzado: {forced_mode}",
            needs_execution=forced_mode in {"execution", "hybrid"},
            needs_policy=forced_mode in {"execution", "hybrid", "external"},
            needs_external=forced_mode == "external",
        )

    text = (prompt or "").strip().lower()
    external_hits = detect_externalization_intent(text)
    sensitive_hits = detect_sensitive_action(text)
    reasoning_hits = [kw for kw in REASONING_ROUTE_KEYWORDS if kw in text]

    if external_hits:
        return build_orchestration_decision(
            intent="external",
            target="nemoclaw",
            reason=f"detecté intención outward/external ({external_hits[0]})",
            needs_execution=True,
            needs_policy=True,
            needs_external=True,
        )
    if sensitive_hits:
        return build_orchestration_decision(
            intent="hybrid",
            target="openclaw",
            reason=f"detecté acción sensible ({sensitive_hits[0]})",
            needs_execution=True,
            needs_policy=True,
            needs_external=False,
        )
    if reasoning_hits or len(text) > 280:
        return build_orchestration_decision(
            intent="reasoning",
            target="hermes",
            reason=f"detecté tarea de razonamiento ({reasoning_hits[0] if reasoning_hits else 'prompt largo'})",
            needs_execution=False,
            needs_policy=False,
            needs_external=False,
        )
    simple_route, simple_reason = choose_route_for_prompt(text)
    if simple_route == "fast":
        return build_orchestration_decision(
            intent="reasoning",
            target="hermes",
            reason=simple_reason,
            needs_execution=False,
            needs_policy=False,
            needs_external=False,
        )
    return build_orchestration_decision(
        intent="hybrid" if any(word in text for word in ["haz", "ejecuta", "run", "crea", "make", "instala", "configura"]) else "reasoning",
        target="openclaw" if any(word in text for word in ["haz", "ejecuta", "run", "crea", "make", "instala", "configura"]) else "hermes",
        reason="clasificación por defecto de Miliciano",
        needs_execution=any(word in text for word in ["haz", "ejecuta", "run", "crea", "make", "instala", "configura"]),
        needs_policy=any(word in text for word in ["haz", "ejecuta", "run", "crea", "make", "instala", "configura"]),
        needs_external=False,
    )


def evaluate_policy_for_prompt(prompt, decision):
    text = (prompt or "").lower()
    sensitive_hits = detect_sensitive_action(text)
    permission_mode = get_permission_mode()
    allow_reasoning_only = ["reasoning", "read", "status", "trace"]

    if permission_mode == "plan":
        if decision.get("needs_execution") or decision.get("needs_external"):
            return build_policy_result(
                "deny",
                "modo plan: solo permito análisis; cambia a `miliciano mode permission execute` o `ask` para ejecutar",
                requires_confirmation=True,
                mode=permission_mode,
                next_step="cambia a un modo con ejecución habilitada",
                allowed_actions=allow_reasoning_only,
            )
        return build_policy_result("allow", "modo plan: reasoning permitido, ejecución bloqueada", False, mode=permission_mode, allowed_actions=allow_reasoning_only)

    if permission_mode == "restricted-boundary" and decision.get("needs_external"):
        return build_policy_result(
            "deny",
            "modo restricted-boundary: la salida al exterior está bloqueada hasta aprobación explícita",
            requires_confirmation=True,
            mode=permission_mode,
            next_step="usa boundary con aprobación explícita o cambia el modo de permisos",
            allowed_actions=["reasoning", "local execution"],
        )

    if permission_mode == "accept-edits" and (decision.get("needs_external") or any(hit in text for hit in ["run", "ejecuta", "instala", "deploy", "webhook", "sudo"])):
        return build_policy_result(
            "ask",
            "modo accept-edits: permito edición/plan, pero comandos o acciones outward requieren aprobación",
            requires_confirmation=True,
            mode=permission_mode,
            next_step="confirma la acción o cambia a execute si confías en este entorno",
            allowed_actions=["reasoning", "file edits"],
        )

    if any(marker in text for marker in ["rm -rf /", "wipe disk", "format disk"]):
        return build_policy_result("deny", "acción destructiva clara; requiere revisión humana", requires_confirmation=True, mode=permission_mode)
    if decision.get("needs_external"):
        return build_policy_result("ask", "la tarea quiere salir al exterior; requiere boundary/policy antes de ejecutar", requires_confirmation=True, mode=permission_mode, next_step="revisa boundary y confirma exposición")
    if sensitive_hits:
        return build_policy_result("ask", f"detecté operación sensible ({sensitive_hits[0]})", requires_confirmation=True, mode=permission_mode, next_step="confirma la acción sensible antes de seguir")
    return build_policy_result("allow", "sin señales de riesgo crítico en esta fase", requires_confirmation=False, mode=permission_mode)


def load_last_orchestration_report():
    return read_json_file(MILICIANO_ORCHESTRATION_REPORT_PATH) or {}


def save_orchestration_report(decision=None, policy=None, execution=None):
    current = load_last_orchestration_report()
    if decision is not None:
        current["decision"] = decision
    if policy is not None:
        current["policy"] = policy
    if execution is not None:
        current["execution"] = execution
    write_json_file(MILICIANO_ORCHESTRATION_REPORT_PATH, current)
    return current


def update_orchestration_report(**fields):
    current = load_last_orchestration_report()
    current.update(fields)
    write_json_file(MILICIANO_ORCHESTRATION_REPORT_PATH, current)
    return current


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
    pool = (auth.get("credential_pool") or {}).get(active_provider, [])
    last_profile = pool[0] if pool else {}
    access_token = last_profile.get("access_token") or (provider_entry.get("tokens") or {}).get("access_token")
    payload = decode_jwt_payload(access_token)
    auth_claims = payload.get("https://api.openai.com/auth", {})
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
        "email": payload.get("email") or (payload.get("https://api.openai.com/profile", {}) or {}).get("email"),
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

    version_commands = {
        "python3": ["python3", "--version"],
        "node": ["node", "-v"],
        "npm": ["npm", "-v"],
        "curl": ["curl", "--version"],
        "docker": ["docker", "--version"],
        "git": ["git", "--version"],
        "tar": ["tar", "--version"],
        "zstd": ["zstd", "--version"],
    }

    info = {}
    for cmd in PREREQ_COMMANDS:
        path = which(cmd)
        version = None
        if path:
            version = capture_version(version_commands.get(cmd, [cmd, "--version"]))
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


def probe_reasoning_path():
    from shutil import which
    if which("hermes") is None:
        return {"ok": False, "kind": "error", "summary": "Hermes no está instalado"}
    provider, model = get_hermes_selection()
    return {"ok": True, "kind": "ready", "summary": f"reasoning disponible con {provider}/{model}"}


def probe_execution_path():
    from shutil import which
    if which("openclaw") is None:
        return {"ok": False, "kind": "error", "summary": "OpenClaw no está instalado"}
    health = run(["openclaw", "health", "--json"], capture=True, timeout=6)
    out = (health.stdout or "").strip()
    ok = bool(health.returncode == 0 and '"ok":true' in out.lower().replace(" ", ""))
    if ok:
        return {"ok": True, "kind": "ready", "summary": "gateway y ejecución base responden"}
    return {"ok": False, "kind": "pending", "summary": "gateway OpenClaw no confirmó salud end-to-end"}


def probe_local_path():
    status = collect_ollama_status()
    local_model = preferred_local_ollama_model()
    if not status.get("path"):
        return {"ok": False, "kind": "pending", "summary": "Ollama no está instalado"}
    if not status.get("api_ok"):
        return {"ok": False, "kind": "pending", "summary": status.get("api_detail") or "API local no responde"}
    if not local_model:
        return {"ok": False, "kind": "pending", "summary": "no hay modelo local preferido en Ollama"}
    return {"ok": True, "kind": "ready", "summary": f"local fast path listo con {local_model}"}


def probe_boundary_path():
    from shutil import which
    if which("nemoclaw") is None:
        return {"ok": False, "kind": "pending", "summary": "Nemoclaw no está instalado"}
    res = run(["nemoclaw", "--version"], capture=True, timeout=6)
    if res.returncode != 0:
        return {"ok": False, "kind": "error", "summary": "Nemoclaw está presente pero no operativo"}
    return {"ok": True, "kind": "info", "summary": "boundary base disponible; outward workflow completo sigue pendiente"}




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


def resolve_route_mode_for_prompt(prompt):
    return get_route_mode()


def apply_route_mode_override(route, prompt, forced_role=None):
    if forced_role:
        route["reason"] = f"{route['reason']} · respeté la ruta forzada"
        return route

    mode = resolve_route_mode_for_prompt(prompt)
    text = (prompt or "").strip().lower()
    local_spec = get_route_selection("local")
    fast_spec = get_route_selection("fast")
    simple_fast = bool(fast_spec) and (
        any(kw in text for kw in FAST_ROUTE_KEYWORDS) or len(text.split()) <= 18 or len(text) <= 140
    )

    if mode == "cheap":
        if simple_fast and fast_spec:
            provider, model = parse_hermes_route_spec(fast_spec)
            return {
                "role": "fast",
                "provider": provider,
                "model": model,
                "spec": fast_spec,
                "reason": f"modo cheap: prioricé velocidad/costo con la ruta fast ({fast_spec})",
            }
        if local_spec and route["role"] == "reasoning" and len(text) <= 220:
            provider, model = parse_hermes_route_spec(local_spec)
            return {
                "role": "local",
                "provider": provider,
                "model": model,
                "spec": local_spec,
                "reason": f"modo cheap: preferí la base local ({local_spec}) para evitar costo premium",
            }
        route["reason"] = f"{route['reason']} · modo cheap mantuvo la mejor ruta disponible"
        return route

    if mode == "max":
        reasoning_spec = get_route_selection("reasoning")
        if reasoning_spec and route["role"] in {"fast", "local"}:
            provider, model = parse_hermes_route_spec(reasoning_spec)
            return {
                "role": "reasoning",
                "provider": provider,
                "model": model,
                "spec": reasoning_spec,
                "reason": f"modo max: escalé a reasoning premium para máxima calidad",
            }
        route["reason"] = f"{route['reason']} · modo max conservó reasoning principal"
        return route

    route["reason"] = f"{route['reason']} · modo balanced"
    return route


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
    route = {
        "role": role,
        "provider": provider,
        "model": model,
        "spec": spec,
        "reason": reason,
    }
    return apply_route_mode_override(route, prompt, forced_role=forced_role)


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
