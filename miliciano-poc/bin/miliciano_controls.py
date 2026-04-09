#!/usr/bin/env python3
import json
import os
import sys
import tempfile

from miliciano_runtime import *
from miliciano_ui import *

def print_route_overview():
    state = load_miliciano_state()
    routes = state.get("routing", {})
    local_model = preferred_local_ollama_model()
    nvidia = collect_nvidia_status()
    openclaw_fallbacks = collect_openclaw_fallbacks()
    panel("ROUTING ACTIVO", [
        f"reasoning  {routes.get('reasoning')}",
        f"execution  {routes.get('execution')}",
        f"fast       {routes.get('fast')}",
        f"local      {routes.get('local') or 'sin definir'}",
        f"fallback   {routes.get('fallback') or 'sin definir'}",
        f"nvidia     {nvidia['model'] if nvidia['enabled'] else 'desactivado'}",
    ])
    panel("CAPA LOCAL Y REMOTA", [
        f"preferido  {state.get('ollama', {}).get('preferred_model') or 'sin definir'}",
        f"detectado  {local_model or 'sin modelos locales'}",
        f"fallbacks openclaw  {', '.join(openclaw_fallbacks) if openclaw_fallbacks else 'sin fallback remoto aplicado'}",
    ])
    print("Uso:")
    print("  miliciano route")
    print("  miliciano route set reasoning openai-codex/gpt-5.4")
    print("  miliciano route set fast local")
    print("  miliciano route set local qwen2.5:3b")
    print("  miliciano route set fallback anthropic/claude-sonnet-4")
    print("  miliciano route set fallback nvidia/llama-3.1-nemotron-70b-instruct")
    print("  miliciano route use fast")
    print("  miliciano route sync")
    print(f"{DIM}Auto-routing: Miliciano prioriza reasoning remoto; fast solo se detecta una tarea simple y hay modelo local útil disponible.{RESET}")

def print_model_overview():
    state = load_miliciano_state()
    nvidia = collect_nvidia_status()
    panel("MODELOS ACTIVOS", [
        f"hermes    {state['hermes']['provider']}/{state['hermes']['model']}",
        f"openclaw  {state['openclaw']['model']}",
        f"nemoclaw  {state['nemoclaw']['model'] or 'sin definir'}",
        f"nvidia    {nvidia['model'] if nvidia['enabled'] else 'sin activar'}",
    ])
    print_route_overview()
    print("Uso:")
    print("  miliciano model")
    print("  miliciano model hermes local")
    print("  miliciano model hermes custom/qwen2.5:3b")
    print("  miliciano model hermes openai-codex/gpt-5.4")
    print("  miliciano model openclaw openai-codex/gpt-5.4")
    print("  miliciano model all openai-codex/gpt-5.4-mini")
    print("  miliciano model nemoclaw nemotron/local")
    print("  miliciano provider activate fallback nvidia/llama-3.1-nemotron-70b-instruct")
    print(f"{DIM}Miliciano ya no piensa en un solo modelo: guarda rutas por rol y deja el local como base/fallback.{RESET}")
    print(f"{DIM}Nemoclaw aún no está integrado al camino de inferencia; el valor se guarda como reserva.{RESET}")


def print_mode_overview():
    panel("MODOS ACTIVOS", [
        f"output       {get_output_mode()}",
        f"route        {get_route_mode()}",
        f"permission   {get_permission_mode()}",
    ])
    print("Uso:")
    print("  miliciano mode")
    print("  miliciano mode output simple")
    print("  miliciano mode output operator")
    print("  miliciano mode output debug")
    print("  miliciano mode route cheap")
    print("  miliciano mode route balanced")
    print("  miliciano mode route max")
    print("  miliciano mode permission plan")
    print("  miliciano mode permission ask")
    print("  miliciano mode permission accept-edits")
    print("  miliciano mode permission execute")
    print("  miliciano mode permission restricted-boundary")

