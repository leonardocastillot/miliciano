#!/usr/bin/env python3
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from miliciano_constants import MILICIANO_HERMES_HOME
from miliciano_ui import BOLD, DIM, RESET, SOFT, VIOLET, YELLOW


def agent_timeout():
    try:
        return int(os.environ.get("MILICIANO_AGENT_TIMEOUT", "300"))
    except ValueError:
        return 300


def has_rtk():
    from shutil import which
    return which("rtk") is not None


def maybe_rtk_prefix(cmd):
    if not has_rtk():
        return cmd
    compatible = {"git", "gh", "ls", "tree", "diff", "npm", "pnpm", "docker", "kubectl", "curl"}
    if isinstance(cmd, list) and cmd and cmd[0] in compatible:
        return ["rtk"] + cmd
    return cmd


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

    thread = threading.Thread(target=spinner, daemon=True)
    thread.start()
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
        thread.join(timeout=1)
    return subprocess.CompletedProcess(cmd, proc.returncode, out or "", None)


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


def strip_terminal_noise(text):
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
        "usage limit",
        "429",
        "insufficient",
        "billing",
        "credit",
        "capacity",
        "exhaust",
    ]
    return any(marker in normalized for marker in markers)
