"""Regression tests for NVIDIA provider wiring."""

from pathlib import Path

import pytest


def _patch_nvidia_paths(monkeypatch, temp_dir):
    import miliciano_state

    config_dir = temp_dir / ".config" / "miliciano"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(miliciano_state, "MILICIANO_STATE_PATH", str(config_dir / "config.json"))
    monkeypatch.setattr(miliciano_state, "MILICIANO_SECRETS_PATH", str(config_dir / "secrets.json"))
    monkeypatch.setattr(miliciano_state, "_STATE_CACHE", None)
    monkeypatch.setattr(miliciano_state, "preferred_local_ollama_model", lambda: None)
    return config_dir


class TestNvidiaValidation:
    @pytest.mark.unit
    def test_validate_api_key_accepts_nvidia_prefix(self):
        from miliciano_validators import validate_api_key

        key = "nvapi-" + "a" * 40
        assert validate_api_key(key, provider="nvidia") == key

    @pytest.mark.unit
    def test_validate_api_key_rejects_invalid_nvidia_prefix(self):
        from miliciano_validators import ValidationError, validate_api_key

        with pytest.raises(ValidationError, match="nvapi-"):
            validate_api_key("sk-" + "a" * 40, provider="nvidia")


class TestNvidiaState:
    @pytest.mark.unit
    def test_collect_nvidia_status_reads_local_secret_and_migrates_model(self, monkeypatch, temp_dir):
        import miliciano_state

        config_dir = _patch_nvidia_paths(monkeypatch, temp_dir)
        miliciano_state.write_json_file(
            str(config_dir / "config.json"),
            {
                "nvidia": {
                    "enabled": True,
                    "api_key_present": False,
                    "base_url": "https://integrate.api.nvidia.com/v1",
                    "model": "nvidia/llama-3.1-nemotron-70b-instruct",
                },
                "routing": {
                    "fallback": "nvidia/llama-3.1-nemotron-70b-instruct",
                },
            },
        )
        miliciano_state.set_nvidia_api_key("nvapi-" + "b" * 40)
        status = miliciano_state.collect_nvidia_status()

        assert status["api_key_present"] is True
        assert status["credential_source"] == "local"
        assert status["model"] == "nvidia/llama-3.3-nemotron-super-49b-v1.5"

    @pytest.mark.unit
    def test_connect_and_disconnect_nvidia_provider_manage_local_secret(self, monkeypatch, temp_dir):
        import miliciano_control_support
        import miliciano_state

        config_dir = _patch_nvidia_paths(monkeypatch, temp_dir)
        monkeypatch.setattr(miliciano_control_support, "load_miliciano_state", miliciano_state.load_miliciano_state)
        monkeypatch.setattr(miliciano_control_support, "save_miliciano_state", miliciano_state.save_miliciano_state)
        monkeypatch.setattr(miliciano_control_support, "collect_nvidia_status", miliciano_state.collect_nvidia_status)
        monkeypatch.setattr(miliciano_control_support, "set_nvidia_api_key", miliciano_state.set_nvidia_api_key)
        monkeypatch.setattr(miliciano_control_support, "clear_nvidia_api_key", miliciano_state.clear_nvidia_api_key)
        monkeypatch.setattr(miliciano_control_support, "get_nvidia_api_key", miliciano_state.get_nvidia_api_key)

        miliciano_control_support.connect_nvidia_provider("nvapi-" + "c" * 40)
        secret_path = Path(config_dir / "secrets.json")
        assert secret_path.exists()
        status = miliciano_state.collect_nvidia_status()
        assert status["api_key_present"] is True
        assert status["credential_source"] == "local"

        miliciano_control_support.disconnect_nvidia_provider()
        status = miliciano_state.collect_nvidia_status()
        assert status["api_key_present"] is False
        assert status["credential_source"] == "missing"