def set_hermes_model(spec, update_route=True):
    provider, model = resolve_hermes_model_spec(spec)
    state = load_miliciano_state()
    state["hermes"]["provider"] = provider
    state["hermes"]["model"] = model
    if update_route:
        state.setdefault("routing", {})["reasoning"] = make_model_spec(provider, model)
    if provider == "custom":
        state.setdefault("ollama", {})["preferred_model"] = model
    if provider == "nvidia":
        nvidia_state = state.setdefault("nvidia", {})
        nvidia_state["enabled"] = True
        nvidia_state["api_key_present"] = any(os.environ.get(name) for name in NVIDIA_API_ENV_VARS)
        nvidia_state["base_url"] = NVIDIA_BASE_URL
        nvidia_state["model"] = model
        save_miliciano_state(state)
        print(f"Fallback NVIDIA configurado en {provider}/{model}")
        return
    save_miliciano_state(state)
    sync_hermes_global_config(provider, model)
    sync_hermes_profile_config(provider, model)
    print(f"Hermes configurado en {provider}/{model}")

def set_openclaw_model(spec, update_route=True):
    need("openclaw")
    res = run(["openclaw", "models", "set", spec], capture=True)
    out = (res.stdout or "").strip()
    if res.returncode != 0:
        print(out or "No pude cambiar el modelo de OpenClaw.", file=sys.stderr)
        return res.returncode
    state = load_miliciano_state()
    state["openclaw"]["model"] = spec
    if update_route:
        state.setdefault("routing", {})["execution"] = spec
    save_miliciano_state(state)
    print(f"OpenClaw configurado en {spec}")
    return 0

def set_nemoclaw_model(spec):
    state = load_miliciano_state()
    state["nemoclaw"]["model"] = spec
    save_miliciano_state(state)
    print(f"Nemoclaw reservado en {spec}")
    print("Nemoclaw todavía no participa en el camino de inferencia de Miliciano.")

def set_route_target(role, spec):
    role = role.lower()
    if role not in ROUTE_ROLE_LABELS:
        raise ValueError(f"ruta desconocida: {role}")
    normalized = resolve_route_spec(role, spec)
    if role == "reasoning":
        set_hermes_model(normalized, update_route=True)
        return
    if role == "execution":
        rc = set_openclaw_model(normalized, update_route=True)
        if rc != 0:
            sys.exit(rc)
        return

    state = load_miliciano_state()
    state.setdefault("routing", {})[role] = normalized
    if role == "local" and normalized and normalized.startswith("custom/"):
        state.setdefault("ollama", {})["preferred_model"] = normalized.split("/", 1)[1]
    if normalized and normalized.startswith("nvidia/"):
        nvidia_state = state.setdefault("nvidia", {})
        nvidia_state["enabled"] = True
        nvidia_state["api_key_present"] = any(os.environ.get(name) for name in NVIDIA_API_ENV_VARS)
        nvidia_state["base_url"] = NVIDIA_BASE_URL
        nvidia_state["model"] = normalized.split("/", 1)[1]
    save_miliciano_state(state)
    print(f"Ruta {role} actualizada a {normalized or 'sin definir'}")
    if role == "fallback":
        ok, detail = sync_openclaw_fallback_route(state)
        label = "OK" if ok else "WARN"
        print(f"[{label}] {detail}")

def use_route_target(role):
    role = role.lower()
    state = load_miliciano_state()
    spec = state.get("routing", {}).get(role)
    if not spec:
        print(f"La ruta {role} no está definida.", file=sys.stderr)
        sys.exit(1)
    if role == "execution":
        rc = set_openclaw_model(spec, update_route=False)
        if rc != 0:
            sys.exit(rc)
        return
    set_hermes_model(spec, update_route=False)
    print(f"Ruta {role} aplicada al motor de razonamiento")

