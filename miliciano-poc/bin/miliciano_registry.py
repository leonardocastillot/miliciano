#!/usr/bin/env python3
"""
Tool registry for dynamic tool management in Miliciano.
Allows declarative registration of CLI/HTTP/MCP tools.
"""
import concurrent.futures
import json
import os
import subprocess
import sys
import urllib.request
from typing import Dict, List, Optional


REGISTRY_PATH = os.path.expanduser("~/.config/miliciano/tools.json")

DEFAULT_TOOLS = {
    "version": "1",
    "tools": {
        "hermes": {
            "type": "cli",
            "binary": "hermes",
            "capabilities": ["reasoning", "chat", "code"],
            "health_check": {
                "command": ["hermes", "--version"],
                "timeout": 5
            },
            "routes": ["reasoning", "fallback"],
            "enabled": True
        },
        "openclaw": {
            "type": "cli",
            "binary": "openclaw",
            "capabilities": ["execution", "agents", "tools"],
            "health_check": {
                "command": ["openclaw", "health", "--json"],
                "timeout": 6,
                "success_pattern": '"ok":true'
            },
            "routes": ["execution"],
            "enabled": True
        },
        "nemoclaw": {
            "type": "cli",
            "binary": "nemoclaw",
            "capabilities": ["policy", "firewall"],
            "health_check": {
                "command": ["nemoclaw", "--version"],
                "timeout": 6
            },
            "routes": [],
            "enabled": True
        },
        "ollama": {
            "type": "http",
            "base_url": "http://127.0.0.1:11434",
            "capabilities": ["local_inference", "chat", "embeddings"],
            "health_check": {
                "url": "http://127.0.0.1:11434/api/tags",
                "timeout": 5
            },
            "routes": ["fast", "local"],
            "enabled": True
        },
        "nvidia": {
            "type": "http",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "capabilities": ["inference", "chat"],
            "health_check": None,
            "routes": ["fallback"],
            "enabled": False,
            "requires_env": ["NVIDIA_API_KEY"]
        }
    }
}


def ensure_registry():
    """Ensure registry file exists with defaults."""
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    if not os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "w") as f:
            json.dump(DEFAULT_TOOLS, f, indent=2)


def load_registry() -> Dict:
    """Load tool registry from disk."""
    ensure_registry()
    try:
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_TOOLS


def save_registry(data: Dict):
    """Save tool registry to disk."""
    ensure_registry()
    with open(REGISTRY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def register_tool(name: str, config: Dict):
    """Register a new tool."""
    registry = load_registry()
    registry["tools"][name] = config
    save_registry(registry)


def unregister_tool(name: str):
    """Unregister a tool."""
    registry = load_registry()
    if name in registry["tools"]:
        del registry["tools"][name]
        save_registry(registry)


def list_tools(filter_type: Optional[str] = None) -> List[Dict]:
    """List all tools, optionally filtered by type."""
    registry = load_registry()
    tools = []
    for name, config in registry["tools"].items():
        if filter_type and config.get("type") != filter_type:
            continue
        tools.append({"name": name, **config})
    return tools


def _check_tool_health_sync(name: str, config: Dict) -> Dict:
    """Check health of a single tool (synchronous)."""
    from shutil import which

    tool_type = config.get("type")
    enabled = config.get("enabled", True)

    if not enabled:
        return {
            "name": name,
            "status": "disabled",
            "message": "Tool is disabled in registry"
        }

    health_check = config.get("health_check")
    if not health_check:
        return {
            "name": name,
            "status": "unknown",
            "message": "No health check defined"
        }

    if tool_type == "cli":
        # Check if binary exists
        binary = config.get("binary")
        if not which(binary):
            return {
                "name": name,
                "status": "error",
                "message": f"Binary '{binary}' not found in PATH"
            }

        # Run health check command
        cmd = health_check.get("command", [])
        timeout = health_check.get("timeout", 5)
        success_pattern = health_check.get("success_pattern")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode == 0:
                if success_pattern:
                    output = result.stdout + result.stderr
                    if success_pattern in output:
                        return {"name": name, "status": "ready", "message": "Health check passed"}
                    else:
                        return {"name": name, "status": "error", "message": f"Pattern '{success_pattern}' not found"}
                else:
                    return {"name": name, "status": "ready", "message": "Health check passed"}
            else:
                return {"name": name, "status": "error", "message": f"Command failed with code {result.returncode}"}
        except subprocess.TimeoutExpired:
            return {"name": name, "status": "error", "message": "Health check timed out"}
        except Exception as e:
            return {"name": name, "status": "error", "message": str(e)}

    elif tool_type == "http":
        # Check HTTP endpoint
        url = health_check.get("url")
        timeout = health_check.get("timeout", 5)

        if not url:
            return {"name": name, "status": "error", "message": "No health check URL defined"}

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return {"name": name, "status": "ready", "message": "HTTP health check passed"}
                else:
                    return {"name": name, "status": "error", "message": f"HTTP {resp.status}"}
        except urllib.error.URLError as e:
            return {"name": name, "status": "error", "message": f"Connection failed: {e.reason}"}
        except Exception as e:
            return {"name": name, "status": "error", "message": str(e)}

    else:
        return {"name": name, "status": "unknown", "message": f"Unknown tool type: {tool_type}"}


def check_tool_health(name: str) -> Dict:
    """Check health of a single tool."""
    registry = load_registry()
    config = registry["tools"].get(name)
    if not config:
        return {"name": name, "status": "error", "message": "Tool not found in registry"}
    return _check_tool_health_sync(name, config)


def check_all_health(parallel: bool = True) -> List[Dict]:
    """Check health of all tools."""
    registry = load_registry()
    tools = registry["tools"]

    if not parallel:
        return [_check_tool_health_sync(name, config) for name, config in tools.items()]

    # Parallel health checks
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_check_tool_health_sync, name, config): name
            for name, config in tools.items()
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                name = futures[future]
                results.append({
                    "name": name,
                    "status": "error",
                    "message": f"Health check failed: {e}"
                })

    return results


def find_tools_for_capability(capability: str) -> List[str]:
    """Find tools that support a given capability."""
    registry = load_registry()
    matching = []
    for name, config in registry["tools"].items():
        if capability in config.get("capabilities", []):
            matching.append(name)
    return matching


def resolve_dispatch(prompt: str, route: str) -> Optional[Dict]:
    """Resolve which tool should handle a given route."""
    registry = load_registry()
    for name, config in registry["tools"].items():
        if route in config.get("routes", []) and config.get("enabled", True):
            return {"name": name, **config}
    return None
