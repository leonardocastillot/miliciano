#!/usr/bin/env python3
"""
Disk-based cache for cross-invocation performance optimization.
Caches health checks, ollama model lists, hardware info with TTL.
"""
import json
import os
import time


CACHE_DIR = os.path.expanduser("~/.config/miliciano/cache")


def ensure_cache_dir():
    """Ensure cache directory exists."""
    os.makedirs(CACHE_DIR, exist_ok=True)


def cache_get(key, ttl_seconds=300):
    """
    Read a cached value if it exists and is not expired.

    Args:
        key: Cache key (becomes filename)
        ttl_seconds: Time-to-live in seconds (default 300 = 5 minutes)

    Returns:
        Cached value if valid, None if expired or missing
    """
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)

        # Check expiration
        cached_at = data.get("cached_at", 0)
        if time.time() - cached_at > ttl_seconds:
            return None  # Expired

        return data.get("value")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def cache_set(key, value):
    """
    Write a value to cache with current timestamp.

    Args:
        key: Cache key (becomes filename)
        value: Value to cache (must be JSON-serializable)
    """
    ensure_cache_dir()
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")

    data = {
        "cached_at": time.time(),
        "value": value
    }

    try:
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        # Cache write failure should not break the program
        pass


def cache_invalidate(key):
    """
    Remove a cached value.

    Args:
        key: Cache key to invalidate
    """
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        os.remove(cache_path)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def cache_clear_all():
    """Clear all cached values."""
    try:
        if os.path.exists(CACHE_DIR):
            for filename in os.listdir(CACHE_DIR):
                if filename.endswith(".json"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, filename))
                    except Exception:
                        pass
    except Exception:
        pass
