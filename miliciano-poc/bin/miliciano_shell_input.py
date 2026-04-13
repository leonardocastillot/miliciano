#!/usr/bin/env python3
import importlib
import os
from functools import lru_cache

from miliciano_setup_support import (
    missing_optional_runtime_python_dependencies,
    missing_shell_python_dependencies,
    runtime_python_install_command,
)
from miliciano_state import load_miliciano_state, save_miliciano_state

SHELL_MODES = ("reasoning", "plan", "unrestricted")
MODE_LABELS = {
    "reasoning": "Razona",
    "plan": "Plan",
    "unrestricted": "Libre",
}
HELP_TEXT = (
    "Shift+Tab/Ctrl+T/Alt+M cambia modo · Enter envía · Esc+Enter agrega línea · "
    "/mode <reasoning|plan|unrestricted> · /exec · /mission · /fast · /clear · /exit"
)
SHELL_HISTORY_PATH = os.path.expanduser("~/.config/miliciano/shell_history")
MODE_PROMPT_HINTS = {
    "reasoning": "Analiza, depura o compara. Enter envía.",
    "plan": "Escribe objetivo, contexto y restricciones. Esc+Enter agrega líneas.",
    "unrestricted": "Modo libre. Menos estructura, mismo historial.",
}
SHELL_COMMANDS = [
    "/help",
    "/modes",
    "/mode reasoning",
    "/mode plan",
    "/mode unrestricted",
    "/cycle",
    "/clear",
    "/reasoning ",
    "/plan ",
    "/unrestricted ",
    "/fast ",
    "/exec ",
    "/mission ",
    "/exit",
]


def normalize_shell_mode(mode):
    value = (mode or "").strip().lower()
    return value if value in SHELL_MODES else "reasoning"


def cycle_shell_mode(current_mode):
    mode = normalize_shell_mode(current_mode)
    idx = SHELL_MODES.index(mode)
    return SHELL_MODES[(idx + 1) % len(SHELL_MODES)]


def load_shell_mode():
    state = load_miliciano_state()
    preferences = state.setdefault("preferences", {})
    mode = normalize_shell_mode(preferences.get("shell_mode"))
    if preferences.get("shell_mode") != mode:
        preferences["shell_mode"] = mode
        save_miliciano_state(state)
    return mode


def save_shell_mode(mode):
    normalized = normalize_shell_mode(mode)
    state = load_miliciano_state()
    state.setdefault("preferences", {})["shell_mode"] = normalized
    save_miliciano_state(state)
    return normalized


def prompt_label(mode):
    normalized = normalize_shell_mode(mode)
    return f"miliciano[{normalized}] » "


def parse_shell_command(text, current_mode="reasoning"):
    raw = (text or "").strip()
    mode = normalize_shell_mode(current_mode)
    if not raw:
        return {"kind": "empty", "mode": mode}
    if raw in {"/exit", "/quit"}:
        return {"kind": "exit", "mode": mode}
    if raw == "/clear":
        return {"kind": "clear", "mode": mode}
    if raw in {"/help", "/modes"}:
        return {"kind": "info", "mode": mode, "message": HELP_TEXT}
    if raw in {"/cycle", "/next-mode"}:
        next_mode = cycle_shell_mode(mode)
        return {"kind": "mode", "mode": next_mode, "message": f"Modo activo: {next_mode}"}
    if raw.startswith("/mode "):
        requested = normalize_shell_mode(raw.split(None, 1)[1])
        if requested == "reasoning" and raw.split(None, 1)[1].strip().lower() not in SHELL_MODES:
            return {"kind": "error", "mode": mode, "message": "Modo inválido. Usa reasoning, plan o unrestricted."}
        return {"kind": "mode", "mode": requested, "message": f"Modo activo: {requested}"}
    if raw.startswith("/reasoning "):
        return {"kind": "prompt", "mode": "reasoning", "prompt": raw[11:].strip()}
    if raw.startswith("/fast "):
        return {"kind": "prompt", "mode": "fast", "prompt": raw[6:].strip()}
    if raw.startswith("/exec "):
        return {"kind": "prompt", "mode": "exec", "prompt": raw[6:].strip()}
    if raw.startswith("/mission "):
        return {"kind": "prompt", "mode": "mission", "prompt": raw[9:].strip()}
    if raw.startswith("/plan "):
        return {"kind": "prompt", "mode": "plan", "prompt": raw[6:].strip()}
    if raw.startswith("/unrestricted "):
        return {"kind": "prompt", "mode": "unrestricted", "prompt": raw[14:].strip()}
    return {"kind": "prompt", "mode": mode, "prompt": raw}


