"""Tests for interactive shell mode controls."""

import pytest


class TestShellModes:
    @pytest.mark.unit
    def test_cycle_shell_mode_wraps_with_shift_tab(self):
        from miliciano_shell_input import cycle_shell_mode

        assert cycle_shell_mode("reasoning") == "plan"
        assert cycle_shell_mode("plan") == "unrestricted"
        assert cycle_shell_mode("unrestricted") == "reasoning"

    @pytest.mark.unit
    def test_parse_shell_command_updates_mode(self):
        from miliciano_shell_input import parse_shell_command

        result = parse_shell_command("/mode plan", current_mode="reasoning")

        assert result["kind"] == "mode"
        assert result["mode"] == "plan"
        assert "plan" in result["message"].lower()

    @pytest.mark.unit
    def test_parse_shell_command_rejects_unknown_mode(self):
        from miliciano_shell_input import parse_shell_command

        result = parse_shell_command("/mode dragon", current_mode="reasoning")

        assert result["kind"] == "error"
        assert "modo" in result["message"].lower()

    @pytest.mark.unit
    def test_parse_shell_command_maps_plan_shortcut(self):
        from miliciano_shell_input import parse_shell_command

        result = parse_shell_command("/plan diseña login", current_mode="reasoning")

        assert result["kind"] == "prompt"
        assert result["mode"] == "plan"
        assert result["prompt"] == "diseña login"

    @pytest.mark.unit
    def test_prompt_label_includes_current_mode(self):
        from miliciano_shell_input import prompt_label

        assert prompt_label("reasoning") == "miliciano[reasoning] » "

    @pytest.mark.unit
    def test_shell_toolbar_text_mentions_supported_shortcuts(self):
        from miliciano_shell_input import shell_toolbar_text

        text = shell_toolbar_text("plan", flash_message="Modo activo: plan")

        assert "PLAN" in text
        assert "objetivo, contexto y restricciones" in text.lower()
        assert "Shift+Tab" in text
        assert "Ctrl+T" in text
        assert "Alt+M" in text
        assert "Esc+Enter" in text
        assert "Modo activo: plan" in text

    @pytest.mark.unit
    def test_prompt_toolkit_error_is_actionable(self):
        from miliciano_shell_input import _prompt_toolkit_error

        message = _prompt_toolkit_error()

        assert "ui avanzada" in message.lower()
        assert "modo básico" in message.lower()

    @pytest.mark.unit
    def test_shell_runtime_status_reports_basic_fallback_when_prompt_toolkit_missing(self, monkeypatch):
        import miliciano_shell_input

        monkeypatch.setattr(
            miliciano_shell_input,
            "missing_shell_python_dependencies",
            lambda: [{"module": "prompt_toolkit", "package": "prompt_toolkit>=3.0.43"}],
        )
        monkeypatch.setattr(
            miliciano_shell_input,
            "missing_optional_runtime_python_dependencies",
            lambda: [],
        )

        status = miliciano_shell_input.shell_runtime_status()

        assert status["available"] is True
        assert "prompt_toolkit" in status["missing_modules"]
        assert "modo básico" in status["detail"].lower()
        assert "ui avanzada" in status["action"].lower()

    @pytest.mark.unit
    def test_shell_runtime_status_reports_optional_security_extras(self, monkeypatch):
        import miliciano_shell_input

        monkeypatch.setattr(miliciano_shell_input, "missing_shell_python_dependencies", lambda: [])
        monkeypatch.setattr(
            miliciano_shell_input,
            "missing_optional_runtime_python_dependencies",
            lambda: [{"module": "keyring", "package": "keyring>=24.0.0"}],
        )

        status = miliciano_shell_input.shell_runtime_status()

        assert status["available"] is True
        assert "seguridad" in status["detail"].lower()
        assert "miliciano setup" in status["action"]

    @pytest.mark.unit
    def test_setup_support_short_circuits_when_optional_security_extras_exist(self, monkeypatch):
        import miliciano_setup_support

        monkeypatch.setattr(
            miliciano_setup_support.importlib.util,
            "find_spec",
            lambda name: object(),
        )

        def fail_run(*args, **kwargs):
            raise AssertionError("run() no debería ejecutarse si prompt_toolkit ya existe")

        monkeypatch.setattr(miliciano_setup_support, "run", fail_run)

        result = miliciano_setup_support.ensure_runtime_python_dependencies()

        assert result["ok"] is True
        assert "Extras opcionales de seguridad listos" in result["detail"]

    @pytest.mark.unit
    def test_setup_support_detects_missing_optional_extras_without_install_when_requested(self, monkeypatch):
        import miliciano_setup_support

        monkeypatch.setattr(
            miliciano_setup_support.importlib.util,
            "find_spec",
            lambda name: None if name == "keyring" else object(),
        )

        def fail_run(*args, **kwargs):
            raise AssertionError("run() no debería ejecutarse en modo detección")

        monkeypatch.setattr(miliciano_setup_support, "run", fail_run)

        result = miliciano_setup_support.ensure_runtime_python_dependencies(auto_install=False)

        assert result["ok"] is False
        assert result["missing_modules"] == ["keyring"]
        assert "keyring" in result["detail"]

    @pytest.mark.unit
    def test_python_system_prereq_status_reports_missing_debian_runtime_bits(self, monkeypatch):
        import miliciano_setup_support

        monkeypatch.setattr(
            miliciano_setup_support,
            "read_os_release",
            lambda: {"ID": "ubuntu", "ID_LIKE": "debian"},
        )
        monkeypatch.setattr(
            miliciano_setup_support.importlib.util,
            "find_spec",
            lambda name: None if name in {"venv", "ensurepip"} else object(),
        )
        monkeypatch.setattr(
            miliciano_setup_support,
            "run",
            lambda *args, **kwargs: type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
        )

        status = miliciano_setup_support.python_system_prereq_status()

        assert status["ok"] is False
        assert status["debian_like"] is True
        assert status["missing"] == ["pip", "venv", "ensurepip"]
        assert "python3-pip python3-venv" in status["detail"]

    @pytest.mark.unit
    def test_ensure_python_system_prereqs_dry_run_does_not_install(self, monkeypatch):
        import miliciano_setup_support

        monkeypatch.setattr(
            miliciano_setup_support,
            "python_system_prereq_status",
            lambda: {
                "ok": False,
                "missing": ["pip"],
                "debian_like": True,
                "packages": ["python3-pip", "python3-venv"],
                "detail": "faltan componentes",
            },
        )

        result = miliciano_setup_support.ensure_python_system_prereqs(auto_install=True, dry_run=True)

        assert result["ok"] is False
        assert result["detail"].startswith("[dry-run]")

    @pytest.mark.unit
    def test_read_shell_line_falls_back_to_builtin_input_when_prompt_toolkit_missing(self, monkeypatch):
        import miliciano_shell_input

        monkeypatch.setattr(miliciano_shell_input.os, "isatty", lambda fd: True)
        monkeypatch.setattr(miliciano_shell_input, "prompt_toolkit_available", lambda: False)
        monkeypatch.setattr("builtins.input", lambda prompt="": "/plan define rollout")

        prompt, mode = miliciano_shell_input.read_shell_line("reasoning")

        assert prompt == "/plan define rollout"
        assert mode == "reasoning"

    @pytest.mark.unit
    def test_right_prompt_changes_by_mode(self):
        from miliciano_shell_input import _right_prompt

        assert _right_prompt("plan") == "editor de trabajo"
        assert _right_prompt("unrestricted") == "libre"
        assert _right_prompt("reasoning") == "stateless"
