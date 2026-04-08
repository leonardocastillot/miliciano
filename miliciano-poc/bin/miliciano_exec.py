#!/usr/bin/env python3
import sys
from textwrap import dedent

from miliciano_runtime import *
from miliciano_obsidian import *
from miliciano_ui import *


def stream_local_ollama_response(model, local_prompt, route):
    width = terminal_width()
    print(rule(f" Miliciano · {route['role']} ", "─", width))
    sys.stdout.write("  ")
    sys.stdout.flush()

    payload = json.dumps({"model": model, "prompt": local_prompt, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    chunks = []
    line_open = True
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw_line in resp:
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                piece = event.get("response") or ""
                if piece:
                    chunks.append(piece)
                    for ch in piece:
                        sys.stdout.write(ch)
                        if ch == "\n":
                            sys.stdout.write("  ")
                            line_open = True
                        else:
                            line_open = False
                        sys.stdout.flush()
                if event.get("done"):
                    break
    except urllib.error.URLError as exc:
        if not line_open:
            sys.stdout.write("\n")
        print(rule(accent="─", width=width))
        return 1, f"No pude streamear desde Ollama: {exc.reason}"
    except Exception as exc:
        if not line_open:
            sys.stdout.write("\n")
        print(rule(accent="─", width=width))
        return 1, f"Falló el streaming local de Ollama: {exc}"

    if not line_open:
        sys.stdout.write("\n")
    print(rule(accent="─", width=width))
    return 0, strip_terminal_noise("".join(chunks))


def call_local_ollama_query(prompt, route, session_id=None):
    need("ollama")
    model = route["model"]
    local_prompt = (
        f"{MILICIANO_PREAMBLE}\n\n"
        f"Ruta seleccionada: {route['role']} ({route['spec']}). Motivo: {route['reason']}\n"
        f"Responde de forma breve y útil.\n\n"
        f"Usuario: {prompt}"
    )
    rc, clean = stream_local_ollama_response(model, local_prompt, route)
    if rc == 0:
        return rc, "", session_id
    res = run_with_spinner(["ollama", "run", model, local_prompt], f"Pensando como Miliciano · {route['role']}")
    return res.returncode, strip_terminal_noise(res.stdout or clean), session_id


def _nvidia_api_key():
    for env_name in NVIDIA_API_ENV_VARS:
        value = os.environ.get(env_name)
        if value:
            return value.strip()
    return None


def call_nvidia_query(prompt, route, session_id=None):
    status = collect_nvidia_status()
    api_key = _nvidia_api_key()
    if not api_key:
        return 1, "Falta NVIDIA_API_KEY/NVAPI_API_KEY/NVAPI para usar el fallback NVIDIA", session_id

    model = route.get("model") or status["model"] or NVIDIA_DEFAULT_MODEL
    route_hint = f"Ruta seleccionada: {route['role']} ({route['spec']}). Motivo: {route['reason']}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": MILICIANO_PREAMBLE},
            {"role": "user", "content": f"{route_hint}\n\nUsuario: {prompt}"},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{status['base_url'].rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        return 1, strip_terminal_noise(body or str(exc)), session_id
    except urllib.error.URLError as exc:
        return 1, f"No pude conectar con NVIDIA: {getattr(exc, 'reason', exc)}", session_id
    except Exception as exc:
        return 1, f"Falló el fallback NVIDIA: {exc}", session_id

    try:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
    except Exception:
        content = ""
    if not content:
        content = json.dumps(data, ensure_ascii=False)
    return 0, strip_terminal_noise(content), session_id


def _fallback_route_from_state(state):
    spec = (state.get("routing", {}) or {}).get("fallback")
    if not spec:
        return None
    provider, model = parse_hermes_route_spec(spec)
    return {
        "role": "fallback",
        "provider": provider,
        "model": model,
        "spec": spec,
        "reason": "ruta de fallback de Miliciano",
    }


def call_hermes_query(prompt, session_id=None, forced_role=None):
    state = load_miliciano_state()
    route = resolve_hermes_route_for_prompt(prompt, forced_role=forced_role)
    provider = route["provider"]
    model = route["model"]
    if provider == "custom":
        rc, clean, sid = call_local_ollama_query(prompt, route, session_id=session_id)
        save_obsidian_memory(prompt, clean, route=route, source="consulta", session_id=sid)
        return rc, clean, sid
    if provider == "nvidia":
        rc, clean, sid = call_nvidia_query(prompt, route, session_id=session_id)
        save_obsidian_memory(prompt, clean, route=route, source="consulta", session_id=sid)
        return rc, clean, sid

    need("hermes")
    route_hint = f"Ruta seleccionada: {route['role']} ({route['spec']}). Motivo: {route['reason']}"
    cmd = [
        "hermes", "chat", "-Q",
        "--provider", provider,
        "-m", model,
        "-q", f"{MILICIANO_PREAMBLE}\n\n{route_hint}\n\nUsuario: {prompt}",
        "--source", "tool",
    ]
    if session_id:
        cmd.extend(["--resume", session_id])
    spinner_label = f"Pensando como Miliciano · {route['role']}"
    res = run_with_spinner(cmd, spinner_label)
    out = (res.stdout or "")
    new_session_id = session_id
    clean_lines = []
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("session_id:"):
            new_session_id = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("↻ Resumed session"):
            continue
        if stripped.startswith("╭─ ⚕ Hermes") or stripped.startswith("╰") or stripped.startswith("│"):
            continue
        clean_lines.append(line)
    clean = "\n".join(clean_lines).strip()
    if clean:
        parts = [p.strip() for p in clean.split("\n\n") if p.strip()]
        compact = []
        seen = set()
        for part in parts:
            key = " ".join(part.split())
            if key in seen:
                continue
            if compact and compact[-1] == part:
                continue
            compact.append(part)
            seen.add(key)
        clean = "\n\n".join(compact).strip()
        lines = [ln.rstrip() for ln in clean.splitlines()]
        deduped_lines = []
        seen_line_runs = set()
        for ln in lines:
            key = " ".join(ln.split())
            if key and key in seen_line_runs and ln.startswith(("Hola.", "Objetivo:", "Siguiente paso:", "Cómo ")):
                continue
            deduped_lines.append(ln)
            if key:
                seen_line_runs.add(key)
        clean = "\n".join(deduped_lines).strip()

    fallback_route = _fallback_route_from_state(state)
    if (res.returncode != 0 or detect_quota_signal(out)) and fallback_route:
        fallback_provider = fallback_route["provider"]
        if fallback_provider == "custom":
            rc, clean, sid = call_local_ollama_query(prompt, fallback_route, session_id=session_id)
            save_obsidian_memory(prompt, clean, route=fallback_route, source="consulta", session_id=sid)
            return rc, clean, sid
        if fallback_provider == "nvidia":
            rc, clean, sid = call_nvidia_query(prompt, fallback_route, session_id=session_id)
            save_obsidian_memory(prompt, clean, route=fallback_route, source="consulta", session_id=sid)
            return rc, clean, sid

    save_obsidian_memory(prompt, clean, route=route, source="consulta", session_id=new_session_id)
    return res.returncode, clean, new_session_id


def interactive_chat():
    session_frame()
    session_id = None
    print("Escribe tu mensaje o /exit para salir.")
    print("Comandos: /fast, /reasoning, /clear, /exit")
    while True:
        try:
            prompt = input("miliciano> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            break
        if prompt == "/clear":
            session_id = None
            print("Sesión limpia.")
            continue
        forced_role = None
        raw_prompt = prompt
        if raw_prompt.startswith("/fast "):
            forced_role = "fast"
            raw_prompt = raw_prompt[6:].strip()
        elif raw_prompt.startswith("/reasoning "):
            forced_role = "reasoning"
            raw_prompt = raw_prompt[11:].strip()
        rc, clean, session_id = call_hermes_query(raw_prompt, session_id=session_id, forced_role=forced_role)
        if clean:
            response_box(clean)
        if rc != 0:
            print(f"[salida {rc}] revisión de la última respuesta")


def cmd_shell():
    banner()
    interactive_chat()


def cmd_think(prompt):
    forced_role = None
    raw_prompt = prompt.strip()
    if raw_prompt.startswith("--fast "):
        forced_role = "fast"
        raw_prompt = raw_prompt[7:].strip()
    elif raw_prompt.startswith("--reasoning "):
        forced_role = "reasoning"
        raw_prompt = raw_prompt[12:].strip()
    rc, clean, _ = call_hermes_query(raw_prompt, forced_role=forced_role)
    if clean:
        response_box(clean)
    sys.exit(rc)

def cmd_exec(prompt):
    need("openclaw")
    preamble = (
        "Eres el ejecutor operativo de Miliciano by Milytics. "
        "Toma la instrucción y ejecútala o responde como operador de ejecución."
    )
    rc, out = run_openclaw_agent(f"{preamble}\n\nTarea: {prompt}")
    save_obsidian_memory(prompt, out, source="exec")
    sys.exit(rc)

def cmd_mission(prompt):
    need("hermes")
    need("openclaw")
    route = resolve_hermes_route_for_prompt(prompt, forced_role="reasoning")
    provider = route["provider"]
    model = route["model"]
    planner = dedent(f"""
    Actúa como el cerebro de Miliciano by Milytics.
    Objetivo del usuario: {prompt}

    Devuelve solamente:
    1. OBJETIVO
    2. PLAN
    3. INSTRUCCIONES PARA OPENCLAW

    Sé concreto, breve y orientado a ejecución.
    """).strip()

    res = run_with_spinner([
        "hermes", "chat",
        "--provider", provider,
        "-m", model,
        "-q", planner,
    ], "Preparando misión")
    if res.returncode != 0:
        print(res.stdout, file=sys.stderr)
        save_obsidian_memory(prompt, res.stdout, route=route, source="mission")
        sys.exit(res.returncode)

    plan = res.stdout.strip()
    print("== Plan de Hermes ==")
    print(plan)
    print("\n== Pasando a OpenClaw ==")

    executor_prompt = dedent(f"""
    Eres OpenClaw dentro de Miliciano by Milytics.
    Recibes un plan generado por Hermes. Continúa la ejecución a partir de esto.

    {plan}
    """).strip()
    rc, out = run_openclaw_agent(executor_prompt)
    save_obsidian_memory(prompt, f"== Plan de Hermes ==\n{plan}\n\n== OpenClaw ==\n{out}", route=route, source="mission")
    sys.exit(rc)

