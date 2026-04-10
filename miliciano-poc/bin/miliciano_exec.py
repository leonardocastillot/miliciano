#!/usr/bin/env python3
import sys
from shutil import which
from textwrap import dedent

from miliciano_runtime import *
from miliciano_obsidian import *
from miliciano_ui import *


def stream_local_ollama_response(model, local_prompt, route, stream_output=False):
    width = terminal_width()
    stream_visible = stream_output or get_output_mode() == "debug"
    if stream_visible:
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
                    if stream_visible:
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
        if stream_visible and not line_open:
            sys.stdout.write("\n")
        if stream_visible:
            print(rule(accent="─", width=width))
        return 1, f"No pude streamear desde Ollama: {exc.reason}"
    except Exception as exc:
        if stream_visible and not line_open:
            sys.stdout.write("\n")
        if stream_visible:
            print(rule(accent="─", width=width))
        return 1, f"Falló el streaming local de Ollama: {exc}"

    if stream_visible and not line_open:
        sys.stdout.write("\n")
    if stream_visible:
        print(rule(accent="─", width=width))
    return 0, strip_terminal_noise("".join(chunks))


def call_local_ollama_query(prompt, route, session_id=None, stream_output=False):
    need("ollama")
    model = route["model"]
    local_prompt = (
        f"{get_miliciano_preamble()}\n\n"
        f"Ruta seleccionada: {route['role']} ({route['spec']}). Motivo: {route['reason']}\n"
        f"Responde de forma breve y útil.\n\n"
        f"Usuario: {prompt}"
    )
    rc, clean = stream_local_ollama_response(model, local_prompt, route, stream_output=stream_output)
    if rc == 0:
        return rc, strip_terminal_noise(clean), session_id
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
            {"role": "system", "content": get_miliciano_preamble()},
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


def call_hermes_query(prompt, session_id=None, forced_role=None, stream_output=False):
    state = load_miliciano_state()
    route = resolve_hermes_route_for_prompt(prompt, forced_role=forced_role)
    provider = route["provider"]
    model = route["model"]
    project = load_miliciano_project_instructions()
    project_block = ""
    if project.get("present") and project.get("content"):
        project_block = f"\n\nInstrucciones activas desde MILICIANO.md ({project['path']}):\n{project['content']}"
    if provider == "custom":
        rc, clean, sid = call_local_ollama_query(prompt, route, session_id=session_id, stream_output=stream_output)
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
        "-q", f"{get_miliciano_preamble()}\n\n{route_hint}{project_block}\n\nUsuario: {prompt}",
        "--source", "tool",
    ]
    if session_id:
        cmd.extend(["--resume", session_id])
    spinner_label = f"Pensando como Miliciano · {route['role']}"
    runner = run_with_live_output if stream_output else run_with_spinner
    res = runner(cmd, spinner_label)
    out = (res.stdout or "")
    new_session_id = session_id
    clean_lines = []
    suppressed_prefixes = (
        "⚠️  API call failed",
        "🔌 Provider:",
        "🌐 Endpoint:",
        "📝 Error:",
        "📋 Details:",
        "⏱️ Rate limit reached",
    )
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("session_id:"):
            new_session_id = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("↻ Resumed session"):
            continue
        if stripped.startswith("╭─ ⚕ Hermes") or stripped.startswith("╰") or stripped.startswith("│"):
            continue
        if any(stripped.startswith(prefix) for prefix in suppressed_prefixes):
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
    should_try_fallback = bool(fallback_route) and (res.returncode != 0 or not clean)
    if should_try_fallback:
        fallback_provider = fallback_route["provider"]
        if fallback_provider == "custom":
            rc, clean, sid = call_local_ollama_query(prompt, fallback_route, session_id=session_id, stream_output=stream_output)
            save_obsidian_memory(prompt, clean, route=fallback_route, source="consulta", session_id=sid)
            return rc, clean, sid
        if fallback_provider == "nvidia":
            rc, clean, sid = call_nvidia_query(prompt, fallback_route, session_id=session_id)
            save_obsidian_memory(prompt, clean, route=fallback_route, source="consulta", session_id=sid)
            return rc, clean, sid

    save_obsidian_memory(prompt, clean, route=route, source="consulta", session_id=new_session_id)
    return res.returncode, clean, new_session_id






