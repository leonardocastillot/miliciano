#!/usr/bin/env python3
from shutil import which

from miliciano_runtime import *
from miliciano_ui import *
from miliciano_obsidian import *

def render_session_status(session_id=None, include_banner=True):
    from shutil import which

    if include_banner:
        banner()
    runtime = basic_runtime_status()
    hermes_path = which("hermes")
    openclaw_path = which("openclaw")
    nemoclaw_path = which("nemoclaw")

    health = run(["openclaw", "health", "--json"], capture=True, timeout=6) if openclaw_path else None
    health_out = (health.stdout or "").strip() if health else ""
    gateway_ok = bool(health and health.returncode == 0 and '"ok":true' in health_out.lower().replace(" ", ""))

    auth_probe = run(
        ["openclaw", "agent", "--agent", "main", "--message", "Responde solo OK"],
        capture=True,
        timeout=20,
    ) if openclaw_path else None
    auth_out = (auth_probe.stdout or "") if auth_probe else ""
    auth_ok = bool(auth_probe and auth_probe.returncode == 0 and "No API key found for provider" not in auth_out and "FailoverError:" not in auth_out)

    nemoclaw_ok = False
    nemoclaw_out = ""
    if nemoclaw_path:
        res = run(["nemoclaw", "--version"], capture=True, timeout=6)
        nemoclaw_out = (res.stdout or "").strip()
        nemoclaw_ok = res.returncode == 0

    reasoning_ok = bool(hermes_path)
    execution_ok = bool(openclaw_path and gateway_ok and auth_ok)
    policy_ok = nemoclaw_ok
    hermes_model = collect_hermes_model_status()
    openclaw_model = collect_openclaw_model_status()
    nemoclaw_model = collect_nemoclaw_status()
    ollama_status = collect_ollama_status()
    local_hw = collect_local_ai_hardware()
    ollama_recos = recommend_ollama_models(local_hw)
    orchestration = load_last_orchestration_report()
    orchestration_decision = orchestration.get("decision") or {}
    orchestration_policy = orchestration.get("policy") or {}
    orchestration_execution = orchestration.get("execution") or {}
    orchestration_policy_ready = bool(orchestration_policy.get("verdict"))
    output_mode = get_output_mode()
    route_mode = get_route_mode()
    permission_mode = get_permission_mode()
    project_instructions = load_miliciano_project_instructions()
    reasoning_probe = probe_reasoning_path()
    execution_probe = probe_execution_path()
    local_probe = probe_local_path()
    boundary_probe = probe_boundary_path()

    execution_limit_kind = "pending"
    execution_limit_text = "sin señal de cuota agotada"
    if detect_quota_signal(auth_out):
        execution_limit_kind = "error"
        execution_limit_text = "posible cuota/límite agotado"
        openclaw_model["quota_exhausted"] = True
    elif auth_probe and auth_probe.returncode == 124:
        execution_limit_text = "timeout consultando OpenClaw; backend lento o colgado"
    elif auth_probe and auth_probe.returncode == 0:
        execution_limit_kind = "ready"

    reasoning_limit_kind = "error" if hermes_model["quota_exhausted"] else "info"
    reasoning_limit_text = "sin API de cuota; muestro auth/plan/token"
    if hermes_model["quota_exhausted"]:
        reasoning_limit_text = hermes_model["last_error"] or "último error sugiere cuota/límite agotado"

    panel("PANEL OPERATIVO", [
        f"reasoning      {status_badge('ready' if reasoning_ok else 'pending')}",
        f"execution      {status_badge('ready' if execution_ok else 'pending')}",
        f"policy         {status_badge('ready' if policy_ok else 'pending')}",
        f"orchestration  {status_badge('ready' if orchestration_policy_ready else 'pending')}",
    ])

    panel("MODOS DE PRODUCTO", [
        f"output        {output_mode}",
        f"route         {route_mode}",
        f"permission    {permission_mode}",
    ])

    identity = get_partner_identity()
    panel("IDENTIDAD DEL PARTNER", [
        f"nombre        {identity.get('partner_name') or 'Miliciano'}",
        f"persona       {identity.get('persona_key') or 'operator'}",
        f"tono          {(identity.get('persona') or {}).get('tone')}",
        f"estilo        {identity.get('interaction_style') or 'directo y útil'}",
        f"idioma        {identity.get('language') or 'es'}",
        f"operador      {identity.get('owner_name') or 'n/d'}",
    ])

    runtime_rows = []
    for cmd in PREREQ_COMMANDS:
        required = cmd in REQUIRED_SYSTEM_COMMANDS
        kind = 'ready' if runtime[cmd]['path'] else ('error' if required else 'pending')
        suffix = '' if required else ' · opcional'
        runtime_rows.append(f"{cmd:<7} {status_badge(kind)}  {runtime[cmd]['version'] or 'no detectado'}{suffix}")

    panel("RUNTIME BASE", runtime_rows)

    panel("STACK MILICIANO", [
        f"hermes    {(status_badge('ready') if hermes_path else status_badge('error'))}  {hermes_path or 'no encontrado'}",
        f"openclaw  {(status_badge('ready') if openclaw_path else status_badge('error'))}  {openclaw_path or 'no encontrado'}",
        f"nemoclaw  {(status_badge('ready') if nemoclaw_path else status_badge('pending'))}  {nemoclaw_path or 'no encontrado'}",
    ])

    panel("EJECUCIÓN Y POLICY", [
        f"gateway openclaw  {(status_badge('ready') if gateway_ok else status_badge('error'))}",
        f"auth modelo       {(status_badge('ready') if auth_ok else status_badge('pending'))}",
        f"nemoclaw runtime  {(status_badge('ready') if nemoclaw_ok else status_badge('error' if nemoclaw_path else 'pending'))}",
    ])

    panel("INFERENCIA LOCAL", [
        f"ollama    {(status_badge('ready') if ollama_status['path'] else status_badge('pending'))}  {ollama_status['version'] or 'no instalado'}",
        f"api local {(status_badge('ready') if ollama_status['api_ok'] else status_badge('pending'))}  {ollama_status['api_detail']}",
        f"hardware  {local_hw['cpu'] or 'CPU n/d'} · RAM {local_hw['ram_gib'] or 'n/d'} GiB · GPU {local_hw['gpu'] or 'n/d'} · VRAM {local_hw['gpu_vram_gib'] or 'n/d'} GiB",
        f"sugerido  {ollama_recos[0][0]} · {ollama_recos[0][1]}",
    ])

    panel("SALUD END-TO-END", [
        f"reasoning   {status_badge(reasoning_probe['kind'])}  {reasoning_probe['summary']}",
        f"execution   {status_badge(execution_probe['kind'])}  {execution_probe['summary']}",
        f"local       {status_badge(local_probe['kind'])}  {local_probe['summary']}",
        f"boundary    {status_badge(boundary_probe['kind'])}  {boundary_probe['summary']}",
    ])

    panel("MODELOS Y LÍMITES", [
        f"hermes    {status_badge('ready' if reasoning_ok else 'pending')}  {hermes_model['provider']}/{hermes_model['model']}",
        f"          plan={hermes_model['plan'] or 'n/d'} · auth={hermes_model['auth_mode'] or 'n/d'} · expira={format_timestamp(hermes_model['expires_at'])}",
        f"          límites {status_badge(reasoning_limit_kind)}  {reasoning_limit_text}",
        f"openclaw  {status_badge('ready' if auth_ok else 'pending')}  {openclaw_model['model']}",
        f"          plan={openclaw_model['plan'] or 'n/d'} · perfil={openclaw_model['email'] or 'n/d'} · expira={format_timestamp(openclaw_model['expires_at'], ms=True)}",
        f"          límites {status_badge(execution_limit_kind)}  {execution_limit_text}",
        f"          uso previo: errores={openclaw_model['error_count'] or 0} · último uso={format_timestamp(openclaw_model['last_used'], ms=True)} · último fallo={format_timestamp(openclaw_model['last_failure_at'], ms=True)}",
        f"nemoclaw {status_badge('ready' if policy_ok else 'pending')}  modelo reservado={nemoclaw_model['model'] or 'sin definir'}",
    ])

    panel("ORQUESTACIÓN", [
        f"último intent    {orchestration_decision.get('intent') or 'n/d'}",
        f"último target    {orchestration_decision.get('target') or 'n/d'}",
        f"policy verdict   {orchestration_policy.get('verdict') or 'n/d'}",
        f"policy reason    {orchestration_policy.get('reason') or 'n/d'}",
        f"policy mode      {orchestration_policy.get('mode') or permission_mode}",
        f"exec outcome     {orchestration_execution.get('outcome') or 'n/d'}",
        f"exec verified    {'sí' if orchestration_execution.get('verified') else 'no' if orchestration_execution else 'n/d'}",
    ])

    obsidian = collect_obsidian_status()
    panel("OBSIDIAN CEREBRO", [
        f"vault     {status_badge('ready' if obsidian['present'] else 'pending')}  {obsidian['path']}",
        f"notas     {obsidian['total_notes']}",
        f"dashboard {status_badge('ready' if obsidian['dashboard_exists'] else 'pending')}  00 Dashboard",
        f"miliciano {status_badge('ready' if obsidian['miliciano_exists'] else 'pending')}  {OBSIDIAN_MILICIANO_NOTE}",
    ])

    panel("INSTRUCCIONES DE PROYECTO", [
        f"MILICIANO.md  {status_badge('ready' if project_instructions['present'] else 'pending')}  {project_instructions['path'] or 'no detectado'}",
    ])

    jobs = list_miliciano_jobs()
    tasks = list_open_miliciano_tasks()
    panel("JOBS PERSISTENTES", [
        f"jobs         {len(jobs)} definidos",
        f"modelo       Miliciano guarda intención; Hermes razona; OpenClaw ejecuta",
    ])
    panel("TASKS ABIERTAS", [
        f"tasks        {len(tasks)} abiertas",
        f"modelo       Miliciano prioriza la bandeja diaria de trabajo humano",
    ])

    if session_id is not None:
        panel("SESIÓN ACTUAL", [
            f"session_id  {session_id or 'nueva'}",
            f"reasoning   {hermes_model['provider']}/{hermes_model['model']}",
            f"execution   {openclaw_model['model']}",
        ])

    if health_out and not gateway_ok:
        print_kv("detalle gateway", health_out)
    if nemoclaw_path and nemoclaw_out:
        print_kv("detalle nemoclaw", nemoclaw_out)
    if auth_out and detect_quota_signal(auth_out):
        print_kv("detalle límite ejecución", "OpenClaw devolvió una señal compatible con cuota/rate limit")

