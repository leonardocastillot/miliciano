"""Tests for persisted state preferences."""

import pytest


class TestStatePreferences:
    @pytest.mark.unit
    def test_default_state_includes_tactical_response_style(self):
        from miliciano_state import default_miliciano_state

        state = default_miliciano_state()

        assert state["preferences"]["response_style"] == "tactical_markdown"

    @pytest.mark.unit
    def test_loaded_state_backfills_response_style(self, temp_config_dir):
        from miliciano_state import load_miliciano_state

        state = load_miliciano_state(refresh=True)

        assert state["preferences"]["response_style"] == "tactical_markdown"