def render_trace_report():
    report = load_last_orchestration_report()
    decision = report.get("decision") or {}
    policy = report.get("policy") or {}
    execution = report.get("execution") or {}
    retry = report.get("retry") or {}
    rows = [
        f"mode          {get_output_mode()}",
        f"route-mode    {get_route_mode()}",
        f"perm-mode     {get_permission_mode()}",
        f"intent        {decision.get('intent') or 'n/d'}",
        f"target        {decision.get('target') or 'n/d'}",
        f"reason        {decision.get('reason') or 'n/d'}",
        f"policy        {policy.get('verdict') or 'n/d'}",
        f"policy why    {policy.get('reason') or 'n/d'}",
        f"outcome       {execution.get('outcome') or 'n/d'}",
        f"verified      {'sí' if execution.get('verified') else 'no' if execution else 'n/d'}",
        f"retry used    {'sí' if retry.get('used') else 'no' if retry else 'n/d'}",
        f"retry why     {retry.get('reason') or 'n/d'}",
    ]
    panel("TRACE DE ORQUESTACIÓN", rows)


def cmd_trace(args=None):
    banner()
    render_trace_report()


def _dedupe_text_blocks(text):
    raw = (text or "").strip()
    if not raw:
        return raw
    blocks = [block.strip() for block in raw.split("\n\n") if block.strip()]
    compact = []
    seen = set()
    for block in blocks:
        key = " ".join(block.split())
        if key in seen:
            continue
        compact.append(block)
        seen.add(key)
    return "\n\n".join(compact).strip() or raw


def normalize_plan_text(plan_text):
    original = (plan_text or "").strip()
    if not original:
        return original
    deduped = _dedupe_text_blocks(original)
    lines = []
    seen_headers = set()
    seen_content = set()
    for line in deduped.splitlines():
        stripped = line.strip()
        upper = stripped.upper().rstrip(":")
        if upper in {"1. OBJETIVO", "2. PLAN", "3. CRITERIO_DE_VERIFICACION", "OBJETIVO", "PLAN", "CRITERIO_DE_VERIFICACION"}:
            if upper in seen_headers:
                continue
            seen_headers.add(upper)
            lines.append(line)
            continue
        key = " ".join(stripped.split())
        if key and key in seen_content:
            continue
        if key:
            seen_content.add(key)
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    return cleaned or original


def normalize_verification_summary(summary):
    original = (summary or "").strip()
    if not original:
        return original
    cleaned = _dedupe_text_blocks(original)
    return cleaned or original


def _debug_meta_lines(decision, verification):
    verification_outcome = (verification or {}).get("outcome") or "n/d"
    return [
        f"mode: {get_output_mode()}",
        f"route-mode: {get_route_mode()}",
        f"permission-mode: {get_permission_mode()}",
        f"intent: {decision.get('intent') or 'n/d'}",
        f"target: {decision.get('target') or 'n/d'}",
        f"reason: {decision.get('reason') or 'n/d'}",
        f"verification: {verification_outcome}",
    ]


def format_partner_response(decision, plan_text, exec_out, verification, force_mode=None):
    mode = get_output_mode()
    plan_text = normalize_plan_text(plan_text)
    exec_out = (exec_out or "").strip()
    verification_summary = normalize_verification_summary((verification or {}).get("summary"))

    if decision.get("intent") == "external":
        return exec_out

    if mode == "simple":
        if force_mode == "execution":
            return exec_out or verification_summary or "sin salida"
        if force_mode == "reasoning" or (decision.get("intent") == "reasoning" and not decision.get("needs_execution")):
            return exec_out or plan_text or verification_summary or "sin salida"
        return exec_out or verification_summary or plan_text or "sin salida"

    sections = []
    if mode == "debug":
        sections.append("Debug\n" + "\n".join(_debug_meta_lines(decision, verification)))
    if plan_text:
        sections.append(f"Plan\n{plan_text}")
    if exec_out:
        sections.append(f"Ejecución\n{exec_out}")
    if verification_summary:
        sections.append(f"Verificación\n{verification_summary}")
    return "\n\n".join(sections).strip()