def shell_toolbar_text(mode, flash_message=None):
    normalized = normalize_shell_mode(mode).upper()
    parts = [
        f"modo {normalized}",
        "motor Hermes/OpenClaw",
        MODE_PROMPT_HINTS.get(normalize_shell_mode(mode), "Editor táctico"),
        "Enter envía",
        "Esc+Enter agrega línea",
        "Shift+Tab Ctrl+T Alt+M cambia modo",
        "/help atajos",
    ]
    if flash_message:
        parts.append(flash_message)
    return "  |  ".join(parts)


def _prompt_toolkit_error():
    missing = missing_shell_python_dependencies()
    missing_modules = ", ".join(dependency["module"] for dependency in missing) or "prompt_toolkit"
    return (
        f"UI avanzada del shell no disponible: {missing_modules}. "
        "Miliciano seguirá funcionando en modo básico usando el prompt integrado."
    )


def prompt_toolkit_available():
    return not missing_shell_python_dependencies()


def shell_runtime_status():
    shell_missing = missing_shell_python_dependencies()
    optional_missing = missing_optional_runtime_python_dependencies()
    if not shell_missing and not optional_missing:
        return {
            "available": True,
            "missing_modules": [],
            "detail": "Shell interactivo completo disponible; extras opcionales de seguridad presentes",
            "action": "",
        }
    if shell_missing:
        missing_modules = [dependency["module"] for dependency in shell_missing]
        detail = f"Shell interactivo disponible en modo básico; faltan módulos de UI avanzada: {', '.join(missing_modules)}"
        action = _prompt_toolkit_error()
    else:
        missing_modules = []
        detail = "Shell interactivo completo disponible"
        action = ""
    if optional_missing:
        optional_modules = [dependency["module"] for dependency in optional_missing]
        detail = (
            f"{detail}; extras opcionales de seguridad pendientes: "
            + ", ".join(optional_modules)
        )
        action = (
            "Opcional: ejecuta `miliciano setup` o instala manualmente con "
            + "`"
            + " ".join(
                f'"{part}"' if " " in part else part
                for part in runtime_python_install_command(optional_missing)
            )
            + "`."
        )
    return {
        "available": True,
        "missing_modules": missing_modules,
        "detail": detail,
        "action": action,
    }


def _load_prompt_toolkit():
    try:
        return {
            "PromptSession": importlib.import_module("prompt_toolkit").PromptSession,
            "AutoSuggestFromHistory": importlib.import_module("prompt_toolkit.auto_suggest").AutoSuggestFromHistory,
            "WordCompleter": importlib.import_module("prompt_toolkit.completion").WordCompleter,
            "FormattedText": importlib.import_module("prompt_toolkit.formatted_text").FormattedText,
            "FileHistory": importlib.import_module("prompt_toolkit.history").FileHistory,
            "KeyBindings": importlib.import_module("prompt_toolkit.key_binding").KeyBindings,
            "Style": importlib.import_module("prompt_toolkit.styles").Style,
        }
    except ImportError as exc:
        raise RuntimeError(_prompt_toolkit_error()) from exc


@lru_cache(maxsize=1)
def _build_shell_style():
    modules = _load_prompt_toolkit()
    return modules["Style"].from_dict(
        {
            "prompt": "bold ansimagenta",
            "mode": "bold ansiyellow",
            "continuation": "ansimagenta",
            "toolbar": "bg:#2a233d #f2e9ff",
            "toolbar.label": "bold #f6c177",
            "toolbar.mode": "bold #ffdd57",
            "toolbar.value": "#e0def4",
            "toolbar.hint": "italic #c4a7e7",
            "toolbar.modehint": "bold #9ccfd8",
            "toolbar.flash": "bold #9ccfd8",
            "rprompt": "italic ansibrightblack",
        }
    )