def cmd_status():
    render_session_status()

def cmd_doctor(args=None):
    banner()
    openclaw_path = which("openclaw")
    panel("DOCTOR", [
        f"hermes          {status_badge('info')} diagnóstico del core",
        f"openclaw        {status_badge('info' if openclaw_path else 'pending')} diagnóstico del motor de ejecución",
        f"security audit  {status_badge('info' if openclaw_path else 'pending')} revisión profunda de seguridad",
    ])
    print(f"{BOLD}Hermes doctor{RESET}")
    print(rule(accent="─"))
    run(["hermes", "doctor"])
    print()
    if not openclaw_path:
        print(f"{BOLD}OpenClaw doctor{RESET}")
        print(rule(accent="─"))
        print("OpenClaw no está instalado; se omite el diagnóstico profundo del motor de ejecución.")
        print("Sugerencia: usa `miliciano bootstrap` o `miliciano setup --auto` con un hook de instalación, o instala OpenClaw manualmente.")
        return
    print(f"{BOLD}OpenClaw doctor{RESET}")
    print(rule(accent="─"))
    run(["openclaw", "doctor"])
    print()
    print(f"{BOLD}OpenClaw security audit{RESET}")
    print(rule(accent="─"))
    run(["openclaw", "security", "audit", "--deep"])

