"""
Pytest fixtures for Miliciano test suite.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

# Add miliciano-poc/bin to Python path for imports
MILICIANO_BIN = Path(__file__).parent.parent / 'miliciano-poc' / 'bin'
sys.path.insert(0, str(MILICIANO_BIN))


@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_dir(temp_dir, monkeypatch):
    """Create temporary config directory and set HOME."""
    config_dir = temp_dir / '.config' / 'miliciano'
    config_dir.mkdir(parents=True)

    # Set HOME to temp dir
    monkeypatch.setenv('HOME', str(temp_dir))

    yield config_dir


@pytest.fixture
def sample_config():
    """Sample valid Miliciano configuration."""
    return {
        "hermes": {
            "provider": "openai-codex",
            "model": "gpt-4"
        },
        "openclaw": {
            "model": "openai-codex/gpt-4"
        },
        "nemoclaw": {
            "model": None
        },
        "routing": {
            "reasoning": "openai-codex/gpt-4",
            "execution": "openai-codex/gpt-4",
            "fast": "custom/qwen2.5:3b",
            "local": "custom/qwen2.5:3b",
            "fallback": "openai-codex/gpt-4"
        }
    }


@pytest.fixture
def mock_subprocess_run(monkeypatch):
    """Mock subprocess.run to avoid actual command execution."""
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    mock_run = Mock(return_value=mock_result)

    import subprocess
    monkeypatch.setattr(subprocess, 'run', mock_run)

    return mock_run


@pytest.fixture
def mock_hermes(mock_subprocess_run):
    """Mock Hermes CLI responses."""
    mock_subprocess_run.return_value.stdout = "Mock Hermes response"
    mock_subprocess_run.return_value.returncode = 0
    return mock_subprocess_run


@pytest.fixture
def mock_openclaw(mock_subprocess_run):
    """Mock OpenClaw CLI responses."""
    mock_subprocess_run.return_value.stdout = "Mock OpenClaw response"
    mock_subprocess_run.return_value.returncode = 0
    return mock_subprocess_run


@pytest.fixture
def mock_nemoclaw(mock_subprocess_run):
    """Mock Nemoclaw CLI responses."""
    def side_effect(*args, **kwargs):
        cmd = args[0] if args else kwargs.get('args', [])

        result = Mock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""

        if 'status' in cmd:
            result.returncode = 0
        elif 'policy' in cmd and 'check' in cmd:
            result.stdout = json.dumps({
                "allowed": True,
                "reason": "test_policy_passed"
            })

        return result

    mock_subprocess_run.side_effect = side_effect
    return mock_subprocess_run


@pytest.fixture
def policy_config_simple():
    """Simple policy configuration for testing."""
    return {
        "version": "1.0",
        "mode": "enforce",
        "blocked_commands": [
            {
                "pattern": r"\brm\s+-rf\b",
                "description": "Recursive deletion",
                "risk": "critical"
            }
        ],
        "audit": {
            "enabled": True,
            "log_path": "~/.config/miliciano/audit.log"
        }
    }


@pytest.fixture
def sample_action():
    """Sample action descriptor for policy testing."""
    return {
        "type": "openclaw_agent",
        "agent": "main",
        "message": "List files in /tmp",
        "timestamp": "2026-04-10T20:00:00Z"
    }


@pytest.fixture
def dangerous_action():
    """Dangerous action for policy testing."""
    return {
        "type": "shell_command",
        "command": "rm -rf /",
        "timestamp": "2026-04-10T20:00:00Z"
    }


@pytest.fixture
def audit_log_path(temp_config_dir):
    """Path to temporary audit log."""
    return temp_config_dir / 'audit.log'


@pytest.fixture
def cleanup_audit_log(audit_log_path):
    """Clean up audit log after test."""
    yield
    if audit_log_path.exists():
        audit_log_path.unlink()


@pytest.fixture
def mock_keyring(monkeypatch):
    """Mock keyring for credential encryption tests."""
    keyring_data = {}

    def mock_get_password(service, username):
        return keyring_data.get(f"{service}:{username}")

    def mock_set_password(service, username, password):
        keyring_data[f"{service}:{username}"] = password

    try:
        import keyring
        monkeypatch.setattr(keyring, 'get_password', mock_get_password)
        monkeypatch.setattr(keyring, 'set_password', mock_set_password)
    except ImportError:
        pass

    return keyring_data


@pytest.fixture
def mock_urllib_request(monkeypatch):
    """Mock urllib.request.urlopen for testing downloads."""
    class MockResponse:
        def __init__(self, content):
            self.content = content

        def read(self):
            return self.content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def mock_urlopen(url, **kwargs):
        # Return fake script content
        return MockResponse(b"#!/bin/bash\necho 'test script'\n")

    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', mock_urlopen)

    return mock_urlopen


@pytest.fixture(autouse=True)
def reset_environment(monkeypatch):
    """Reset environment variables between tests."""
    # Clear Miliciano-related env vars
    env_vars = [
        'NEMOCLAW_POLICY_MODE',
        'MILICIANO_OPENCLAW_INSTALL_URL',
        'MILICIANO_OPENCLAW_INSTALL_CMD',
        'MILICIANO_DEBUG',
        'NVIDIA_API_KEY',
        'NVAPI_API_KEY',
        'NVAPI',
    ]

    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
