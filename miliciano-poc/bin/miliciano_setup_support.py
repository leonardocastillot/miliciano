#!/usr/bin/env python3
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from shutil import which

from miliciano_constants import (
    DEBIAN_PYTHON_SYSTEM_PACKAGES,
    MILICIANO_HERMES_HOME,
    OPTIONAL_SECURITY_PYTHON_DEPENDENCIES,
    PREREQ_COMMANDS,
    SHELL_PYTHON_DEPENDENCIES,
)
from miliciano_obsidian import sync_obsidian_cerebro
from miliciano_runtime import (
    basic_runtime_status,
    collect_local_ai_hardware,
    collect_ollama_status,
    load_miliciano_state,
    pull_ollama_model,
    recommend_ollama_models,
    run,
    run_with_spinner,
    save_miliciano_state,
    sync_hermes_global_config,
    sync_hermes_profile_config,
    sync_openclaw_fallback_route,
)
from miliciano_ui import activity_line
from miliciano_validators import ValidationError, validate_install_url


SOUL_TEMPLATE = """# Miliciano SOUL

Perfil mínimo del espacio personal de Miliciano.

- Producto: Miliciano
- Marca: Milytics
- Rol: CLI/chat táctico
- Objetivo: razonar, ejecutar y dejar trazabilidad
- Estado: este archivo se crea o repara durante setup/repair
"""

TRUSTED_SOURCES = {
    "ollama": {
        "url": "https://ollama.com/install.sh",
        "verify_checksum": False,
        "sha256": None,
    },
    "nemoclaw": {
        "url": "https://www.nvidia.com/nemoclaw.sh",
        "verify_checksum": False,
        "sha256": None,
    },
}


def download_and_verify_script(url, expected_sha256=None):
    validated_url = validate_install_url(url)
    try:
        with urllib.request.urlopen(validated_url, timeout=30) as response:
            content = response.read()
    except Exception as exc:
        raise Exception(f"Failed to download from {validated_url}: {exc}")

    if expected_sha256:
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_sha256:
            raise ValidationError(
                f"Checksum mismatch for {url}\nExpected: {expected_sha256}\nGot:      {actual_hash}"
            )

    tmp = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".sh")
    try:
        tmp.write(content)
        tmp.close()
        os.chmod(tmp.name, 0o700)
        return tmp.name
    except Exception as exc:
        try:
            os.remove(tmp.name)
        except Exception:
            pass
        raise Exception(f"Failed to write temp script: {exc}")


def ensure_miliciano_soul(profile_dir):
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    soul_path = profile_dir / "SOUL.md"
    if soul_path.exists():
        return False, f"SOUL.md presente en {soul_path}"
    soul_path.write_text(SOUL_TEMPLATE, encoding="utf-8")
    activity_line("SOUL.md creado", str(soul_path))
    return True, f"SOUL.md creado en {soul_path}"


def ensure_policy_config():
    config_dir = Path.home() / ".config" / "miliciano"
    config_dir.mkdir(parents=True, exist_ok=True)
    policy_path = config_dir / "policy.yaml"
    if policy_path.exists():
        return False, f"Política existente en {policy_path}"

    template_path = Path(__file__).parent.parent / "config" / "policy.yaml"
    if template_path.exists():
        import shutil
        shutil.copy(template_path, policy_path)
        activity_line("Política de seguridad creada", str(policy_path))
        return True, f"Política creada desde plantilla: {policy_path}"

    minimal_policy = """# Miliciano Security Policy
version: "1.0"
mode: enforce

blocked_commands:
  - pattern: "\\\\brm\\\\s+-rf\\\\b"
    description: "Recursive file deletion"
    risk: critical

audit:
  enabled: true
  log_path: "~/.config/miliciano/audit.log"
"""
    policy_path.write_text(minimal_policy, encoding="utf-8")
    activity_line("Política mínima creada", str(policy_path))
    return True, f"Política mínima creada: {policy_path}"


