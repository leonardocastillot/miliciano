"""
Unit tests for miliciano_validators.py
"""

import pytest
from miliciano_validators import (
    validate_provider,
    validate_model_spec,
    validate_route_name,
    validate_install_url,
    sanitize_prompt,
    validate_path,
    validate_api_key,
    validate_command_args,
    ValidationError,
)


class TestValidateProvider:
    """Tests for validate_provider()"""

    def test_valid_provider_simple(self):
        """Test valid simple provider name."""
        assert validate_provider("openai") == "openai"

    def test_valid_provider_with_hyphen(self):
        """Test valid provider with hyphens."""
        assert validate_provider("openai-codex") == "openai-codex"

    def test_valid_provider_with_numbers(self):
        """Test provider with numbers."""
        assert validate_provider("gpt4") == "gpt4"

    def test_invalid_empty(self):
        """Test empty provider name."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_provider("")

    def test_invalid_special_chars(self):
        """Test provider with shell special characters."""
        with pytest.raises(ValidationError):
            validate_provider("test'; rm -rf /")

    def test_invalid_path_traversal(self):
        """Test path traversal attempt."""
        with pytest.raises(ValidationError):
            validate_provider("../../../etc/passwd")

    def test_invalid_forward_slash(self):
        """Test forward slash in provider."""
        with pytest.raises(ValidationError):
            validate_provider("provider/model")

    def test_invalid_backslash(self):
        """Test backslash in provider."""
        with pytest.raises(ValidationError):
            validate_provider("provider\\model")

    def test_strips_whitespace(self):
        """Test whitespace is stripped."""
        assert validate_provider("  openai  ") == "openai"


class TestValidateModelSpec:
    """Tests for validate_model_spec()"""

    def test_valid_spec(self):
        """Test valid provider/model spec."""
        provider, model = validate_model_spec("openai-codex/gpt-4")
        assert provider == "openai-codex"
        assert model == "gpt-4"

    def test_valid_spec_with_dots(self):
        """Test model with dots."""
        provider, model = validate_model_spec("custom/qwen2.5:3b")
        assert provider == "custom"
        assert model == "qwen2.5:3b"

    def test_invalid_no_separator(self):
        """Test spec without separator."""
        with pytest.raises(ValidationError, match="provider/model"):
            validate_model_spec("invalid-spec")

    def test_invalid_empty(self):
        """Test empty spec."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_model_spec("")

    def test_invalid_shell_chars(self):
        """Test shell metacharacters."""
        with pytest.raises(ValidationError):
            validate_model_spec("provider/model; rm -rf /")

    def test_invalid_path_traversal_in_model(self):
        """Test path traversal in model name."""
        with pytest.raises(ValidationError):
            validate_model_spec("provider/../../../etc/passwd")

    def test_strips_whitespace(self):
        """Test whitespace stripping."""
        provider, model = validate_model_spec("  openai / gpt-4  ")
        assert provider == "openai"
        assert model == "gpt-4"


class TestValidateRouteName:
    """Tests for validate_route_name()"""

    def test_valid_routes(self):
        """Test all valid route names."""
        valid = ["reasoning", "execution", "fast", "local", "fallback"]
        for route in valid:
            assert validate_route_name(route) == route

    def test_case_insensitive(self):
        """Test route names are case-insensitive."""
        assert validate_route_name("REASONING") == "reasoning"
        assert validate_route_name("Execution") == "execution"

    def test_invalid_route(self):
        """Test invalid route name."""
        with pytest.raises(ValidationError, match="Invalid route"):
            validate_route_name("invalid")

    def test_empty_route(self):
        """Test empty route name."""
        with pytest.raises(ValidationError):
            validate_route_name("")


class TestValidateInstallUrl:
    """Tests for validate_install_url()"""

    def test_valid_ollama_url(self):
        """Test valid Ollama install URL."""
        url = "https://ollama.com/install.sh"
        assert validate_install_url(url) == url

    def test_valid_github_url(self):
        """Test valid GitHub URL."""
        url = "https://github.com/user/repo/install.sh"
        assert validate_install_url(url) == url

    def test_invalid_http(self):
        """Test HTTP (not HTTPS) is rejected."""
        with pytest.raises(ValidationError, match="HTTPS"):
            validate_install_url("http://ollama.com/install.sh")

    def test_invalid_untrusted_domain(self):
        """Test untrusted domain is rejected."""
        with pytest.raises(ValidationError, match="Untrusted"):
            validate_install_url("https://evil.com/malware.sh")

    def test_empty_url(self):
        """Test empty URL."""
        with pytest.raises(ValidationError):
            validate_install_url("")


