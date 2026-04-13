"""Tests for reasoning payload transport."""

from types import SimpleNamespace

import pytest


class TestReasoningTransport:
    @pytest.mark.unit
    def test_build_reasoning_payload_includes_preamble_route_and_prompt(self):
        from miliciano_agent import build_reasoning_payload

        route = {
            "role": "reasoning",
            "spec": "openai-codex/gpt-5.4",
            "reason": "por defecto uso la ruta principal remota",
        }

        payload = build_reasoning_payload("hola", route)

        assert "Usuario: hola" in payload["payload"]
        assert "Ruta seleccionada: reasoning (openai-codex/gpt-5.4)." in payload["payload"]
        assert payload["payload_chars"] == len(payload["payload"])
        assert payload["payload_words"] > 0

    @pytest.mark.unit
    def test_run_reasoning_is_stateless_by_default(self, monkeypatch):
        from miliciano_agent import run_reasoning

        captured = {}

        monkeypatch.setattr("miliciano_agent.load_miliciano_state", lambda: {"routing": {"fallback": None}})
        monkeypatch.setattr(
            "miliciano_agent.resolve_hermes_route_for_prompt",
            lambda prompt, forced_role=None: {
                "role": forced_role or "reasoning",
                "provider": "openai-codex",
                "model": "gpt-5.4",
                "spec": "openai-codex/gpt-5.4",
                "reason": "ruta de prueba",
            },
        )
        monkeypatch.setattr("miliciano_agent.need", lambda cmd: None)
        monkeypatch.setattr("miliciano_agent._announce_action", lambda message, detail=None: None)
        monkeypatch.setattr("miliciano_agent._save_memory", lambda *args, **kwargs: None)

        def fake_run_with_spinner(cmd, label):
            captured["cmd"] = cmd
            return SimpleNamespace(returncode=0, stdout="respuesta final")

        monkeypatch.setattr("miliciano_agent.run_with_spinner", fake_run_with_spinner)

        rc, result = run_reasoning("hola", forced_role="reasoning", save_memory=False)

        assert rc == 0
        assert "--resume" not in captured["cmd"]
        assert result["transport_mode"] == "stateless"
        assert result["payload_chars"] > len("hola")
