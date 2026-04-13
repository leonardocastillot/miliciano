#!/usr/bin/env python3
import os


MILICIANO_VERSION = "0.3.0"

MILICIANO_PREAMBLE = (
    "Eres Miliciano, partner tecnológico by Milytics. "
    "Responde español cuando usuario habla español. "
    "Token-optimized output: elimina articles/filler/pleasantries/hedging. Fragments OK. Short synonyms. "
    "Pattern: [cosa] [acción] [razón]. [siguiente paso]. "
    "No: 'Claro, con gusto te ayudo con eso.' "
    "Sí: 'Bug en auth middleware. Fix: línea 47 validación token.' "
    "Code/security explanations: write normal. Todo lo demás: ultra-compacto."
)

MILICIANO_HERMES_HOME = os.path.expanduser("~/.hermes/profiles/miliciano")
MILICIANO_GLOBAL_HERMES_CONFIG = os.path.expanduser("~/.hermes/config.yaml")
MILICIANO_PROFILE_CONFIG = os.path.join(MILICIANO_HERMES_HOME, "config.yaml")
MILICIANO_STATE_DIR = os.path.expanduser("~/.config/miliciano")
MILICIANO_STATE_PATH = os.path.join(MILICIANO_STATE_DIR, "config.json")
MILICIANO_SECRETS_PATH = os.path.join(MILICIANO_STATE_DIR, "secrets.json")
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
NVIDIA_DEFAULT_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
NVIDIA_DEPRECATED_MODEL_MAP = {
    "nvidia/llama-3.1-nemotron-70b-instruct": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/llama-3.1-nemotron-51b-instruct": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
}

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
DEBIAN_PYTHON_SYSTEM_PACKAGES = ("python3-pip", "python3-venv")

PROMPT_TOOLKIT_SPEC = "prompt_toolkit>=3.0.43"
SHELL_PYTHON_DEPENDENCIES = (
    {"module": "prompt_toolkit", "package": "prompt_toolkit>=3.0.43"},
    {"module": "wcwidth", "package": "wcwidth>=0.2.13"},
)
OPTIONAL_SECURITY_PYTHON_DEPENDENCIES = (
    {"module": "cryptography", "package": "cryptography>=41.0.0"},
    {"module": "keyring", "package": "keyring>=24.0.0"},
)