@lru_cache(maxsize=1)
def _get_prompt_session():
    modules = _load_prompt_toolkit()
    os.makedirs(os.path.dirname(SHELL_HISTORY_PATH), exist_ok=True)
    return modules["PromptSession"](
        history=modules["FileHistory"](SHELL_HISTORY_PATH),
        auto_suggest=modules["AutoSuggestFromHistory"](),
        completer=modules["WordCompleter"](SHELL_COMMANDS, sentence=True, match_middle=True),
        complete_while_typing=True,
        style=_build_shell_style(),
        multiline=True,
    )


def _prompt_fragments(mode, formatted_text_cls):
    normalized = normalize_shell_mode(mode)
    return formatted_text_cls(
        [
            ("class:prompt", "miliciano"),
            ("", "["),
            ("class:mode", normalized),
            ("", "] » "),
        ]
    )


def _continuation_fragments(width, line_number, wrap_count, formatted_text_cls):
    return formatted_text_cls([("class:continuation", "… ".rjust(width))])


def _toolbar_fragments(mode, flash_message, formatted_text_cls):
    normalized_mode = normalize_shell_mode(mode)
    normalized = normalized_mode.upper()
    fragments = [
        ("class:toolbar.label", " modo "),
        ("class:toolbar.mode", f" {normalized} "),
        ("class:toolbar", "  "),
        ("class:toolbar.label", " motor "),
        ("class:toolbar.value", " Hermes/OpenClaw "),
        ("class:toolbar", "  "),
        ("class:toolbar.modehint", f" {MODE_PROMPT_HINTS.get(normalized_mode, 'Editor táctico')} "),
        ("class:toolbar", "  "),
        ("class:toolbar.hint", " Enter envía "),
        ("class:toolbar", "  "),
        ("class:toolbar.hint", " Esc+Enter agrega línea "),
        ("class:toolbar", "  "),
        ("class:toolbar.hint", " Shift+Tab Ctrl+T Alt+M cambia modo "),
    ]
    if flash_message:
        fragments.extend([("class:toolbar", "  "), ("class:toolbar.flash", f" {flash_message} ")])
    return formatted_text_cls(fragments)


def _build_key_bindings(mode_state):
    modules = _load_prompt_toolkit()
    key_bindings = modules["KeyBindings"]()

    def cycle(event):
        mode_state["mode"] = cycle_shell_mode(mode_state["mode"])
        mode_state["flash"] = f"Modo activo: {mode_state['mode']}"
        event.app.invalidate()

    @key_bindings.add("c-t")
    def _ctrl_t(event):
        cycle(event)

    @key_bindings.add("s-tab")
    def _shift_tab(event):
        cycle(event)

    @key_bindings.add("escape", "m")
    def _alt_m(event):
        cycle(event)

    @key_bindings.add("escape", "enter")
    def _newline(event):
        mode_state["flash"] = "Nueva línea"
        event.current_buffer.insert_text("\n")
        event.app.invalidate()

    @key_bindings.add("c-j")
    def _submit_ctrl_j(event):
        event.current_buffer.validate_and_handle()

    @key_bindings.add("c-l")
    def _clear_screen(event):
        event.app.renderer.clear()
        event.app.invalidate()

    return key_bindings


def _right_prompt(mode):
    normalized = normalize_shell_mode(mode)
    if normalized == "plan":
        return "editor de trabajo"
    if normalized == "unrestricted":
        return "libre"
    return "stateless"


def read_shell_line(current_mode):
    mode = normalize_shell_mode(current_mode)
    if not os.isatty(0) or not os.isatty(1):
        return input(prompt_label(mode)), mode
    if not prompt_toolkit_available():
        return input(prompt_label(mode)), mode

    modules = _load_prompt_toolkit()
    session = _get_prompt_session()
    mode_state = {"mode": mode, "flash": None}

    try:
        prompt = session.prompt(
            _prompt_fragments(mode_state["mode"], modules["FormattedText"]),
            key_bindings=_build_key_bindings(mode_state),
            rprompt=lambda: modules["FormattedText"]([("class:rprompt", _right_prompt(mode_state["mode"]))]),
            bottom_toolbar=lambda: _toolbar_fragments(
                mode_state["mode"],
                mode_state["flash"],
                modules["FormattedText"],
            ),
            prompt_continuation=lambda width, line_number, wrap_count: _continuation_fragments(
                width,
                line_number,
                wrap_count,
                modules["FormattedText"],
            ),
        )
    except EOFError:
        raise
    except KeyboardInterrupt:
        raise

    return prompt, mode_state["mode"]