def cmd_route(args):
    banner()
    if not args or args[0] in {"show", "status", "list"}:
        print_route_overview()
        return

    action = args[0].lower()
    if action == "set":
        if len(args) < 3:
            print("Uso: miliciano route set <reasoning|execution|fast|local|fallback> <modelo>", file=sys.stderr)
            sys.exit(1)
        role = args[1]
        spec = " ".join(args[2:]).strip()
        set_route_target(role, spec)
        return
    if action == "use":
        if len(args) != 2:
            print("Uso: miliciano route use <reasoning|execution|fast|local|fallback>", file=sys.stderr)
            sys.exit(1)
        use_route_target(args[1])
        return
    if action == "sync":
        state = load_miliciano_state()
        ok, detail = sync_openclaw_fallback_route(state)
        print(detail)
        if not ok:
            sys.exit(1)
        return

    print(f"Acción de routing desconocida: {action}", file=sys.stderr)
    print("Usa: show | set | use | sync", file=sys.stderr)
    sys.exit(1)

def collect_codex_oauth_alignment(hermes_auth, openclaw_auth):
    hermes_entry = ((hermes_auth.get("credential_pool") or {}).get("openai-codex") or [{}])[0]
    openclaw_entry = (openclaw_auth.get("profiles") or {}).get("openai-codex:default") or {}

    hermes_payload = decode_jwt_payload(hermes_entry.get("access_token")) if hermes_entry.get("access_token") else {}
    openclaw_payload = decode_jwt_payload(openclaw_entry.get("access")) if openclaw_entry.get("access") else {}

    hermes_auth_claims = hermes_payload.get("https://api.openai.com/auth", {})
    openclaw_auth_claims = openclaw_payload.get("https://api.openai.com/auth", {})
    hermes_profile = hermes_payload.get("https://api.openai.com/profile", {})
    openclaw_profile = openclaw_payload.get("https://api.openai.com/profile", {})

    hermes_email = hermes_payload.get("email") or hermes_profile.get("email")
    openclaw_email = openclaw_payload.get("email") or openclaw_profile.get("email")
    hermes_account = hermes_auth_claims.get("chatgpt_account_id")
    openclaw_account = openclaw_auth_claims.get("chatgpt_account_id")
    aligned = bool(hermes_account and openclaw_account and hermes_account == openclaw_account)

    if hermes_account or openclaw_account:
        reason = "alineadas" if aligned else "desalineadas: Hermes y OpenClaw usan cuentas OAuth distintas"
    else:
        reason = "sin datos suficientes para comparar cuentas OAuth"

    return {
        "aligned": aligned,
        "reason": reason,
        "hermes_email": hermes_email,
        "openclaw_email": openclaw_email,
        "hermes_account": hermes_account,
        "openclaw_account": openclaw_account,
    }


def collect_auth_overview():
    hermes_auth = read_json_file(HERMES_AUTH_PATH) or {}
    hermes_pool = hermes_auth.get("credential_pool") or {}
    hermes_rows = []
    for provider in sorted(hermes_pool):
        entries = hermes_pool.get(provider) or []
        labels = []
        for entry in entries[:3]:
            labels.append(entry.get("label") or entry.get("id") or entry.get("auth_mode") or "credencial")
        suffix = ""
        if len(entries) > 3:
            suffix = f" +{len(entries) - 3}"
        hermes_rows.append({
            "provider": provider,
            "count": len(entries),
            "labels": ", ".join(labels) + suffix if labels else "sin etiquetas",
        })

    openclaw_auth = read_json_file(OPENCLAW_AUTH_PATH) or {}
    openclaw_profiles = openclaw_auth.get("profiles") or {}
    openclaw_rows = []
    grouped = {}
    for profile_id, entry in openclaw_profiles.items():
        provider = entry.get("provider") or "unknown"
        grouped.setdefault(provider, []).append((profile_id, entry))
    for provider in sorted(grouped):
        rows = grouped[provider]
        labels = []
        for profile_id, entry in rows[:3]:
            labels.append(entry.get("email") or profile_id)
        suffix = ""
        if len(rows) > 3:
            suffix = f" +{len(rows) - 3}"
        openclaw_rows.append({
            "provider": provider,
            "count": len(rows),
            "labels": ", ".join(labels) + suffix if labels else "sin etiquetas",
        })

    env_rows = []
    for provider, env_name in ENV_PROVIDER_HINTS.items():
        env_rows.append({
            "provider": provider,
            "env": env_name,
            "present": bool(os.environ.get(env_name)),
        })

    return {
        "hermes_active": hermes_auth.get("active_provider"),
        "hermes_rows": hermes_rows,
        "openclaw_rows": openclaw_rows,
        "env_rows": env_rows,
        "codex_alignment": collect_codex_oauth_alignment(hermes_auth, openclaw_auth),
    }