def cmd_boundary(prompt):
    rc, clean, _ = orchestrate_partner_request(prompt, force_mode="external", stream_output=True)
    if clean and get_output_mode() != "debug":
        print()
    sys.exit(rc)


def verify_execution_result(prompt, result_text):
    result = (result_text or "").strip()
    if not result:
        report = build_execution_report("verification", "failed", "la ejecución no devolvió salida útil", verified=False)
        save_orchestration_report(execution=report)
        return report

    verdict_prompt = dedent(f"""
    Evalúa si la siguiente salida resolvió la tarea del usuario.

    Tarea del usuario: {prompt}
    Resultado observado:
    {result}

    Responde solo JSON con:
    {{"verdict":"passed|needs_followup|failed","summary":"..."}}
    """).strip()
    rc, clean, _ = call_hermes_query(verdict_prompt, forced_role="reasoning")
    verdict = "passed" if rc == 0 else "needs_followup"
    summary = clean or "verificación no concluyente; revisar salida"
    try:
        payload = json.loads(clean) if clean and clean.strip().startswith('{') else None
    except Exception:
        payload = None
    if payload:
        verdict = payload.get("verdict") or verdict
        summary = payload.get("summary") or summary
    report = build_execution_report("verification", verdict, summary, verified=(verdict == "passed"))
    save_orchestration_report(execution=report)
    return report


def run_nemoclaw_boundary_action(prompt, decision):
    if which("nemoclaw") is None:
        report = build_execution_report("nemoclaw", "pending", "Nemoclaw no está instalado; el path outward sigue pendiente", verified=False)
        save_orchestration_report(execution=report)
        return 1, report["summary"], None
    res = run(["nemoclaw", "--version"], capture=True, timeout=10)
    summary = "Boundary/outward path detectado; Nemoclaw queda reservado para la exposición segura en una fase posterior."
    if res.returncode != 0:
        summary = "Nemoclaw está presente pero no quedó operativo para boundary/outward."
        report = build_execution_report("nemoclaw", "failed", summary, verified=False)
        save_orchestration_report(execution=report)
        return 1, summary, None
    report = build_execution_report("nemoclaw", "pending", summary, verified=False)
    save_orchestration_report(execution=report)
    return 0, summary, None


def run_execution_with_openclaw(prompt, plan_text=None, stream_output=False):
    identity = get_partner_identity()
    preamble = (
        f"Eres {identity.get('partner_name') or 'Miliciano'}, el ejecutor operativo de Miliciano by Milytics. "
        "Toma la instrucción y ejecútala o responde como operador de ejecución."
    )
    full_prompt = f"{preamble}\n\nTarea: {prompt}"
    if plan_text:
        full_prompt += f"\n\nPlan de Hermes:\n{plan_text}"
    rc, out = run_openclaw_agent(full_prompt, stream_output=stream_output)
    return rc, out, None


