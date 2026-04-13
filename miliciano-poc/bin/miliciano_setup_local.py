#!/usr/bin/env python3
import os
from pathlib import Path

from miliciano_local import collect_ollama_status
from miliciano_runtime import pull_ollama_model, run, run_with_spinner


def install_ollama_if_needed(box_line, download_and_verify_script, trusted_sources):
    current = collect_ollama_status(refresh=True)
    if current["path"]:
        return current
    box_line("• Ollama no está instalado; intento instalarlo automáticamente")

    try:
        script_path = download_and_verify_script(trusted_sources["ollama"]["url"])
        try:
            install_run = run_with_spinner(["bash", script_path], "Instalando Ollama")
        finally:
            try:
                os.remove(script_path)
            except Exception:
                pass
    except Exception as exc:
        box_line(f"  Error descargando instalador: {exc}")
        install_run = type("obj", (object,), {"returncode": 1, "stdout": ""})()

    if install_run.returncode != 0:
        out = (install_run.stdout or "").strip()
        if out:
            box_line(out)
        box_line("  El instalador oficial pidió sudo o falló; pruebo instalación portable en ~/.local")
        machine = os.uname().machine
        arch = "amd64" if machine in {"x86_64", "amd64"} else "arm64" if machine in {"aarch64", "arm64"} else None
        if arch:
            portable_cmd = (
                "set -euo pipefail; mkdir -p ~/.local/bin ~/.local/lib/ollama; "
                f"curl -fsSL https://ollama.com/download/ollama-linux-{arch}.tar.zst | zstd -d | tar -xf - -C ~/.local; "
                "chmod +x ~/.local/ollama; ln -sf ~/.local/ollama ~/.local/bin/ollama"
            )
            portable_run = run(["bash", "-lc", portable_cmd], capture=True, timeout=600)
            if portable_run.returncode == 0 and (Path.home() / ".local" / "bin" / "ollama").exists():
                box_line("  Ollama quedó instalado en ~/.local/bin/ollama.")
                return collect_ollama_status(refresh=True)
            portable_out = (portable_run.stdout or "").strip()
            if portable_out:
                box_line(portable_out)
        box_line("  No pude instalar Ollama automáticamente.")
        return collect_ollama_status(refresh=True)

    box_line("  Ollama instalado.")
    return collect_ollama_status(refresh=True)


def start_ollama_if_needed(box_line):
    current = collect_ollama_status(refresh=True)
    if current["api_ok"]:
        return current
    box_line("• La API local de Ollama no responde; intento levantar el servidor")
    start_run = run(["bash", "-lc", "nohup ollama serve >/tmp/miliciano-ollama.log 2>&1 </dev/null & sleep 2"], capture=True, timeout=10)
    if start_run.returncode != 0:
        out = (start_run.stdout or "").strip()
        if out:
            box_line(out)
    return collect_ollama_status(refresh=True)


def ensure_ollama_ready(box_line, local_base_model, auto, download_and_verify_script, trusted_sources):
    current = collect_ollama_status(refresh=True)
    if not current["path"]:
        current = install_ollama_if_needed(box_line, download_and_verify_script, trusted_sources)
    if current["path"] and not current["api_ok"]:
        current = start_ollama_if_needed(box_line)
    if current["path"] and current["api_ok"] and not current["models"] and auto:
        box_line(f"• No había modelos en Ollama; bajo {local_base_model} como base")
        pull = pull_ollama_model(local_base_model)
        if pull.returncode == 0:
            box_line(f"  \033[38;5;84mListo:\033[0m {local_base_model} quedó descargado en Ollama.")
        else:
            out = (pull.stdout or "").strip()
            box_line(f"  \033[38;5;221mNo pude descargar {local_base_model}.\033[0m")
            if out:
                box_line(out)
    return collect_ollama_status(refresh=True)