def print_auth_overview():
    overview = collect_auth_overview()
    hermes_rows = overview["hermes_rows"] or [{"provider": "ninguno", "count": 0, "labels": "sin credenciales"}]
    openclaw_rows = overview["openclaw_rows"] or [{"provider": "ninguno", "count": 0, "labels": "sin perfiles"}]

    panel(
        "AUTH HERMES",
        [
            f"activo    {overview['hermes_active'] or 'n/d'}",
            *[
                f"{row['provider']:<12} {row['count']} credencial(es) · {row['labels']}"
                for row in hermes_rows
            ],
        ],
    )
    panel(
        "AUTH OPENCLAW",
        [
            *[
                f"{row['provider']:<12} {row['count']} perfil(es) · {row['labels']}"
                for row in openclaw_rows
            ],
        ],
    )
    panel(
        "SEÑALES DE ENTORNO",
        [
            f"{row['provider']:<12} {status_badge('ready' if row['present'] else 'pending')}  {row['env']}"
            for row in overview['env_rows']
        ],
    )
    codex_alignment = overview.get("codex_alignment") or {}
    panel(
        "COHERENCIA OAUTH CODEX",
        [
            f"estado        {status_badge('ready' if codex_alignment.get('aligned') else 'warn')}  {codex_alignment.get('reason') or 'n/d'}",
            f"Hermes        {codex_alignment.get('hermes_email') or 'n/d'}",
            f"OpenClaw      {codex_alignment.get('openclaw_email') or 'n/d'}",
        ],
    )
    print("Uso:")
    print("  miliciano auth")
    print("  miliciano auth add hermes openrouter")
    print("  miliciano auth add hermes openrouter sk-tu-key")
    print("  miliciano auth add openclaw openai-codex")
    print("  miliciano auth remove hermes openrouter 1")
    print("  miliciano auth remove openclaw openai-codex")
    print("  miliciano auth reset hermes openrouter")
    print("  miliciano provider")
    print("  miliciano provider connect hermes openrouter sk-tu-key")
    print("  miliciano provider activate reasoning openai-codex/gpt-5.4")

def remove_openclaw_auth_profiles(target):
    auth = read_json_file(OPENCLAW_AUTH_PATH) or {}
    profiles = auth.get("profiles") or {}
    usage = auth.get("usageStats") or {}
    last_good = auth.get("lastGood") or {}
    matches = []
    for profile_id, entry in profiles.items():
        provider = entry.get("provider") or ""
        email = entry.get("email") or ""
        if target in {profile_id, provider, email}:
            matches.append(profile_id)

    if not matches:
        return 0

    for profile_id in matches:
        provider = (profiles.get(profile_id) or {}).get("provider")
        profiles.pop(profile_id, None)
        usage.pop(profile_id, None)
        if provider and last_good.get(provider) == profile_id:
            last_good.pop(provider, None)

    auth["profiles"] = profiles
    auth["usageStats"] = usage
    auth["lastGood"] = last_good
    write_json_file(OPENCLAW_AUTH_PATH, auth)
    return len(matches)

def add_openclaw_api_token(provider, token):
    import tempfile

    script = tempfile.NamedTemporaryFile("w", delete=False, suffix=".sh")
    try:
        script.write("#!/usr/bin/env bash\n")
        script.write(
            f"printf '%s\\n' {json.dumps(token)} | openclaw models auth paste-token --provider {provider}\n"
        )
        script.close()
        os.chmod(script.name, 0o700)
        run(["bash", script.name])
    finally:
        try:
            os.remove(script.name)
        except Exception:
            pass