def orchestrate_partner_request(prompt, session_id=None, force_mode=None, stream_output=False):
    decision = classify_orchestration_intent(prompt, forced_mode=force_mode)
    policy = evaluate_policy_for_prompt(prompt, decision)
    save_orchestration_report(decision=decision, policy=policy)

    if decision["intent"] == "reasoning" and decision["target"] == "hermes":
        rc, clean, sid = call_hermes_query(prompt, session_id=session_id, stream_output=stream_output)
        report = build_execution_report("hermes", "passed" if rc == 0 else "failed", clean or "sin salida", verified=(rc == 0))
        save_orchestration_report(execution=report)
        return rc, clean, sid

    if decision["intent"] == "external":
        rc, clean, sid = run_nemoclaw_boundary_action(prompt, decision)
        return rc, clean, sid

    if policy["verdict"] == "deny":
        clean = f"Bloqueado por policy: {policy['reason']}"
        if policy.get("next_step"):
            clean += f"\nSiguiente paso: {policy['next_step']}"
        report = build_execution_report(decision["target"], "blocked", clean, verified=False)
        save_orchestration_report(execution=report)
        return 1, clean, session_id

    if policy["verdict"] == "ask" and decision.get("needs_execution"):
        clean = f"Requiere aprobación: {policy['reason']}"
        if policy.get("next_step"):
            clean += f"\nSiguiente paso: {policy['next_step']}"
        report = build_execution_report(decision["target"], "approval_required", clean, verified=False)
        save_orchestration_report(execution=report)
        return 2, clean, session_id

    planning_prompt = dedent(f"""
    Actúa como el cerebro/orquestador de Miliciano by Milytics.
    Tarea del usuario: {prompt}

    Devuelve solamente:
    1. OBJETIVO
    2. PLAN
    3. CRITERIO_DE_VERIFICACION

    Sé concreto y orientado a ejecución.
    """).strip()
    planning_rc, plan_text, planning_sid = call_hermes_query(planning_prompt, session_id=session_id, forced_role="reasoning", stream_output=stream_output)
    plan_text = normalize_plan_text(plan_text)
    active_sid = planning_sid or session_id
    if planning_rc != 0 or not plan_text:
        report = build_execution_report("hermes", "failed", plan_text or "Hermes no pudo planificar", verified=False)
        save_orchestration_report(execution=report)
        return planning_rc or 1, plan_text or "Hermes no pudo planificar la tarea", active_sid

    rc, exec_out, _ = run_execution_with_openclaw(prompt, plan_text=plan_text, stream_output=stream_output)
    verification = verify_execution_result(prompt, exec_out)
    verification["summary"] = normalize_verification_summary(verification.get("summary"))
    summary = format_partner_response(decision, plan_text, exec_out, verification, force_mode=force_mode)
    save_obsidian_memory(prompt, summary, source="orchestration", session_id=active_sid)
    return rc if verification["verified"] else (rc or 2), summary, active_sid


def cmd_ask(prompt):
    rc, clean, _ = orchestrate_partner_request(prompt, stream_output=True)
    if clean and get_output_mode() != "debug":
        print()
    sys.exit(rc)


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
        if forced_role in {"fast", "reasoning"}:
            mapped_force = "reasoning" if forced_role == "reasoning" else None
            rc, clean, session_id = orchestrate_partner_request(raw_prompt, session_id=session_id, force_mode=mapped_force, stream_output=True)
        else:
            rc, clean, session_id = orchestrate_partner_request(raw_prompt, session_id=session_id, stream_output=True)
        if clean and get_output_mode() != "debug":
            print()
        if rc != 0:
            print(f"[salida {rc}] revisión de la última respuesta")


def render_home_dashboard():
    banner()
    state = load_miliciano_state()
    identity = get_partner_identity()
    rows = [
        f"partner     {identity.get('partner_name') or 'Miliciano'}",
        f"persona     {identity.get('persona_key') or 'operator'}",
        f"operador    {identity.get('owner_name') or 'n/d'}",
        f"output      {get_output_mode()}",
        f"route       {get_route_mode()}",
        f"permission  {get_permission_mode()}",
    ]
    panel("MILICIANO HOME", rows)

    jobs = list_miliciano_jobs()
    tasks = list_open_miliciano_tasks()
    setup_hint = "listo para trabajar" if (state.get('identity') or {}).get('partner_name') else "necesita personalización"
    panel("HOY", [
        f"estado       {setup_hint}",
        f"jobs         {len(jobs)} programado(s)",
        f"tasks        {len(tasks)} abiertos",
        "ask          pensar, analizar y decidir",
        "exec         ejecutar una tarea concreta",
        "mission      planear y luego ejecutar",
        "task         gestionar la bandeja diaria",
        "identity     personalizar nombre y estilo",
        "setup        cerrar la instalación base",
    ])

    print("Siguiente paso recomendado:")
    print("  miliciano ask \"qué quieres resolver hoy\"")
    print("  miliciano mission \"objetivo de trabajo\"")
    print("  miliciano exec \"tarea concreta\"")
    print("  miliciano identity")
    print("  miliciano setup --dry-run")
    print(f"{DIM}Miliciano-first: usa este panel como entrada diaria. El chat táctico vive en `miliciano shell`.{RESET}")


