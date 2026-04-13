#!/usr/bin/env python3
"""
Input validation and sanitization for Miliciano.

Provides security-focused validation for all user inputs, configuration values,
and external data to prevent injection attacks and ensure data integrity.
"""

import re
from typing import Optional, Tuple
from urllib.parse import urlparse


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


# Allowed domains for external script downloads
ALLOWED_INSTALL_DOMAINS = [
    "install.openclaw.io",
    "github.com",
    "raw.githubusercontent.com",
    "ollama.com",
    "ollama.ai",
]

# Valid routing roles
VALID_ROUTES = {"reasoning", "execution", "fast", "local", "fallback"}


def validate_provider(provider: str) -> str:
    """
    Validate provider name format.

    Provider names must be alphanumeric with hyphens, starting with alphanumeric.
    This prevents shell injection and path traversal.

    Args:
        provider: Provider name to validate

    Returns:
        Validated provider name

    Raises:
        ValidationError: If provider name is invalid

    Examples:
        >>> validate_provider("openai-codex")
        'openai-codex'
        >>> validate_provider("test'; rm -rf /")
        ValidationError: Invalid provider name
    """
    if not provider:
        raise ValidationError("Provider name cannot be empty")

    provider = provider.strip()
    if not provider:
        raise ValidationError("Provider name cannot be empty")

    if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$', provider, re.IGNORECASE):
        raise ValidationError(
            f"Invalid provider name: {provider}. "
            "Must be alphanumeric with hyphens, no special characters."
        )

    # Check for path traversal patterns
    if ".." in provider or "/" in provider or "\\" in provider:
        raise ValidationError(f"Provider name contains invalid path characters: {provider}")

    return provider


def validate_model_spec(spec: str) -> Tuple[str, str]:
    """
    Validate and parse model specification (provider/model).

    Args:
        spec: Model spec in format "provider/model"

    Returns:
        Tuple of (provider, model)

    Raises:
        ValidationError: If spec is invalid

    Examples:
        >>> validate_model_spec("openai-codex/gpt-4")
        ('openai-codex', 'gpt-4')
    """
    if not spec:
        raise ValidationError("Model spec cannot be empty")

    spec = spec.strip()

    if '/' not in spec:
        raise ValidationError(
            f"Model spec must be in format 'provider/model', got: {spec}"
        )

    parts = spec.split('/', 1)
    if len(parts) != 2:
        raise ValidationError(f"Invalid model spec format: {spec}")

    provider, model = parts
    model = model.strip()

    # Validate provider
    provider = validate_provider(provider)

    # Validate model name
    if not model or not model.strip():
        raise ValidationError("Model name cannot be empty")

    # Model names can contain alphanumeric, dots, hyphens, underscores, colons
    if not re.match(r'^[a-zA-Z0-9._:/-]+$', model):
        raise ValidationError(
            f"Invalid model name: {model}. "
            "Must contain only alphanumeric, dots, slashes, hyphens, underscores, colons."
        )

    # Check for path traversal
    if ".." in model:
        raise ValidationError(f"Model name contains path traversal pattern: {model}")

    return provider, model


def validate_route_name(route: str) -> str:
    """
    Validate routing role name.

    Args:
        route: Route name to validate

    Returns:
        Validated route name

    Raises:
        ValidationError: If route is invalid
    """
    if not route:
        raise ValidationError("Route name cannot be empty")

    route = route.strip().lower()

    if route not in VALID_ROUTES:
        raise ValidationError(
            f"Invalid route: {route}. Must be one of: {', '.join(sorted(VALID_ROUTES))}"
        )

    return route


def sanitize_prompt(prompt: str, max_length: int = 50000) -> str:
    """
    Sanitize user prompt for safe processing.

    Args:
        prompt: User input prompt
        max_length: Maximum allowed length

    Returns:
        Sanitized prompt

    Raises:
        ValidationError: If prompt is invalid
    """
    if not prompt:
        raise ValidationError("Prompt cannot be empty")

    # Check length
    if len(prompt) > max_length:
        raise ValidationError(
            f"Prompt too long: {len(prompt)} characters (max: {max_length})"
        )

    # Remove null bytes (can cause issues in subprocess)
    if '\0' in prompt:
        raise ValidationError("Prompt contains null bytes")

    # Strip excessive whitespace but preserve structure
    cleaned = prompt.strip()

    if not cleaned:
        raise ValidationError("Prompt is empty after sanitization")

    return cleaned


def validate_install_url(url: str) -> str:
    """
    Validate installation URL is from trusted source.

    Only HTTPS URLs from whitelisted domains are allowed.

    Args:
        url: URL to validate

    Returns:
        Validated URL

    Raises:
        ValidationError: If URL is untrusted

    Examples:
        >>> validate_install_url("https://ollama.com/install.sh")
        'https://ollama.com/install.sh'
        >>> validate_install_url("http://evil.com/malware.sh")
        ValidationError: Installation URLs must use HTTPS
    """
    if not url:
        raise ValidationError("Installation URL cannot be empty")

    # Must use HTTPS
    if not url.startswith("https://"):
        raise ValidationError(
            f"Installation URLs must use HTTPS, got: {url}"
        )

    # Parse and validate domain
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValidationError(f"Invalid URL format: {e}")

    domain = parsed.netloc.lower()

    # Remove port if present
    if ':' in domain:
        domain = domain.split(':')[0]

    # Check against whitelist
    if domain not in ALLOWED_INSTALL_DOMAINS:
        raise ValidationError(
            f"Untrusted installation domain: {domain}. "
            f"Allowed domains: {', '.join(ALLOWED_INSTALL_DOMAINS)}"
        )

    return url