def cmd_auth(args):
    banner()
    if not args or args[0] in {"status", "show", "list"}:
        print_auth_overview()
        return

    action = args[0].lower()
    if action == "add":
        if len(args) < 3:
            print("Uso: miliciano auth add <hermes|openclaw> <provider> [token/api-key]", file=sys.stderr)
            sys.exit(1)
        target = args[1].lower()
        provider = args[2]
        secret = args[3] if len(args) > 3 else None
        if target == "hermes":
            cmd = ["hermes", "auth", "add", provider]
            if secret:
                cmd.extend(["--type", "api-key", "--api-key", secret])
            rc = run(cmd).returncode
            if rc != 0:
                sys.exit(rc)
            print_auth_overview()
            return
        if target == "openclaw":
            if secret:
                rc = add_openclaw_api_token(provider, secret).returncode
            else:
                rc = run(["openclaw", "models", "auth", "login", "--provider", provider]).returncode
            if rc != 0:
                sys.exit(rc)
            print_auth_overview()
            return
        print(f"Destino de auth desconocido: {target}", file=sys.stderr)
        sys.exit(1)

    if action == "remove":
        if len(args) < 3:
            print("Uso: miliciano auth remove <hermes|openclaw> <provider|perfil> [target]", file=sys.stderr)
            sys.exit(1)
        target = args[1].lower()
        provider = args[2]
        if target == "hermes":
            if len(args) < 4:
                print("Uso: miliciano auth remove hermes <provider> <index|id|label>", file=sys.stderr)
                sys.exit(1)
            rc = run(["hermes", "auth", "remove", provider, args[3]]).returncode
            if rc != 0:
                sys.exit(rc)
            print_auth_overview()
            return
        if target == "openclaw":
            removed = remove_openclaw_auth_profiles(provider)
            if removed == 0:
                print("No encontré perfiles OpenClaw que coincidan.", file=sys.stderr)
                sys.exit(1)
            print(f"Eliminé {removed} perfil(es) de OpenClaw para {provider}")
            print_auth_overview()
            return
        print(f"Destino de auth desconocido: {target}", file=sys.stderr)
        sys.exit(1)

    if action == "reset":
        if len(args) != 3 or args[1].lower() != "hermes":
            print("Uso: miliciano auth reset hermes <provider>", file=sys.stderr)
            sys.exit(1)
        rc = run(["hermes", "auth", "reset", args[2]]).returncode
        if rc != 0:
            sys.exit(rc)
        print_auth_overview()
        return

    print(f"Acción de auth desconocida: {action}", file=sys.stderr)
    print("Usa: show | add | remove | reset", file=sys.stderr)
    sys.exit(1)

def cmd_provider(args):
    banner()
    if not args or args[0] in {"status", "show", "list"}:
        print_auth_overview()
        print_route_overview()
        return

    action = args[0].lower()
    if action in {"connect", "add"}:
        if len(args) < 3:
            print("Uso: miliciano provider connect <hermes|openclaw> <provider> [secret]", file=sys.stderr)
            sys.exit(1)
        cmd_auth(["add", args[1], args[2], *args[3:]])
        return
    if action in {"remove", "disconnect"}:
        if len(args) < 3:
            print("Uso: miliciano provider disconnect <hermes|openclaw> <provider> [target]", file=sys.stderr)
            sys.exit(1)
        cmd_auth(["remove", args[1], args[2], *args[3:]])
        return
    if action in {"activate", "use"}:
        if len(args) < 3:
            print("Uso: miliciano provider activate <reasoning|execution|fast|local|fallback> <provider/modelo|local>", file=sys.stderr)
            sys.exit(1)
        role = args[1]
        spec = " ".join(args[2:]).strip()
        set_route_target(role, spec)
        return
    if action == "reset":
        if len(args) != 3 or args[1].lower() != "hermes":
            print("Uso: miliciano provider reset hermes <provider>", file=sys.stderr)
            sys.exit(1)
        cmd_auth(["reset", args[1], args[2]])
        return

    print(f"Acción de provider desconocida: {action}", file=sys.stderr)
    print("Usa: show | connect | disconnect | activate | reset", file=sys.stderr)
    sys.exit(1)