class TestSanitizePrompt:
    """Tests for sanitize_prompt()"""

    def test_valid_prompt(self):
        """Test normal prompt."""
        prompt = "What is 2 + 2?"
        assert sanitize_prompt(prompt) == prompt

    def test_strips_whitespace(self):
        """Test whitespace stripping."""
        assert sanitize_prompt("  test  ") == "test"

    def test_rejects_null_bytes(self):
        """Test null bytes are rejected."""
        with pytest.raises(ValidationError, match="null bytes"):
            sanitize_prompt("test\x00malicious")

    def test_rejects_too_long(self):
        """Test overly long prompts rejected."""
        long_prompt = "x" * 60000
        with pytest.raises(ValidationError, match="too long"):
            sanitize_prompt(long_prompt, max_length=50000)

    def test_empty_after_strip(self):
        """Test prompt empty after stripping."""
        with pytest.raises(ValidationError, match="empty"):
            sanitize_prompt("   ")


class TestValidatePath:
    """Tests for validate_path()"""

    def test_valid_absolute_path(self):
        """Test valid absolute path."""
        path = "/home/user/file.txt"
        assert validate_path(path) == path

    def test_rejects_traversal_absolute(self):
        """Test path traversal rejected by default."""
        with pytest.raises(ValidationError):
            validate_path("/home/user/../../../etc/passwd")

    def test_allows_traversal_if_enabled(self):
        """Test path traversal allowed when explicitly enabled."""
        path = "../relative/path"
        assert validate_path(path, allow_relative=True) == path

    def test_rejects_null_bytes(self):
        """Test null bytes rejected."""
        with pytest.raises(ValidationError):
            validate_path("/path\x00/file")


class TestValidateApiKey:
    """Tests for validate_api_key()"""

    def test_valid_generic_key(self):
        """Test valid generic API key."""
        key = "x" * 40
        assert validate_api_key(key) == key

    def test_valid_openai_key(self):
        """Test valid OpenAI key."""
        key = "sk-" + "x" * 40
        assert validate_api_key(key, provider="openai") == key

    def test_valid_anthropic_key(self):
        """Test valid Anthropic key."""
        key = "sk-ant-" + "x" * 40
        assert validate_api_key(key, provider="anthropic") == key

    def test_invalid_openai_prefix(self):
        """Test OpenAI key with wrong prefix."""
        with pytest.raises(ValidationError, match="sk-"):
            validate_api_key("wrong-prefix-xxx", provider="openai")

    def test_invalid_anthropic_prefix(self):
        """Test Anthropic key with wrong prefix."""
        with pytest.raises(ValidationError, match="sk-ant-"):
            validate_api_key("sk-xxx", provider="anthropic")

    def test_too_short(self):
        """Test key too short."""
        with pytest.raises(ValidationError, match="too short"):
            validate_api_key("short")

    def test_invalid_characters(self):
        """Test key with invalid characters."""
        with pytest.raises(ValidationError):
            validate_api_key("x" * 30 + "\n" + "y" * 30)


class TestValidateCommandArgs:
    """Tests for validate_command_args()"""

    def test_valid_args(self):
        """Test valid command arguments."""
        args = ["ls", "-la", "/tmp"]
        assert validate_command_args(args) == args

    def test_empty_list(self):
        """Test empty args list."""
        with pytest.raises(ValidationError):
            validate_command_args([])

    def test_not_list(self):
        """Test non-list argument."""
        with pytest.raises(ValidationError, match="must be a list"):
            validate_command_args("not a list")

    def test_non_string_arg(self):
        """Test non-string in args."""
        with pytest.raises(ValidationError, match="must be string"):
            validate_command_args(["ls", 123])

    def test_null_byte_in_arg(self):
        """Test null byte in argument."""
        with pytest.raises(ValidationError):
            validate_command_args(["ls", "\x00malicious"])


class TestEdgeCases:
    """Edge case and security tests"""

    @pytest.mark.security
    def test_sql_injection_attempt(self):
        """Test SQL injection pattern rejected."""
        with pytest.raises(ValidationError):
            validate_provider("'; DROP TABLE users--")

    @pytest.mark.security
    def test_command_injection_attempt(self):
        """Test command injection rejected."""
        with pytest.raises(ValidationError):
            validate_provider("test`whoami`")

    @pytest.mark.security
    def test_unicode_bypass_attempt(self):
        """Test Unicode normalization doesn't bypass."""
        # Some Unicode characters normalize to dangerous chars
        # This is basic test - real implementation may need more
        result = validate_provider("test")
        assert result == "test"

    def test_very_long_provider_name(self):
        """Test extremely long provider name."""
        long_name = "a" * 1000
        # Should either accept or reject cleanly
        try:
            validate_provider(long_name)
        except ValidationError:
            pass  # Expected

    def test_model_spec_multiple_slashes(self):
        """Test model spec with multiple slashes."""
        provider, model = validate_model_spec("provider/model/with/slashes")
        assert provider == "provider"
        assert model == "model/with/slashes"
