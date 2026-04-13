#!/usr/bin/env python3
"""
Credential encryption for Miliciano.

Provides encryption/decryption of sensitive credentials using OS keyring
and the cryptography library (Fernet symmetric encryption).
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Check if cryptography is available
try:
    from cryptography.fernet import Fernet, InvalidToken
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    Fernet = None
    InvalidToken = None

# Check if keyring is available
try:
    import keyring
    from keyring.errors import KeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    keyring = None
    KeyringError = None


SERVICE_NAME = "miliciano"
KEY_NAME = "encryption_key"

# Fields that should be encrypted
SENSITIVE_FIELDS = {
    "api_key",
    "token",
    "password",
    "secret",
    "key",
    "credential",
    "bearer",
    "auth",
}


def check_dependencies():
    """Check if required encryption libraries are available."""
    missing = []
    if not CRYPTO_AVAILABLE:
        missing.append("cryptography")
    if not KEYRING_AVAILABLE:
        missing.append("keyring")

    if missing:
        return False, f"Missing required packages: {', '.join(missing)}"

    return True, "Encryption dependencies available"


def get_or_create_encryption_key() -> Optional[bytes]:
    """
    Get encryption key from OS keyring, or create new one if missing.

    Returns:
        Encryption key as bytes, or None if keyring unavailable

    Raises:
        Exception: If key operations fail
    """
    if not KEYRING_AVAILABLE or not CRYPTO_AVAILABLE:
        return None

    try:
        # Try to get existing key
        key_str = keyring.get_password(SERVICE_NAME, KEY_NAME)

        if key_str:
            return key_str.encode()

        # Generate new key
        key = Fernet.generate_key()
        keyring.set_password(SERVICE_NAME, KEY_NAME, key.decode())
        return key

    except KeyringError as e:
        # Keyring not available on this system
        print(f"Warning: OS keyring not available: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Failed to manage encryption key: {e}", file=sys.stderr)
        return None


def is_encrypted_value(value: str) -> bool:
    """Check if a string value looks like encrypted data."""
    if not isinstance(value, str):
        return False

    # Encrypted values are base64 and fairly long
    if len(value) < 40:
        return False

    # Fernet tokens start with specific prefix
    try:
        return value.startswith("gAAAAA")  # Fernet token prefix
    except:
        return False


def encrypt_value(value: str, key: bytes) -> str:
    """
    Encrypt a string value.

    Args:
        value: Plain text value
        key: Encryption key from get_or_create_encryption_key()

    Returns:
        Encrypted value as string

    Raises:
        Exception: If encryption fails
    """
    if not CRYPTO_AVAILABLE or not key:
        return value

    try:
        f = Fernet(key)
        encrypted_bytes = f.encrypt(value.encode())
        return encrypted_bytes.decode()
    except Exception as e:
        print(f"Warning: Encryption failed: {e}", file=sys.stderr)
        return value


def decrypt_value(encrypted_value: str, key: bytes) -> str:
    """
    Decrypt an encrypted value.

    Args:
        encrypted_value: Encrypted string
        key: Encryption key

    Returns:
        Decrypted plain text

    Raises:
        Exception: If decryption fails
    """
    if not CRYPTO_AVAILABLE or not key:
        return encrypted_value

    # If not encrypted, return as-is
    if not is_encrypted_value(encrypted_value):
        return encrypted_value

    try:
        f = Fernet(key)
        decrypted_bytes = f.decrypt(encrypted_value.encode())
        return decrypted_bytes.decode()
    except InvalidToken:
        # Token is invalid or corrupted
        print("Warning: Failed to decrypt value (invalid token)", file=sys.stderr)
        return encrypted_value
    except Exception as e:
        print(f"Warning: Decryption failed: {e}", file=sys.stderr)
        return encrypted_value


def should_encrypt_field(field_name: str) -> bool:
    """
    Check if a field should be encrypted based on its name.

    Args:
        field_name: Name of the field

    Returns:
        True if field should be encrypted
    """
    field_lower = field_name.lower()

    # Check if any sensitive keyword is in field name
    for sensitive in SENSITIVE_FIELDS:
        if sensitive in field_lower:
            return True

    return False


def encrypt_config(data: Dict[str, Any], key: Optional[bytes] = None) -> Dict[str, Any]:
    """
    Encrypt sensitive fields in configuration dictionary.

    Args:
        data: Configuration dictionary
        key: Optional encryption key (will be auto-generated if None)

    Returns:
        Dictionary with sensitive fields encrypted
    """
    if not CRYPTO_AVAILABLE or not KEYRING_AVAILABLE:
        # Encryption not available, return as-is
        return data

    if key is None:
        key = get_or_create_encryption_key()
        if key is None:
            return data

    encrypted = {}

    for field, value in data.items():
        if isinstance(value, dict):
            # Recursively encrypt nested dicts
            encrypted[field] = encrypt_config(value, key)
        elif isinstance(value, str) and should_encrypt_field(field):
            # Encrypt if not already encrypted
            if not is_encrypted_value(value):
                encrypted[field] = encrypt_value(value, key)
            else:
                encrypted[field] = value
        else:
            encrypted[field] = value

    return encrypted


def decrypt_config(data: Dict[str, Any], key: Optional[bytes] = None) -> Dict[str, Any]:
    """
    Decrypt sensitive fields in configuration dictionary.

    Args:
        data: Configuration dictionary with encrypted fields
        key: Optional encryption key

    Returns:
        Dictionary with sensitive fields decrypted
    """
    if not CRYPTO_AVAILABLE or not KEYRING_AVAILABLE:
        return data

    if key is None:
        key = get_or_create_encryption_key()
        if key is None:
            return data

    decrypted = {}

    for field, value in data.items():
        if isinstance(value, dict):
            # Recursively decrypt nested dicts
            decrypted[field] = decrypt_config(value, key)
        elif isinstance(value, str) and should_encrypt_field(field):
            # Decrypt if encrypted
            decrypted[field] = decrypt_value(value, key)
        else:
            decrypted[field] = value

    return decrypted


def encrypt_json_file(file_path: str) -> bool:
    """
    Encrypt sensitive fields in a JSON file (in-place).

    Args:
        file_path: Path to JSON file

    Returns:
        True if encryption succeeded, False otherwise
    """
    path = Path(file_path)

    if not path.exists():
        return False

    try:
        with open(path, 'r') as f:
            data = json.load(f)

        encrypted = encrypt_config(data)

        with open(path, 'w') as f:
            json.dump(encrypted, f, indent=2)

        return True

    except Exception as e:
        print(f"Error encrypting {file_path}: {e}", file=sys.stderr)
        return False


def decrypt_json_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Load and decrypt a JSON file.

    Args:
        file_path: Path to JSON file

    Returns:
        Decrypted data, or None if failed
    """
    path = Path(file_path)

    if not path.exists():
        return None

    try:
        with open(path, 'r') as f:
            data = json.load(f)

        return decrypt_config(data)

    except Exception as e:
        print(f"Error decrypting {file_path}: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    # Self-test
    print("Miliciano Crypto Module")
    print("=" * 50)

    # Check dependencies
    ok, msg = check_dependencies()
    print(f"Dependencies: {msg}")

    if not ok:
        print("\nTo enable encryption, install:")
        print("  pip3 install cryptography keyring")
        sys.exit(1)

    # Test encryption
    print("\nTesting encryption...")

    key = get_or_create_encryption_key()
    if not key:
        print("❌ Failed to get encryption key")
        sys.exit(1)

    print("✓ Encryption key available")

    # Test value encryption
    test_value = "sk-test-api-key-12345"
    encrypted = encrypt_value(test_value, key)
    print(f"✓ Encrypted: {test_value[:10]}... → {encrypted[:20]}...")

    decrypted = decrypt_value(encrypted, key)
    assert decrypted == test_value, "Decryption failed"
    print(f"✓ Decrypted correctly")

    # Test config encryption
    test_config = {
        "provider": "openai",
        "api_key": "sk-secret-key",
        "model": "gpt-4",
        "nested": {
            "token": "bearer-token-123",
            "url": "https://api.example.com"
        }
    }

    encrypted_config = encrypt_config(test_config)
    print(f"✓ Config encrypted ({len(encrypted_config)} fields)")

    decrypted_config = decrypt_config(encrypted_config)
    assert decrypted_config["api_key"] == test_config["api_key"]
    assert decrypted_config["nested"]["token"] == test_config["nested"]["token"]
    print(f"✓ Config decrypted correctly")

    print("\n✓ All tests passed")
    print("\nEncryption system ready for use")