def validate_path(path: str, allow_relative: bool = False) -> str:
    """
    Validate file path to prevent path traversal attacks.

    Args:
        path: File path to validate
        allow_relative: Whether to allow relative paths

    Returns:
        Validated path

    Raises:
        ValidationError: If path is invalid
    """
    if not path:
        raise ValidationError("Path cannot be empty")

    # Check for null bytes
    if '\0' in path:
        raise ValidationError("Path contains null bytes")

    # Check for path traversal patterns
    normalized = path.replace('\\', '/')

    if not allow_relative:
        if '..' in normalized.split('/'):
            raise ValidationError(f"Path contains traversal pattern: {path}")

    return path


def validate_api_key(api_key: str, provider: Optional[str] = None) -> str:
    """
    Validate API key format.

    Basic validation to ensure key looks legitimate.

    Args:
        api_key: API key to validate
        provider: Optional provider name for provider-specific validation

    Returns:
        Validated API key

    Raises:
        ValidationError: If API key format is invalid
    """
    if not api_key:
        raise ValidationError("API key cannot be empty")

    key = api_key.strip()
    if not key:
        raise ValidationError("API key cannot be empty")

    provider_lower = provider.lower().strip() if provider else None

    if provider_lower and ("openai" == provider_lower or "openai" in provider_lower):
        if not key.startswith("sk-"):
            raise ValidationError("OpenAI API keys must start with 'sk-'")
    elif provider_lower == "anthropic":
        if not key.startswith("sk-ant-"):
            raise ValidationError("Anthropic API keys must start with 'sk-ant-'")
    elif provider_lower == "nvidia":
        if not key.startswith("nvapi-"):
            raise ValidationError("NVIDIA API keys must start with 'nvapi-'")

    # Check minimum length
    if len(key) < 20:
        raise ValidationError("API key too short (minimum 20 characters)")

    # Check for suspicious characters
    if '\n' in key or '\r' in key or '\0' in key:
        raise ValidationError("API key contains invalid characters")

    # Provider-specific validation
    return key


def validate_command_args(args: list) -> list:
    """
    Validate command arguments for subprocess calls.

    Args:
        args: List of command arguments

    Returns:
        Validated arguments list

    Raises:
        ValidationError: If arguments are invalid
    """
    if not args:
        raise ValidationError("Command arguments cannot be empty")

    if not isinstance(args, list):
        raise ValidationError("Command arguments must be a list")

    validated = []
    for arg in args:
        if not isinstance(arg, str):
            raise ValidationError(f"Command argument must be string, got: {type(arg)}")

        # Check for null bytes
        if '\0' in arg:
            raise ValidationError("Command argument contains null bytes")

        validated.append(arg)

    return validated


def validate_json_safe(data: dict, max_depth: int = 10, max_keys: int = 1000) -> dict:
    """
    Validate JSON data is safe (no excessive nesting or size).

    Args:
        data: Dictionary to validate
        max_depth: Maximum nesting depth
        max_keys: Maximum total keys

    Returns:
        Validated data

    Raises:
        ValidationError: If data structure is unsafe
    """
    if not isinstance(data, dict):
        raise ValidationError("Data must be a dictionary")

    def count_depth(obj, depth=0):
        if depth > max_depth:
            raise ValidationError(f"JSON nesting too deep (max: {max_depth})")

        if isinstance(obj, dict):
            for value in obj.values():
                count_depth(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                count_depth(item, depth + 1)

    def count_keys(obj):
        count = 0
        if isinstance(obj, dict):
            count += len(obj)
            for value in obj.values():
                count += count_keys(value)
        elif isinstance(obj, list):
            for item in obj:
                count += count_keys(item)
        return count

    count_depth(data)

    total_keys = count_keys(data)
    if total_keys > max_keys:
        raise ValidationError(f"Too many keys in JSON: {total_keys} (max: {max_keys})")

    return data


if __name__ == "__main__":
    # Self-test
    import sys

    try:
        # Test valid inputs
        assert validate_provider("openai-codex") == "openai-codex"
        assert validate_model_spec("openai-codex/gpt-4") == ("openai-codex", "gpt-4")
        assert validate_route_name("reasoning") == "reasoning"
        assert validate_install_url("https://ollama.com/install.sh")

        # Test invalid inputs
        try:
            validate_provider("test'; rm -rf /")
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass

        try:
            validate_model_spec("no-separator")
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass

        try:
            validate_install_url("http://evil.com/malware.sh")
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass

        print("✓ All validation tests passed")
        sys.exit(0)

    except Exception as e:
        print(f"✗ Validation test failed: {e}")
        sys.exit(1)