def render_day_dashboard():
    banner()
    identity = get_partner_identity()
    open_tasks = sort_open_miliciano_tasks()
    due_jobs = list_due_miliciano_jobs()
    top_tasks = open_tasks[:5]
    recommended = []
    if top_tasks:
        recommended.append(f"1. empieza por: {top_tasks[0]['title']}")
        if len(top_tasks) > 1:
            recommended.append(f"2. siguiente: {top_tasks[1]['title']}")
    else:
        recommended.append("1. no hay tareas abiertas; crea una con `miliciano task add`")
    if due_jobs:
        recommended.append(f"2. hay {len(due_jobs)} job(s) vencido(s) para automatizar")
    else:
        recommended.append("2. no hay jobs vencidos ahora mismo")
    panel("HOY / COMANDO DIARIO", [
        f"partner     {identity.get('partner_name') or 'Miliciano'}",
        f"tareas      {len(open_tasks)} abiertas",
        f"jobs        {len(due_jobs)} vencidos",
        *recommended,
    ])

    task_rows = [summarize_miliciano_task(task) for task in top_tasks] or ["sin tareas  crea una tarea para comenzar el día"]
    panel("TOP TAREAS", task_rows)

    job_rows = [render_job_summary(job) for job in due_jobs[:5]] or ["sin jobs  nada vencido ahora mismo"]
    panel("JOBS PARA HOY", job_rows)

    panel("SIGUIENTE ACCIÓN", [
        "miliciano task add <titulo> [nota]",
        "miliciano task start <task-id>",
        "miliciano jobs scheduler --once",
        "miliciano ask \"quiero avanzar en esto\"",
        "miliciano mission \"objetivo de hoy\"",
    ])
    print(f"{DIM}Miliciano day: prioriza tareas abiertas, luego jobs vencidos, luego el siguiente paso útil.{RESET}")


def render_about_card():
    banner()
    panel("MILICIANO / ABOUT", [
        "qué es      partner tecnológico personalizable para trabajo real",
        "para quién  builders, founders, ops y equipos que quieren velocidad",
        "promesa     ayudar a pensar, ejecutar y dejar trazabilidad",
        "centro      identidad propia + loop diario + setup cómodo",
        "cara        Miliciano-first; Hermes queda bajo el capó",
    ])
    panel("CÓMO SE USA", [
        "home        ver panel principal y próximos pasos",
        "ask         pedir ayuda y dejar que orqueste",
        "exec        ejecutar una tarea concreta",
        "mission     planear y luego ejecutar",
        "task        gestionar tu bandeja diaria",
        "jobs        administrar automatizaciones persistentes",
        "identity    personalizar nombre y personalidad",
        "shell       chat táctico interactivo",
    ])
    print("Mensaje corto:")
    print("  Miliciano es tu partner tecnológico: entra, se personaliza y te ayuda a trabajar mejor desde el primer día.")


def cmd_about():
    render_about_card()


def cmd_day():
    render_day_dashboard()


