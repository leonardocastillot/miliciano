#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.request
from textwrap import dedent

from miliciano_constants import MILICIANO_PREAMBLE, NVIDIA_DEFAULT_MODEL
from miliciano_obsidian import save_obsidian_memory
from miliciano_runtime import (
    agent_timeout,
    collect_nvidia_status,
    detect_quota_signal,
    get_nvidia_api_key,
    load_miliciano_state,
    need,
    parse_hermes_route_spec,
    resolve_nvidia_model,
    resolve_hermes_route_for_prompt,
    run_openclaw_agent,
    run_with_spinner,
    strip_terminal_noise,
)
from miliciano_shell_input import (
    HELP_TEXT,
    load_shell_mode,
    parse_shell_command,
    prompt_toolkit_available,
    read_shell_line,
    save_shell_mode,
    shell_runtime_status,
)
from miliciano_setup_support import (
    ensure_runtime_python_dependencies,
)
from miliciano_ui import activity_line, response_box, response_meta_line, rule, session_frame, terminal_width
from miliciano_validators import sanitize_prompt


def make_agent_result(status, content="", route=None, session_id=None, provider=None, model=None, latency_ms=None, policy_result=None, memory_path=None, transport_mode=None, payload_chars=None, payload_words=None):
    return {
        "status": status,
        "content": content or "",
        "route_used": route.get("role") if isinstance(route, dict) else None,
        "provider": provider or (route.get("provider") if isinstance(route, dict) else None),
        "model": model or (route.get("model") if isinstance(route, dict) else None),
        "session_id": session_id,
        "latency_ms": latency_ms,
        "policy_result": policy_result,
        "memory_path": memory_path,
        "transport_mode": transport_mode,
        "payload_chars": payload_chars,
        "payload_words": payload_words,
    }


def _format_nvidia_http_error(exc, model):
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = str(exc)
    detail = strip_terminal_noise(body or str(exc))
    if exc.code == 404:
        return (
            f"NVIDIA devolvió 404 para {model}. "
            f"La key existe, pero tu cuenta no tiene acceso a esa función/modelo o la credencial no corresponde al catálogo correcto. "
            f"Detalle: {detail}"
        )
    if exc.code in {401, 403}:
        return f"NVIDIA rechazó la credencial para {model}. Detalle: {detail}"
    return f"Error NVIDIA HTTP {exc.code} para {model}: {detail}"


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
        with urllib.request.urlopen(req, timeout=agent_timeout()) as resp:
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
        return rc, clean, session_id
    res = run_with_spinner(["ollama", "run", model, local_prompt], f"Pensando como Miliciano · {route['role']}")
    return res.returncode, strip_terminal_noise(res.stdout or clean), session_id


