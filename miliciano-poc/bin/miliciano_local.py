#!/usr/bin/env python3
import json

from miliciano_system import capture_version, read_json_file, run


_OLLAMA_STATUS_CACHE = None
_PREFERRED_LOCAL_OLLAMA_MODEL_CACHE = None


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
    try:
        from miliciano_cache import cache_get, cache_set
        cached = cache_get("local_hardware", ttl_seconds=300)
        if cached is not None:
            return cached
    except ImportError:
        cache_set = None

    meminfo = read_meminfo()
    total_ram_gib = kib_to_gib(meminfo.get("MemTotal"))
    total_swap_gib = kib_to_gib(meminfo.get("SwapTotal"))

    gpu_name = None
    gpu_vram_gib = None
    from shutil import which

    if which("nvidia-smi"):
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

    result = {
        "cpu": cpu_name,
        "ram_gib": total_ram_gib,
        "swap_gib": total_swap_gib,
        "gpu": gpu_name,
        "gpu_vram_gib": gpu_vram_gib,
    }

    if cache_set:
        cache_set("local_hardware", result)
    return result


def collect_ollama_status(refresh=False):
    global _OLLAMA_STATUS_CACHE

    if not refresh and _OLLAMA_STATUS_CACHE is not None:
        return _OLLAMA_STATUS_CACHE

    if not refresh:
        try:
            from miliciano_cache import cache_get
            cached = cache_get("ollama_status", ttl_seconds=120)
            if cached is not None:
                _OLLAMA_STATUS_CACHE = cached
                return cached
        except ImportError:
            pass

    from shutil import which

    path = which("ollama")
    version = capture_version(["ollama", "--version"]) if path else None
    api_ok = False
    api_detail = "Ollama no instalado"
    models = []

    if path:
        if not which("curl"):
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

    result = {
        "path": path,
        "version": version,
        "api_ok": api_ok,
        "api_detail": api_detail,
        "models": models,
    }
    _OLLAMA_STATUS_CACHE = result

    try:
        from miliciano_cache import cache_set
        cache_set("ollama_status", result)
    except ImportError:
        pass
    return result


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
    from miliciano_system import run_with_spinner
    return run_with_spinner(["ollama", "pull", model_name], f"Descargando {model_name} en Ollama")