def render_jobs_dashboard():
    banner()
    jobs = list_miliciano_jobs()
    rows = []
    if not jobs:
        rows.append("sin jobs   todavía no hay automatizaciones guardadas")
    else:
        for job in jobs[:10]:
            rows.append(render_job_summary(job))
    panel("JOBS MILICIANO", rows)
    print("Uso:")
    print("  miliciano jobs")
    print("  miliciano jobs add <titulo> <cron> <prompt>")
    print("  miliciano jobs run <job-id>")
    print("  miliciano jobs enable <job-id>")
    print("  miliciano jobs disable <job-id>")
    print("  miliciano jobs remove <job-id>")
    print("  miliciano jobs due")
    print("  miliciano jobs scheduler --once")
    print("  miliciano jobs scheduler --loop")
    print("Nota:")
    print("  Miliciano guarda la intención y el registro; Hermes razona; OpenClaw ejecuta cuando toca.")


def cmd_jobs(args):
    banner()
    if not args or args[0] in {"show", "status", "list"}:
        render_jobs_dashboard()
        return
    action = args[0].lower()
    if action == "add":
        if len(args) < 4:
            print("Uso: miliciano jobs add <titulo> <cron> <prompt>", file=sys.stderr)
            sys.exit(1)
        title = args[1]
        schedule = args[2]
        prompt = " ".join(args[3:]).strip()
        job = create_miliciano_job(title, schedule, prompt)
        print(f"Job creado: {job['id']} · {job['title']}")
        render_jobs_dashboard()
        return
    if action == "run":
        if len(args) != 2:
            print("Uso: miliciano jobs run <job-id>", file=sys.stderr)
            sys.exit(1)
        rc, clean, job = run_miliciano_job(args[1])
        response_box(clean or "Job ejecutado sin salida", title=f"Job · {job['id']}")
        sys.exit(rc)
    if action == "due":
        due = list_due_miliciano_jobs()
        rows = [render_job_summary(job) for job in due] or ["sin jobs  ningún job está vencido ahora mismo"]
        panel("JOBS VENCIDOS", rows)
        return
    if action == "scheduler":
        once = "--once" in args[1:]
        loop = "--loop" in args[1:]
        quiet = "--quiet" in args[1:]
        if not once and not loop:
            print("Uso: miliciano jobs scheduler --once | --loop", file=sys.stderr)
            sys.exit(1)
        if once:
            results = run_due_miliciano_jobs()
            if not results:
                print("No hay jobs vencidos ahora mismo.")
                return
            for result in results:
                response_box(result.get("output") or "Job ejecutado", title=f"Scheduler · {result['id']}")
            return
        scheduler_loop(quiet=quiet)
        return
    if action in {"enable", "disable"}:
        if len(args) != 2:
            print(f"Uso: miliciano jobs {action} <job-id>", file=sys.stderr)
            sys.exit(1)
        job = update_miliciano_job(args[1], enabled=(action == "enable"))
        print(f"Job {job['id']} ahora está {'activo' if job.get('enabled') else 'pausado'}")
        render_jobs_dashboard()
        return
    if action == "remove":
        if len(args) != 2:
            print("Uso: miliciano jobs remove <job-id>", file=sys.stderr)
            sys.exit(1)
        ok = remove_miliciano_job(args[1])
        if not ok:
            print("No encontré ese job.", file=sys.stderr)
            sys.exit(1)
        print(f"Job {args[1]} eliminado")
        render_jobs_dashboard()
        return
    print(f"Acción de jobs desconocida: {action}", file=sys.stderr)
    print("Usa: show | add | run | due | scheduler | enable | disable | remove", file=sys.stderr)
    sys.exit(1)


def render_task_dashboard():
    banner()
    tasks = list_miliciano_tasks()
    open_tasks = [task for task in tasks if task.get('status') not in {'completed', 'cancelled'}]
    rows = []
    if not tasks:
        rows.append("sin tareas  todavía no hay tareas registradas")
    else:
        for task in tasks[:12]:
            rows.append(summarize_miliciano_task(task))
    panel("TASKS MILICIANO", rows)
    print("Uso:")
    print("  miliciano task")
    print("  miliciano task add <titulo> [nota]")
    print("  miliciano task list")
    print("  miliciano task start <task-id>")
    print("  miliciano task done <task-id>")
    print("  miliciano task cancel <task-id>")
    print("  miliciano task priority <task-id> <low|medium|high>")
    print("  miliciano task remove <task-id>")
    print("Nota:")
    print("  Miliciano te ayuda a mover trabajo humano de hoy; jobs automatiza lo repetible.")


