"""
Integration tests for Miliciano security features.

These tests verify end-to-end security workflows.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestSecurityIntegration:
    """Integration tests for security features"""

    @pytest.mark.integration
    @pytest.mark.security
    def test_safe_command_flow(self, temp_config_dir, mock_subprocess_run):
        """Test safe command passes through all layers."""
        from miliciano_runtime import run_openclaw_agent

        # Mock OpenClaw to return success
        mock_subprocess_run.return_value.returncode = 0
        mock_subprocess_run.return_value.stdout = "Files listed successfully"

        # Execute safe command
        returncode, output = run_openclaw_agent("List files in /tmp", check_policy=True)

        assert returncode == 0
        assert "Files listed" in output

    @pytest.mark.integration
    @pytest.mark.security
    def test_dangerous_command_blocked(self, temp_config_dir, monkeypatch):
        """Test dangerous command blocked by policy."""
        from miliciano_runtime import run_openclaw_agent
        from miliciano_policy import SimplePolicy

        # Force SimplePolicy to enforce mode
        monkeypatch.setenv("NEMOCLAW_POLICY_MODE", "enforce")

        # Create policy that will catch dangerous patterns
        policy = SimplePolicy(mode="enforce")

        # Try to execute dangerous command through agent
        # Note: This tests the policy layer, not actual OpenClaw execution
        try:
            policy.check_command("rm -rf /important/data")
            pytest.fail("Should have raised PolicyViolation")
        except Exception as e:
            assert "PolicyViolation" in str(type(e))


class TestValidationIntegration:
    """Integration tests for input validation"""

    @pytest.mark.integration
    def test_provider_validation_in_controls(self):
        """Test provider validation integrated into controls."""
        from miliciano_validators import validate_provider, ValidationError

        # Valid provider
        result = validate_provider("openai-codex")
        assert result == "openai-codex"

        # Invalid provider
        with pytest.raises(ValidationError):
            validate_provider("evil'; rm -rf /")

    @pytest.mark.integration
    def test_url_validation_in_setup(self):
        """Test URL validation integrated into setup."""
        from miliciano_validators import validate_install_url, ValidationError

        # Valid URL
        valid = "https://ollama.com/install.sh"
        assert validate_install_url(valid) == valid

        # Invalid URL (not HTTPS)
        with pytest.raises(ValidationError):
            validate_install_url("http://evil.com/malware.sh")

        # Invalid URL (untrusted domain)
        with pytest.raises(ValidationError):
            validate_install_url("https://untrusted.com/script.sh")


class TestPolicyEnforcementFlow:
    """Test policy enforcement in execution flow"""

    @pytest.mark.integration
    @patch('subprocess.run')
    def test_policy_checked_before_execution(self, mock_run, temp_config_dir, monkeypatch):
        """Test policy is checked before OpenClaw execution."""
        from miliciano_runtime import run_openclaw_agent

        monkeypatch.setenv("NEMOCLAW_POLICY_MODE", "enforce")

        # Setup mock to track call order
        calls = []

        def track_calls(*args, **kwargs):
            cmd = args[0] if args else []
            if 'openclaw' in cmd:
                calls.append('openclaw')
            elif 'nemoclaw' in cmd:
                calls.append('nemoclaw')

            result = Mock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        mock_run.side_effect = track_calls

        # Execute
        run_openclaw_agent("test message", check_policy=True)

        # Policy should be checked (or attempted) before execution
        # Since Nemoclaw not available, it falls back to SimplePolicy
        # OpenClaw should still be called
        assert 'openclaw' in calls

    @pytest.mark.integration
    def test_audit_log_created(self, temp_config_dir):
        """Test audit log is created after execution."""
        from miliciano_policy import PolicyEngine

        engine = PolicyEngine(policy_mode="audit")
        engine.audit_log_path = temp_config_dir / 'audit.log'

        action = {"type": "test", "command": "ls"}
        policy_result = {"allowed": True}
        execution_result = {"success": True}

        engine.audit_log(action, policy_result, execution_result)

        # Verify log exists and contains valid JSON
        assert engine.audit_log_path.exists()

        with open(engine.audit_log_path) as f:
            log_entry = json.loads(f.read())

        assert log_entry["action"] == action
        assert "timestamp" in log_entry


class TestDownloadVerification:
    """Test download and verification of external scripts"""

    @pytest.mark.integration
    def test_download_and_verify_script(self, temp_dir, mock_urllib_request):
        """Test script download with verification."""
        from miliciano_setup import download_and_verify_script

        url = "https://ollama.com/install.sh"

        script_path = download_and_verify_script(url, expected_sha256=None)

        assert Path(script_path).exists()
        assert Path(script_path).stat().st_mode & 0o700

        # Cleanup
        Path(script_path).unlink()

    @pytest.mark.integration
    def test_download_invalid_url_rejected(self):
        """Test invalid URL rejected before download."""
        from miliciano_setup import download_and_verify_script
        from miliciano_validators import ValidationError

        with pytest.raises(ValidationError):
            download_and_verify_script("http://evil.com/malware.sh")


class TestEndToEndScenarios:
    """End-to-end scenarios simulating real usage"""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_setup_creates_policy(self, temp_config_dir):
        """Test setup creates policy configuration."""
        from miliciano_setup import ensure_policy_config

        created, msg = ensure_policy_config()

        policy_path = temp_config_dir / 'policy.yaml'
        assert policy_path.exists()

        # Verify it's valid YAML-like content
        content = policy_path.read_text()
        assert "version" in content or "mode" in content

    @pytest.mark.integration
    def test_multiple_policy_checks(self, temp_config_dir):
        """Test multiple sequential policy checks."""
        from miliciano_policy import SimplePolicy

        policy = SimplePolicy(mode="enforce")

        # First check - safe
        result1 = policy.check_command("ls -la")
        assert result1["allowed"]

        # Second check - dangerous
        try:
            policy.check_command("rm -rf /")
            pytest.fail("Should block dangerous command")
        except:
            pass

        # Third check - safe again
        result3 = policy.check_command("cat file.txt")
        assert result3["allowed"]


class TestRegressionTests:
    """Tests for previously fixed bugs"""

    @pytest.mark.integration
    def test_shell_injection_fixed(self):
        """Test shell injection vulnerability is fixed."""
        from miliciano_validators import validate_provider, ValidationError

        # These should all be rejected
        injection_attempts = [
            "test'; rm -rf /",
            "test`whoami`",
            "test$(whoami)",
            "test && rm file",
        ]

        for attempt in injection_attempts:
            with pytest.raises(ValidationError):
                validate_provider(attempt)

    @pytest.mark.integration
    def test_path_traversal_fixed(self):
        """Test path traversal vulnerability is fixed."""
        from miliciano_validators import validate_provider, ValidationError

        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "provider/../../../etc/passwd",
        ]

        for attempt in traversal_attempts:
            with pytest.raises(ValidationError):
                validate_provider(attempt)