def start_openclaw_gateway_detached():
    try:
        return subprocess.Popen(
            ["openclaw", "gateway", "--force"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as exc:
        return exc


def wait_for_openclaw_gateway_ready(timeout_seconds=30, poll_interval=1):
    deadline = time.time() + timeout_seconds
    last_output = ""
    while time.time() < deadline:
        health = run(["openclaw", "health", "--json"], capture=True, timeout=6)
        normalized = (health.stdout or "").lower().replace(" ", "")
        last_output = (health.stdout or "").strip()
        if health.returncode == 0 and '"ok":true' in normalized:
            return True, "Gateway levantado durante este setup"
        time.sleep(poll_interval)
    return False, last_output or "Gateway no respondió tras el arranque"


def repair_nemoclaw_wrapper():
    wrapper = Path.home() / ".local" / "bin" / "nemoclaw"
    npm_prefix_res = run(["npm", "prefix", "-g"], capture=True, timeout=10)
    npm_prefix = (npm_prefix_res.stdout or "").strip().splitlines()[-1].strip() if npm_prefix_res and npm_prefix_res.returncode == 0 else ""
    npm_global_bin = Path(npm_prefix) / "bin" if npm_prefix else None
    global_candidate = (npm_global_bin / "nemoclaw") if npm_global_bin else None

    if not global_candidate or not global_candidate.exists():
        if wrapper.exists():
            return False, f"No detecté binario global de Nemoclaw para reparar {wrapper}"
        return False, "No detecté una instalación global de Nemoclaw"

    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper_content = """#!/usr/bin/env bash
set -euo pipefail
if command -v npm >/dev/null 2>&1; then
  NPM_PREFIX="$(npm prefix -g 2>/dev/null | tail -n 1)"
  if [ -n "$NPM_PREFIX" ] && [ -x "$NPM_PREFIX/bin/nemoclaw" ]; then
    exec "$NPM_PREFIX/bin/nemoclaw" "$@"
  fi
fi
if command -v nemoclaw >/dev/null 2>&1; then
  exec "$(command -v nemoclaw)" "$@"
fi
printf '[Nemoclaw] existe instalación, pero no está expuesta correctamente en PATH.\\n' >&2
exit 1
"""
    wrapper.write_text(wrapper_content, encoding="utf-8")
    os.chmod(wrapper, 0o755)
    activity_line("Wrapper de Nemoclaw reparado", str(wrapper))
    return True, f"Wrapper recreado en {wrapper}"


def missing_python_dependencies(dependencies):
    missing = []
    for dependency in dependencies:
        if importlib.util.find_spec(dependency["module"]) is None:
            missing.append(dict(dependency))
    return missing


def missing_shell_python_dependencies():
    return missing_python_dependencies(SHELL_PYTHON_DEPENDENCIES)


def missing_optional_runtime_python_dependencies():
    return missing_python_dependencies(OPTIONAL_SECURITY_PYTHON_DEPENDENCIES)


def read_os_release():
    data = {}
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                data[key] = value.strip().strip('"')
    except FileNotFoundError:
        return {}
    return data


def python_system_prereq_status():
    os_release = read_os_release()
    distro_tokens = {
        (os_release.get("ID") or "").lower(),
        *(token.strip().lower() for token in (os_release.get("ID_LIKE") or "").split()),
    }
    debian_like = any(token in {"debian", "ubuntu"} for token in distro_tokens)

    pip_probe = run([sys.executable, "-m", "pip", "--version"], capture=True, timeout=15)
    pip_ok = pip_probe.returncode == 0
    venv_ok = importlib.util.find_spec("venv") is not None
    ensurepip_ok = importlib.util.find_spec("ensurepip") is not None

    missing = []
    if not pip_ok:
        missing.append("pip")
    if not venv_ok:
        missing.append("venv")
    if not ensurepip_ok:
        missing.append("ensurepip")

    detail = "Runtime Python listo para instalar dependencias locales"
    if missing:
        detail = (
            f"Python detectado en {sys.executable}, pero faltan componentes del runtime local: "
            + ", ".join(missing)
        )
        if debian_like:
            detail += (
                ". En Debian/Ubuntu normalmente se repara con: sudo apt-get install -y "
                + " ".join(DEBIAN_PYTHON_SYSTEM_PACKAGES)
            )

    return {
        "ok": not missing,
        "missing": missing,
        "pip_ok": pip_ok,
        "venv_ok": venv_ok,
        "ensurepip_ok": ensurepip_ok,
        "debian_like": debian_like,
        "os_release": os_release,
        "packages": list(DEBIAN_PYTHON_SYSTEM_PACKAGES if debian_like else ()),
        "detail": detail,
    }


def ensure_python_system_prereqs(auto_install=False, dry_run=False):
    status = python_system_prereq_status()
    if status["ok"]:
        return status
    if dry_run:
        status["detail"] = f"[dry-run] {status['detail']}"
        return status
    if not auto_install:
        return status
    if not status["debian_like"]:
        status["detail"] += ". Reparación automática solo implementada para Debian/Ubuntu."
        return status
    if which("sudo") is None:
        status["detail"] += ". Falta `sudo`; no pude ejecutar la reparación automática."
        return status

    update = run(["sudo", "apt-get", "update"], capture=True, timeout=300)
    install = run(
        ["sudo", "apt-get", "install", "-y", *status["packages"]],
        capture=True,
        timeout=600,
    ) if update.returncode == 0 else update
    refreshed = python_system_prereq_status()
    if refreshed["ok"]:
        refreshed["detail"] = (
            "Runtime Python del sistema reparado automáticamente con apt: "
            + " ".join(status["packages"])
        )
        return refreshed

    command = "sudo apt-get install -y " + " ".join(status["packages"])
    out = ((install.stdout or "").strip() or (install.stderr or "").strip())
    tail = out.splitlines()[-1] if out else command
    refreshed["detail"] = f"No pude reparar el runtime Python del sistema automáticamente: {tail}"
    return refreshed


def python_install_command(dependencies):
    packages = [dependency["package"] for dependency in dependencies]
    return [sys.executable, "-m", "pip", "install", "--user", *packages]


def ensure_shell_python_dependencies(auto_install=True):
    missing = missing_shell_python_dependencies()
    if not missing:
        return {
            "ok": True,
            "missing_modules": [],
            "installed_packages": [],
            "detail": "Dependencias base del shell listas (prompt_toolkit, wcwidth detectados)",
        }

    if not auto_install:
        return {
            "ok": False,
            "missing_modules": [dependency["module"] for dependency in missing],
            "installed_packages": [],
            "detail": (
                "Faltan dependencias base del shell: "
                + ", ".join(dependency["module"] for dependency in missing)
            ),
        }

    install = run(
        python_install_command(missing),
        capture=True,
        timeout=180,
    )
    remaining = missing_shell_python_dependencies()
    if install.returncode == 0 and not remaining:
        packages = [dependency["package"] for dependency in missing]
        return {
            "ok": True,
            "missing_modules": [],
            "installed_packages": packages,
            "detail": f"Dependencias base del shell instaladas automáticamente con {sys.executable} -m pip",
        }

    detail = ((install.stdout or "").strip() or (install.stderr or "").strip())
    if detail:
        detail = detail.splitlines()[-1]
    else:
        detail = (
            "Prueba: "
            + " ".join(f'"{part}"' if " " in part else part for part in python_install_command(missing))
        )
    return {
        "ok": False,
        "missing_modules": [dependency["module"] for dependency in remaining or missing],
        "installed_packages": [],
        "detail": f"No pude instalar dependencias base del shell automáticamente: {detail}",
    }


def runtime_python_install_command(missing=None):
    dependencies = missing or missing_optional_runtime_python_dependencies()
    return python_install_command(dependencies)


def ensure_runtime_python_dependencies(auto_install=True):
    missing = missing_optional_runtime_python_dependencies()
    if not missing:
        return {
            "ok": True,
            "missing_modules": [],
            "installed_packages": [],
            "detail": "Extras opcionales de seguridad listos (cryptography, keyring detectados)",
        }

    if not auto_install:
        return {
            "ok": False,
            "missing_modules": [dependency["module"] for dependency in missing],
            "installed_packages": [],
            "detail": (
                "Faltan extras opcionales de seguridad: "
                + ", ".join(dependency["module"] for dependency in missing)
            ),
        }

    install = run(
        runtime_python_install_command(missing),
        capture=True,
        timeout=180,
    )
    remaining = missing_optional_runtime_python_dependencies()
    if install.returncode == 0 and not remaining:
        packages = [dependency["package"] for dependency in missing]
        return {
            "ok": True,
            "missing_modules": [],
            "installed_packages": packages,
            "detail": f"Extras opcionales de seguridad instalados automáticamente con {sys.executable} -m pip",
        }

    detail = ((install.stdout or "").strip() or (install.stderr or "").strip())
    if detail:
        detail = detail.splitlines()[-1]
    else:
        detail = (
            "Prueba: "
            + " ".join(f'"{part}"' if " " in part else part for part in runtime_python_install_command(missing))
        )
    return {
        "ok": False,
        "missing_modules": [dependency["module"] for dependency in remaining or missing],
        "installed_packages": [],
        "detail": f"No pude instalar extras opcionales de seguridad automáticamente: {detail}",
    }


def repair_core_stack(auto_install=True, dry_run=False):
    state = load_miliciano_state(refresh=True)
    actions = []

    hermes_provider = state["hermes"]["provider"]
    hermes_model = state["hermes"]["model"]
    if dry_run:
        actions.append(f"[dry-run] Hermes quedaría sincronizado en {hermes_provider}/{hermes_model}")
    else:
        sync_hermes_global_config(hermes_provider, hermes_model)
        sync_hermes_profile_config(hermes_provider, hermes_model)
        actions.append(f"Hermes sincronizado en {hermes_provider}/{hermes_model}")

    profile_dir = Path(MILICIANO_HERMES_HOME)
    if dry_run:
        actions.append(f"[dry-run] Verificaría SOUL.md en {profile_dir / 'SOUL.md'}")
    else:
        profile_dir.mkdir(parents=True, exist_ok=True)
        created, detail = ensure_miliciano_soul(profile_dir)
        actions.append(detail if created else f"SOUL.md presente en {profile_dir / 'SOUL.md'}")

    if which("openclaw"):
        current_model = state["openclaw"]["model"]
        if dry_run:
            actions.append(f"[dry-run] OpenClaw quedaría alineado a {current_model}")
        else:
            run(["openclaw", "models", "set", current_model], capture=True, timeout=12)
            ok, detail = sync_openclaw_fallback_route(state)
            actions.append(f"OpenClaw alineado a {current_model}")
            actions.append(detail)
    else:
        actions.append("OpenClaw no instalado; no pude re-alinear execution/fallback")

    if dry_run:
        actions.append("[dry-run] Revisaría y repararía el wrapper de Nemoclaw si hace falta")
    else:
        repaired, nemo_detail = repair_nemoclaw_wrapper()
        actions.append(nemo_detail)
        if repaired:
            activity_line("Repair completado", "Nemoclaw / configs / fallback")

    system_python = ensure_python_system_prereqs(auto_install=auto_install and not dry_run, dry_run=dry_run)
    actions.append(system_python["detail"])

    shell_python = ensure_shell_python_dependencies(auto_install=system_python["ok"] and auto_install and not dry_run)
    actions.append(shell_python["detail"])
    if shell_python["ok"] and not dry_run:
        activity_line("Shell interactivo listo", "prompt_toolkit / wcwidth")

    runtime_python = ensure_runtime_python_dependencies(auto_install=system_python["ok"] and auto_install and not dry_run)
    actions.append(runtime_python["detail"])
    if runtime_python["ok"] and not dry_run:
        activity_line("Extras opcionales listos", "cryptography / keyring")

    try:
        if dry_run:
            actions.append("[dry-run] Sincronizaría Obsidian con el vault real")
        else:
            sync_obsidian_cerebro()
            actions.append("Obsidian sincronizado con el vault real")
    except Exception:
        actions.append("Obsidian no se pudo sincronizar automáticamente")
    return actions


def detect_openclaw_auth_state():
    from miliciano_runtime import collect_openclaw_model_status
    status = collect_openclaw_model_status()
    auth_ok = bool(status.get("provider")) and not status.get("quota_exhausted")
    detail = f"Auth de modelo lista ({status.get('model') or 'modelo operativo'})" if auth_ok else "Falta auth de modelo en OpenClaw"
    return auth_ok, detail, status


def current_local_stack_snapshot():
    runtime = basic_runtime_status()
    local_hw = collect_local_ai_hardware()
    ollama_status = collect_ollama_status()
    ollama_recos = recommend_ollama_models(local_hw)
    python_system = python_system_prereq_status()
    return {
        "runtime": runtime,
        "runtime_ready": all(runtime[cmd]["path"] for cmd in PREREQ_COMMANDS),
        "python_system": python_system,
        "docker_ready": runtime["docker"]["path"] is not None,
        "local_hw": local_hw,
        "ollama_status": ollama_status,
        "ollama_recos": ollama_recos,
        "local_base_model": ollama_recos[0][0],
        "local_model_ready": bool(ollama_status["path"] and ollama_status["api_ok"] and ollama_status["models"]),
    }