def cmd_task(args):
    banner()
    if not args or args[0] in {'show', 'status', 'list'}:
        render_task_dashboard()
        return
    action = args[0].lower()
    if action == 'add':
        if len(args) < 2:
            print('Uso: miliciano task add <titulo> [nota]', file=sys.stderr)
            sys.exit(1)
        title = args[1]
        note = ' '.join(args[2:]).strip()
        task = create_miliciano_task(title, note)
        print(f"Task creada: {task['id']} · {task['title']}")
        render_task_dashboard()
        return
    if action == 'start':
        if len(args) != 2:
            print('Uso: miliciano task start <task-id>', file=sys.stderr)
            sys.exit(1)
        task = update_miliciano_task(args[1], status='in_progress')
        print(f"Task {task['id']} en progreso")
        render_task_dashboard()
        return
    if action == 'done':
        if len(args) != 2:
            print('Uso: miliciano task done <task-id>', file=sys.stderr)
            sys.exit(1)
        task = complete_miliciano_task(args[1])
        print(f"Task {task['id']} completada")
        render_task_dashboard()
        return
    if action == 'cancel':
        if len(args) != 2:
            print('Uso: miliciano task cancel <task-id>', file=sys.stderr)
            sys.exit(1)
        task = update_miliciano_task(args[1], status='cancelled')
        print(f"Task {task['id']} cancelada")
        render_task_dashboard()
        return
    if action == 'priority':
        if len(args) != 3:
            print('Uso: miliciano task priority <task-id> <low|medium|high>', file=sys.stderr)
            sys.exit(1)
        level = args[2].lower()
        if level not in {'low', 'medium', 'high'}:
            print('Prioridad inválida: usa low, medium o high', file=sys.stderr)
            sys.exit(1)
        task = update_miliciano_task(args[1], priority=level)
        print(f"Task {task['id']} prioridad -> {task['priority']}")
        render_task_dashboard()
        return
    if action == 'remove':
        if len(args) != 2:
            print('Uso: miliciano task remove <task-id>', file=sys.stderr)
            sys.exit(1)
        if not remove_miliciano_task(args[1]):
            print('No encontré esa task.', file=sys.stderr)
            sys.exit(1)
        print(f"Task {args[1]} eliminada")
        render_task_dashboard()
        return
    print(f"Acción de task desconocida: {action}", file=sys.stderr)
    print('Usa: show | add | list | start | done | cancel | remove', file=sys.stderr)
    sys.exit(1)


def cmd_home():
    render_home_dashboard()


def cmd_start():
    render_home_dashboard()


def cmd_shell():
    banner()
    interactive_chat()


def cmd_think(prompt):
    raw_prompt = prompt.strip()
    force_mode = None
    if raw_prompt.startswith("--reasoning "):
        force_mode = "reasoning"
        raw_prompt = raw_prompt[12:].strip()
    rc, clean, _ = orchestrate_partner_request(raw_prompt, force_mode=force_mode, stream_output=True)
    if clean and get_output_mode() != "debug":
        print()
    sys.exit(rc)

def cmd_exec(prompt):
    rc, clean, _ = orchestrate_partner_request(prompt, force_mode="execution", stream_output=True)
    if clean and get_output_mode() != "debug":
        print()
    sys.exit(rc)

def cmd_mission(prompt):
    rc, clean, _ = orchestrate_partner_request(prompt, force_mode="hybrid", stream_output=True)
    if clean and get_output_mode() != "debug":
        print()
    sys.exit(rc)