def stream_nvidia_response(model, api_key, base_url):
    payload = {
        "model": model,
        "messages": [],
        "temperature": 0.2,
        "stream": True,
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    chunks = []
    try:
        with urllib.request.urlopen(req, timeout=agent_timeout()) as resp:
            for raw_line in resp:
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        chunk_data = json.loads(line[6:])
                        delta = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            sys.stdout.write(delta)
                            sys.stdout.flush()
                            chunks.append(delta)
                    except Exception:
                        continue
    except Exception as exc:
        return 1, f"Error streaming NVIDIA: {exc}"

    print()
    return 0, strip_terminal_noise("".join(chunks))


def call_nvidia_query(prompt, route, session_id=None):
    status = collect_nvidia_status()
    api_key, _ = get_nvidia_api_key()
    if not api_key:
        return 1, "Falta NVIDIA_API_KEY/NVAPI_API_KEY/NVAPI para usar el fallback NVIDIA", session_id

    model = resolve_nvidia_model(route.get("model") or status["model"] or NVIDIA_DEFAULT_MODEL)
    route_hint = f"Ruta seleccionada: {route['role']} ({route['spec']}). Motivo: {route['reason']}"
    messages = [
        {"role": "system", "content": MILICIANO_PREAMBLE},
        {"role": "user", "content": f"{route_hint}\n\nUsuario: {prompt}"},
    ]

    if sys.stdout.isatty():
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }
        req = urllib.request.Request(
            f"{status['base_url'].rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        chunks = []
        try:
            with urllib.request.urlopen(req, timeout=agent_timeout()) as resp:
                for raw_line in resp:
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            chunk_data = json.loads(line[6:])
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                sys.stdout.write(delta)
                                sys.stdout.flush()
                                chunks.append(delta)
                        except Exception:
                            continue
        except urllib.error.HTTPError as exc:
            return 1, _format_nvidia_http_error(exc, model), session_id
        except Exception as exc:
            return 1, f"Error streaming NVIDIA: {exc}", session_id
        print()
        return 0, strip_terminal_noise("".join(chunks)), session_id

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{status['base_url'].rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=agent_timeout()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        return 1, _format_nvidia_http_error(exc, model), session_id
    except urllib.error.URLError as exc:
        return 1, f"No pude conectar con NVIDIA: {getattr(exc, 'reason', exc)}", session_id
    except Exception as exc:
        return 1, f"Falló el fallback NVIDIA: {exc}", session_id

    try:
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
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


def _save_memory(prompt, content, route=None, source="consulta", session_id=None, extra=None):
    return save_obsidian_memory(prompt, content, route=route, source=source, session_id=session_id, extra=extra)


def _announce_action(message, detail=None):
    activity_line(message, detail)


def _normalize_user_prompt(prompt):
    return sanitize_prompt(prompt)


def build_reasoning_payload(prompt, route):
    normalized_prompt = _normalize_user_prompt(prompt)
    route_hint = f"Ruta seleccionada: {route['role']} ({route['spec']}). Motivo: {route['reason']}"
    payload = f"{MILICIANO_PREAMBLE}\n\n{route_hint}\n\nUsuario: {normalized_prompt}"
    return {
        "prompt": normalized_prompt,
        "route_hint": route_hint,
        "payload": payload,
        "payload_chars": len(payload),
        "payload_words": len(payload.split()),
    }


def run_reasoning(prompt, session_id=None, forced_role=None, source="consulta", save_memory=True):
    state = load_miliciano_state()
    route = resolve_hermes_route_for_prompt(prompt, forced_role=forced_role)
    payload_info = build_reasoning_payload(prompt, route)
    provider = route["provider"]
    _announce_action("ruta seleccionada", f"{route['role']} -> {provider}/{route['model']}")
    _announce_action("motivo", route["reason"])
    _announce_action("payload", f"{payload_info['payload_chars']} chars · {payload_info['payload_words']} palabras")
    transport_mode = "resumed" if session_id else "stateless"

    if provider == "custom":
        _announce_action("ejecutando razonamiento local", route["model"])
        rc, clean, sid = call_local_ollama_query(payload_info["prompt"], route, session_id=session_id)
        if rc == 0 and save_memory:
            _announce_action("guardando memoria", source)
        memory_path = _save_memory(payload_info["prompt"], clean, route=route, source=source, session_id=sid) if save_memory else None
        return rc, make_agent_result("ok" if rc == 0 else "error", clean, route=route, session_id=sid, memory_path=memory_path, transport_mode=transport_mode, payload_chars=payload_info["payload_chars"], payload_words=payload_info["payload_words"])

    if provider == "nvidia":
        _announce_action("consultando NVIDIA", route["model"])
        rc, clean, sid = call_nvidia_query(payload_info["prompt"], route, session_id=session_id)
        if rc == 0 and save_memory:
            _announce_action("guardando memoria", source)
        memory_path = _save_memory(payload_info["prompt"], clean, route=route, source=source, session_id=sid) if save_memory else None
        return rc, make_agent_result("ok" if rc == 0 else "error", clean, route=route, session_id=sid, memory_path=memory_path, transport_mode=transport_mode, payload_chars=payload_info["payload_chars"], payload_words=payload_info["payload_words"])

    need("hermes")
    _announce_action("consultando Hermes", f"{provider}/{route['model']}")
    cmd = [
        "hermes", "chat", "-Q",
        "--provider", provider,
        "-m", route["model"],
        "-q", payload_info["payload"],
        "--source", "tool",
    ]
    if session_id:
        cmd.extend(["--resume", session_id])
    res = run_with_spinner(cmd, f"Pensando como Miliciano · {route['role']}")
    out = res.stdout or ""
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

    fallback_route = _fallback_route_from_state(state)
    if (res.returncode != 0 or detect_quota_signal(out)) and fallback_route:
        _announce_action("activando fallback", f"{fallback_route['provider']}/{fallback_route['model']}")
        if fallback_route["provider"] == "custom":
            rc, clean, sid = call_local_ollama_query(payload_info["prompt"], fallback_route, session_id=session_id)
            if rc == 0 and save_memory:
                _announce_action("guardando memoria", f"{source} · fallback")
            memory_path = _save_memory(payload_info["prompt"], clean, route=fallback_route, source=source, session_id=sid, extra="Fallback activado") if save_memory else None
            return rc, make_agent_result("ok" if rc == 0 else "error", clean, route=fallback_route, session_id=sid, memory_path=memory_path, transport_mode=transport_mode, payload_chars=payload_info["payload_chars"], payload_words=payload_info["payload_words"])
        if fallback_route["provider"] == "nvidia":
            rc, clean, sid = call_nvidia_query(payload_info["prompt"], fallback_route, session_id=session_id)
            if rc == 0 and save_memory:
                _announce_action("guardando memoria", f"{source} · fallback")
            memory_path = _save_memory(payload_info["prompt"], clean, route=fallback_route, source=source, session_id=sid, extra="Fallback activado") if save_memory else None
            return rc, make_agent_result("ok" if rc == 0 else "error", clean, route=fallback_route, session_id=sid, memory_path=memory_path, transport_mode=transport_mode, payload_chars=payload_info["payload_chars"], payload_words=payload_info["payload_words"])
        fallback_cmd = [
            "hermes", "chat", "-Q",
            "--provider", fallback_route["provider"],
            "-m", fallback_route["model"],
            "-q", f"{MILICIANO_PREAMBLE}\n\nRuta seleccionada: {fallback_route['role']} ({fallback_route['spec']}). Motivo: {fallback_route['reason']}\n\nUsuario: {payload_info['prompt']}",
            "--source", "tool",
        ]
        fallback_res = run_with_spinner(fallback_cmd, "Activando fallback de Miliciano")
        fallback_clean = strip_terminal_noise(fallback_res.stdout or "")
        if fallback_res.returncode == 0 and save_memory:
            _announce_action("guardando memoria", f"{source} · fallback")
        memory_path = _save_memory(payload_info["prompt"], fallback_clean, route=fallback_route, source=source, session_id=session_id, extra="Fallback activado") if save_memory else None
        return fallback_res.returncode, make_agent_result("ok" if fallback_res.returncode == 0 else "error", fallback_clean, route=fallback_route, session_id=session_id, memory_path=memory_path, transport_mode=transport_mode, payload_chars=payload_info["payload_chars"], payload_words=payload_info["payload_words"])

    if save_memory:
        _announce_action("guardando memoria", source)
    memory_path = _save_memory(payload_info["prompt"], clean, route=route, source=source, session_id=new_session_id) if save_memory else None
    return res.returncode, make_agent_result("ok" if res.returncode == 0 else "error", clean, route=route, session_id=new_session_id, memory_path=memory_path, transport_mode=transport_mode, payload_chars=payload_info["payload_chars"], payload_words=payload_info["payload_words"])


def run_execution(prompt, source="exec", check_policy=True, extra_context=None):
    need("openclaw")
    prompt = _normalize_user_prompt(prompt)
    _announce_action("preparando ejecución", "OpenClaw")
    preamble = (
        "Eres el ejecutor operativo de Miliciano by Milytics. "
        "Toma la instrucción y ejecútala o responde como operador de ejecución."
    )
    if extra_context:
        preamble += f"\n\nContexto:\n{extra_context}"
        _announce_action("inyectando contexto", "plan previo")
    if check_policy:
        _announce_action("validando política", "Nemoclaw/SimplePolicy")
    rc, out = run_openclaw_agent(f"{preamble}\n\nTarea: {prompt}", check_policy=check_policy)
    _announce_action("guardando memoria", source)
    memory_path = _save_memory(prompt, out, source=source, extra=extra_context)
    return rc, make_agent_result("ok" if rc == 0 else "error", out, provider="openclaw", model="main", memory_path=memory_path, policy_result={"checked": check_policy}, transport_mode="execution", payload_chars=len(prompt), payload_words=len(prompt.split()))


def run_unrestricted(prompt, session_id=None, forced_role="reasoning", source="unrestricted", save_memory=True):
    prompt = _normalize_user_prompt(prompt)
    state = load_miliciano_state()
    route = resolve_hermes_route_for_prompt(prompt, forced_role=forced_role)
    provider = route["provider"]
    _announce_action("modo libre", f"{route['role']} -> {provider}/{route['model']}")

    if provider == "custom":
        need("ollama")
        _announce_action("ejecutando local", route["model"])
        res = run_with_spinner(["ollama", "run", route["model"], prompt], f"Modo libre · {route['role']}")
        clean = strip_terminal_noise(res.stdout or "")
        if save_memory:
            _announce_action("guardando memoria", source)
        memory_path = _save_memory(prompt, clean, route=route, source=source, session_id=session_id) if save_memory else None
        return res.returncode, make_agent_result("ok" if res.returncode == 0 else "error", clean, route=route, session_id=session_id, memory_path=memory_path)

    if provider == "nvidia":
        status = collect_nvidia_status()
        api_key, _ = get_nvidia_api_key()
        if not api_key:
            return 1, make_agent_result("error", "Falta NVIDIA_API_KEY/NVAPI_API_KEY/NVAPI para usar modo libre", route=route, session_id=session_id)
        _announce_action("consultando NVIDIA", payload_model := resolve_nvidia_model(route.get("model") or status["model"] or NVIDIA_DEFAULT_MODEL))
        payload = {
            "model": payload_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "stream": False,
        }
        req = urllib.request.Request(
            f"{status['base_url'].rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=agent_timeout()) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        except urllib.error.HTTPError as exc:
            content = _format_nvidia_http_error(exc, payload["model"])
            memory_path = _save_memory(prompt, content, route=route, source=source, session_id=session_id) if save_memory else None
            return 1, make_agent_result("error", content, route=route, session_id=session_id, memory_path=memory_path)
        except Exception as exc:
            content = f"Error modo libre NVIDIA: {exc}"
            memory_path = _save_memory(prompt, content, route=route, source=source, session_id=session_id) if save_memory else None
            return 1, make_agent_result("error", content, route=route, session_id=session_id, memory_path=memory_path)
        clean = strip_terminal_noise(content or json.dumps(data, ensure_ascii=False))
        if save_memory:
            _announce_action("guardando memoria", source)
        memory_path = _save_memory(prompt, clean, route=route, source=source, session_id=session_id) if save_memory else None
        return 0, make_agent_result("ok", clean, route=route, session_id=session_id, memory_path=memory_path)

    need("hermes")
    _announce_action("consultando Hermes", f"{provider}/{route['model']}")
    cmd = [
        "hermes", "chat", "-Q",
        "--provider", provider,
        "-m", route["model"],
        "-q", prompt,
        "--source", "tool",
    ]
    if session_id:
        cmd.extend(["--resume", session_id])
    res = run_with_spinner(cmd, f"Modo libre · {route['role']}")
    out = res.stdout or ""
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

    fallback_route = _fallback_route_from_state(state)
    if (res.returncode != 0 or detect_quota_signal(out)) and fallback_route and fallback_route["provider"] == "custom":
        need("ollama")
        _announce_action("activando fallback", f"{fallback_route['provider']}/{fallback_route['model']}")
        fallback_res = run_with_spinner(["ollama", "run", fallback_route["model"], prompt], f"Modo libre fallback · {fallback_route['role']}")
        fallback_clean = strip_terminal_noise(fallback_res.stdout or "")
        if save_memory:
            _announce_action("guardando memoria", f"{source} · fallback")
        memory_path = _save_memory(prompt, fallback_clean, route=fallback_route, source=source, session_id=session_id, extra="Fallback activado") if save_memory else None
        return fallback_res.returncode, make_agent_result("ok" if fallback_res.returncode == 0 else "error", fallback_clean, route=fallback_route, session_id=session_id, memory_path=memory_path)

    if save_memory:
        _announce_action("guardando memoria", source)
    memory_path = _save_memory(prompt, clean, route=route, source=source, session_id=new_session_id) if save_memory else None
    return res.returncode, make_agent_result("ok" if res.returncode == 0 else "error", clean, route=route, session_id=new_session_id, memory_path=memory_path)


def build_mission_plan_prompt(prompt):
    return dedent(f"""
    Actúa como el cerebro de Miliciano by Milytics.
    Objetivo del usuario: {prompt}

    Devuelve solamente:
    1. OBJETIVO
    2. PLAN
    3. INSTRUCCIONES PARA OPENCLAW
    4. RIESGOS

    Sé concreto, breve y orientado a ejecución.
    """).strip()


def run_mission(prompt):
    _announce_action("fase 1", "planificación")
    rc_plan, plan_result = run_reasoning(build_mission_plan_prompt(prompt), forced_role="reasoning", source="mission_plan", save_memory=False)
    if rc_plan != 0:
        memory_path = _save_memory(prompt, plan_result["content"], route={"role": "reasoning"}, source="mission", extra="Fallo en etapa de planificación")
        plan_result["memory_path"] = memory_path
        return rc_plan, {"planner": plan_result, "executor": None, "summary": plan_result["content"]}

    plan = plan_result["content"].strip()
    executor_prompt = dedent(f"""
    Eres OpenClaw dentro de Miliciano by Milytics.
    Recibes un plan generado por Hermes. Continúa la ejecución a partir de esto.

    {plan}
    """).strip()
    _announce_action("fase 2", "ejecución")
    rc_exec, exec_result = run_execution(prompt, source="mission", check_policy=True, extra_context=plan)
    _announce_action("fase 3", "resumen + memoria")
    summary = f"== Plan de Hermes ==\n{plan}\n\n== OpenClaw ==\n{exec_result['content']}"
    memory_path = _save_memory(prompt, summary, route={"role": "mission"}, source="mission")
    exec_result["memory_path"] = exec_result.get("memory_path") or memory_path
    return rc_exec, {"planner": plan_result, "executor": exec_result, "summary": summary}


def _ask_yes_no(question, default=True):
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        try:
            answer = input(question + suffix).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not answer:
            return default
        if answer in {"y", "yes", "s", "si", "sí"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Responde y/s o n.")


def _ensure_shell_runtime_ready():
    shell_ui = shell_runtime_status()
    if shell_ui["available"]:
        return True
    print(shell_ui["detail"], file=sys.stderr)
    if shell_ui["action"]:
        print(shell_ui["action"], file=sys.stderr)
    return False


def run_shell():
    if not _ensure_shell_runtime_ready():
        return
    shell_ui = shell_runtime_status()
    if not prompt_toolkit_available():
        print(shell_ui["detail"])
        if shell_ui["action"]:
            print(shell_ui["action"])
    runtime_python = ensure_runtime_python_dependencies(auto_install=False)
    if not runtime_python["ok"] and sys.stdin.isatty() and sys.stdout.isatty():
        missing = ", ".join(runtime_python["missing_modules"]) or "extras opcionales"
        question = (
            f"Faltan extras opcionales de seguridad ({missing}). "
            "¿Quieres que Miliciano intente repararlos ahora?"
        )
        if _ask_yes_no(question, default=False):
            runtime_python = ensure_runtime_python_dependencies(auto_install=True)
            print(runtime_python["detail"])
    session_frame(title="SESIÓN MILICIANO ACTIVA", subtitle="Shift+Tab/Ctrl+T/Alt+M cambia modo · /exit sale")
    session_id = None
    shell_mode = load_shell_mode()
    print("Escribe tu mensaje o /exit para salir.")
    print(HELP_TEXT)
    while True:
        try:
            prompt, shell_mode = read_shell_line(shell_mode)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            break
        except (EOFError, KeyboardInterrupt):
            print()
            break
        parsed = parse_shell_command(prompt, current_mode=shell_mode)
        kind = parsed["kind"]

        if kind == "empty":
            continue
        if kind == "exit":
            break
        if kind == "clear":
            session_id = None
            print("Sesión limpia.")
            continue
        if kind == "info":
            print(parsed["message"])
            continue
        if kind == "error":
            print(parsed["message"])
            continue
        if kind == "mode":
            shell_mode = save_shell_mode(parsed["mode"])
            print(parsed["message"])
            continue

        active_mode = parsed["mode"]
        raw_prompt = parsed.get("prompt", "").strip()
        if not raw_prompt:
            continue
        if active_mode in {"reasoning", "plan", "unrestricted"}:
            shell_mode = save_shell_mode(active_mode)

        if active_mode == "exec":
            rc, result = run_execution(raw_prompt)
            response_meta_line(result, mode=active_mode)
            if result["content"]:
                response_box(result["content"], title="OpenClaw")
            if rc != 0:
                print(f"[salida {rc}] revisión de la última respuesta")
            continue

        if active_mode == "mission":
            rc, result = run_mission(raw_prompt)
            if result["planner"] and result["planner"]["content"]:
                response_meta_line(result["planner"], mode="plan")
                response_box(result["planner"]["content"], title="Plan")
            if result["executor"] and result["executor"]["content"]:
                response_meta_line(result["executor"], mode="exec")
                response_box(result["executor"]["content"], title="Ejecución")
            if rc != 0:
                print(f"[salida {rc}] misión incompleta")
            continue

        if active_mode == "plan":
            rc, result = run_reasoning(build_mission_plan_prompt(raw_prompt), forced_role="reasoning", source="plan")
            session_id = None
            response_meta_line(result, mode=active_mode)
            if result["content"]:
                response_box(result["content"], title="Plan")
            if rc != 0:
                print(f"[salida {rc}] revisión del plan")
            continue

        if active_mode == "unrestricted":
            rc, result = run_unrestricted(raw_prompt, session_id=session_id, forced_role="reasoning")
            session_id = result["session_id"]
            response_meta_line(result, mode=active_mode)
            if result["content"]:
                response_box(result["content"], title="Libre")
            if rc != 0:
                print(f"[salida {rc}] revisión de la última respuesta")
            continue

        forced_role = "fast" if active_mode == "fast" else "reasoning"
        rc, result = run_reasoning(raw_prompt, forced_role=forced_role)
        session_id = None
        response_meta_line(result, mode=active_mode)
        if result["content"]:
            response_box(result["content"], title="Miliciano" if active_mode == "reasoning" else active_mode.title())
        if rc != 0:
            print(f"[salida {rc}] revisión de la última respuesta")