def cmd_model(args):
    banner()
    if not args or args[0] in {"show", "status"}:
        print_model_overview()
        return

    target = args[0].lower()
    spec = " ".join(args[1:]).strip()
    if not spec:
        print("Falta modelo. Ejemplo: miliciano model hermes local", file=sys.stderr)
        sys.exit(1)

    if target == "hermes":
        set_hermes_model(spec)
        return
    if target == "openclaw":
        rc = set_openclaw_model(spec)
        if rc != 0:
            sys.exit(rc)
        return
    if target in {"all", "both"}:
        set_hermes_model(spec)
        rc = set_openclaw_model(spec)
        if rc != 0:
            sys.exit(rc)
        return
    if target == "nemoclaw":
        set_nemoclaw_model(spec)
        return

    print(f"Objetivo de modelo desconocido: {target}", file=sys.stderr)
    print("Usa: hermes | openclaw | all | nemoclaw", file=sys.stderr)
    sys.exit(1)


def cmd_mode(args):
    banner()
    if not args or args[0] in {"show", "status", "list"}:
        print_mode_overview()
        return

    if len(args) != 2:
        print("Uso: miliciano mode <output|route|permission> <valor>", file=sys.stderr)
        sys.exit(1)

    family = args[0].lower()
    value = args[1].strip().lower()
    try:
        if family == "output":
            set_output_mode(value)
        elif family == "route":
            set_route_mode(value)
        elif family == "permission":
            set_permission_mode(value)
        else:
            print(f"Familia de modo desconocida: {family}", file=sys.stderr)
            sys.exit(1)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print_mode_overview()


def print_identity_overview():
    identity = get_partner_identity()
    panel("IDENTIDAD DEL PARTNER", [
        f"nombre        {identity.get('partner_name') or 'Miliciano'}",
        f"persona       {identity.get('persona_key')}",
        f"tono          {(identity.get('persona') or {}).get('tone')}",
        f"estilo        {identity.get('interaction_style')}",
        f"idioma        {identity.get('language')}",
        f"operador      {identity.get('owner_name') or 'n/d'}",
    ])
    print("Milio-first: la identidad del partner define cómo responde Miliciano, sin depender de Hermes como interfaz principal.")
    print("Uso:")
    print("  miliciano identity")
    print("  miliciano identity set-name <nombre>")
    print("  miliciano identity set-persona <operator|guardian|builder|concierge>")
    print("  miliciano identity set-owner <nombre>")
    print("  miliciano identity set-style <estilo>")
    print("  miliciano identity set-language <es|en|...>")


def cmd_identity(args):
    banner()
    if not args or args[0] in {"show", "status", "list"}:
        print_identity_overview()
        return

    action = args[0].lower()
    if action == 'set-name':
        set_partner_identity(partner_name=' '.join(args[1:]).strip())
        print_identity_overview()
        return
    if action == 'set-persona':
        value = ' '.join(args[1:]).strip().lower()
        set_partner_identity(persona_key=value)
        print_identity_overview()
        return
    if action == 'set-owner':
        set_partner_identity(owner_name=' '.join(args[1:]).strip())
        print_identity_overview()
        return
    if action == 'set-style':
        set_partner_identity(interaction_style=' '.join(args[1:]).strip())
        print_identity_overview()
        return
    if action == 'set-language':
        set_partner_identity(language=' '.join(args[1:]).strip())
        print_identity_overview()
        return

    print(f"Acción de identity desconocida: {action}", file=sys.stderr)
    print("Usa: show | set-name | set-persona | set-owner | set-style | set-language", file=sys.stderr)
    sys.exit(1)

