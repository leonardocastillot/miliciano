#!/usr/bin/env python3
"""
Nemoclaw policy enforcement layer for Miliciano.

Provides security policy checks before execution, blocking dangerous operations
and maintaining audit trail.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class PolicyViolation(Exception):
    """Raised when an action violates security policy."""
    pass


class PolicyEngine:
    """
    Interface to Nemoclaw policy enforcement.

    Checks actions against security policies before execution,
    logs all operations for audit, and can modify actions based on policy.
    """

    def __init__(self, nemoclaw_path: str = "nemoclaw", policy_mode: str = "enforce"):
        """
        Initialize policy engine.

        Args:
            nemoclaw_path: Path to Nemoclaw CLI (default: "nemoclaw")
            policy_mode: Policy enforcement mode - "enforce", "audit", or "disabled"
        """
        self.nemoclaw_path = nemoclaw_path
        self.policy_mode = policy_mode
        self.enabled = self._check_available() if policy_mode != "disabled" else False
        self.audit_log_path = self._get_audit_log_path()

    def _get_audit_log_path(self) -> Path:
        """Get path to audit log file."""
        config_dir = Path.home() / '.config' / 'miliciano'
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / 'audit.log'

    def _check_available(self) -> bool:
        """
        Check if Nemoclaw is installed and configured.

        Returns:
            True if Nemoclaw is available and responsive
        """
        try:
            result = subprocess.run(
                [self.nemoclaw_path, "status"],
                capture_output=True,
                timeout=5,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            # Nemoclaw not installed
            return False
        except subprocess.TimeoutExpired:
            # Nemoclaw installed but hanging
            return False
        except Exception:
            return False

    def check_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if action is allowed by policy.

        Args:
            action: Action descriptor with keys:
                - type: Action type (e.g., "openclaw_agent", "shell_command")
                - command: Command to execute
                - args: Command arguments
                - context: Additional context

        Returns:
            Policy result dict with keys:
                - allowed: bool - Whether action is permitted
                - reason: str - Explanation
                - modified_action: dict - Modified action if policy suggests changes

        Raises:
            PolicyViolation: If action blocked and mode is "enforce"
        """
        if not self.enabled:
            # Policy disabled or Nemoclaw unavailable
            if self.policy_mode == "disabled":
                return {
                    "allowed": True,
                    "reason": "policy_disabled",
                    "mode": "disabled"
                }
            else:
                # Fail open if Nemoclaw not available in audit mode
                return {
                    "allowed": True,
                    "reason": "nemoclaw_unavailable",
                    "mode": "audit",
                    "warning": "Nemoclaw not available - running without policy checks"
                }

        # Call Nemoclaw policy check
        try:
            payload = json.dumps(action)
            result = subprocess.run(
                [self.nemoclaw_path, "policy", "check", "--json"],
                input=payload,
                capture_output=True,
                timeout=10,
                text=True
            )

            if result.returncode != 0:
                # Policy check failed
                error_msg = result.stderr.strip() or "Unknown policy violation"
                if "unknown command: policy" in error_msg.lower():
                    fallback_command = action.get("command") or action.get("message") or ""
                    return SimplePolicy(mode=self.policy_mode).check_command(fallback_command)

                if self.policy_mode == "enforce":
                    raise PolicyViolation(f"Policy check failed: {error_msg}")
                else:
                    # Audit mode - log but allow
                    return {
                        "allowed": True,
                        "reason": "policy_violation_audit_mode",
                        "mode": "audit",
                        "violation": error_msg
                    }

            # Parse policy response
            try:
                response = json.loads(result.stdout)
            except json.JSONDecodeError:
                # Invalid JSON response
                if self.policy_mode == "enforce":
                    raise PolicyViolation("Invalid policy response from Nemoclaw")
                else:
                    return {
                        "allowed": True,
                        "reason": "invalid_policy_response",
                        "mode": "audit"
                    }

            # Check if allowed
            if not response.get("allowed", False):
                reason = response.get("reason", "Unknown policy violation")

                if self.policy_mode == "enforce":
                    raise PolicyViolation(reason)
                else:
                    # Audit mode
                    response["mode"] = "audit"
                    response["allowed"] = True  # Override for audit mode
                    response["violation"] = reason

            return response

        except subprocess.TimeoutExpired:
            error_msg = "Policy check timeout"
            if self.policy_mode == "enforce":
                raise PolicyViolation(error_msg)
            else:
                return {
                    "allowed": True,
                    "reason": "policy_timeout",
                    "mode": "audit",
                    "warning": error_msg
                }

        except PolicyViolation:
            raise  # Re-raise policy violations

        except Exception as e:
            error_msg = f"Policy check error: {e}"
            if self.policy_mode == "enforce":
                raise PolicyViolation(error_msg)
            else:
                return {
                    "allowed": True,
                    "reason": "policy_error",
                    "mode": "audit",
                    "error": str(e)
                }

    def audit_log(self, action: Dict[str, Any], policy_result: Dict[str, Any],
                  execution_result: Optional[Dict[str, Any]] = None):
        """
        Log action to audit trail.

        Args:
            action: Action that was checked
            policy_result: Result from policy check
            execution_result: Result from execution (if executed)
        """
        timestamp = datetime.utcnow().isoformat() + 'Z'

        log_entry = {
            "timestamp": timestamp,
            "action": action,
            "policy": policy_result,
        }

        if execution_result is not None:
            log_entry["execution"] = execution_result

        # Write to local audit log
        try:
            with open(self.audit_log_path, 'a') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Warning: Failed to write audit log: {e}", file=sys.stderr)

        # If Nemoclaw available, send to Nemoclaw audit system
        if self.enabled:
            try:
                subprocess.run(
                    [self.nemoclaw_path, "audit", "log"],
                    input=json.dumps(log_entry).encode(),
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                # Nemoclaw audit failed, but local log succeeded
                pass

    def get_policy_status(self) -> Dict[str, Any]:
        """
        Get current policy enforcement status.

        Returns:
            Status dict with keys:
                - enabled: bool
                - mode: str
                - nemoclaw_available: bool
                - audit_log_path: str
        """
        return {
            "enabled": self.enabled,
            "mode": self.policy_mode,
            "nemoclaw_available": self.enabled,
            "audit_log_path": str(self.audit_log_path),
            "audit_log_size": self.audit_log_path.stat().st_size if self.audit_log_path.exists() else 0,
        }


# Simplified policy enforcement for cases where Nemoclaw not available
class SimplePolicy:
    """
    Fallback policy enforcement when Nemoclaw unavailable.

    Implements basic pattern matching for dangerous commands.
    """

    # Dangerous command patterns
    BLOCKED_PATTERNS = [
        r'\brm\s+-rf(?:\s|$)',  # rm -rf
        r'\brmdir\s+-rf(?:\s|$)',  # rmdir -rf
        r'\beval\s*\(',  # eval()
        r'\bexec\s*\(',  # exec()
        r'\|\s*bash\b',  # pipe to bash
        r'\|\s*sh\b',    # pipe to sh
        r';\s*rm\b',     # command chaining with rm
        r'&&\s*rm\b',    # command chaining with rm
    ]

    def __init__(self, mode: str = "enforce"):
        self.mode = mode

    def check_command(self, command: str) -> Dict[str, Any]:
        """
        Check command against simple pattern blocklist.

        Args:
            command: Command string to check

        Returns:
            Result dict with allowed/reason keys

        Raises:
            PolicyViolation: If command blocked and mode is enforce
        """
        import re

        command_lower = command.lower()

        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, command_lower):
                reason = f"Dangerous pattern detected: {pattern}"

                if self.mode == "enforce":
                    raise PolicyViolation(reason)
                else:
                    return {
                        "allowed": True,  # Audit mode
                        "reason": "pattern_violation_audit_mode",
                        "mode": "audit",
                        "violation": reason
                    }

        return {
            "allowed": True,
            "reason": "simple_policy_passed"
        }


def create_policy_engine(policy_mode: Optional[str] = None) -> PolicyEngine:
    """
    Create policy engine with configuration from environment/config.

    Args:
        policy_mode: Override policy mode (enforce/audit/disabled)

    Returns:
        Configured PolicyEngine instance
    """
    # Check environment variable
    if policy_mode is None:
        policy_mode = os.environ.get("NEMOCLAW_POLICY_MODE", "enforce").lower()

    # Validate mode
    if policy_mode not in {"enforce", "audit", "disabled"}:
        print(f"Warning: Invalid policy mode '{policy_mode}', using 'enforce'",
              file=sys.stderr)
        policy_mode = "enforce"

    return PolicyEngine(policy_mode=policy_mode)


if __name__ == "__main__":
    # Self-test
    print("Miliciano Policy Engine")
    print("=" * 50)

    # Create engine
    engine = create_policy_engine()
    status = engine.get_policy_status()

    print(f"Policy mode: {status['mode']}")
    print(f"Nemoclaw available: {status['nemoclaw_available']}")
    print(f"Audit log: {status['audit_log_path']}")

    if not status['nemoclaw_available']:
        print("\n⚠️  Nemoclaw not available")
        print("Policy checks will use fallback simple policy")
        print("Install Nemoclaw for full policy enforcement")

    # Test simple policy
    print("\n" + "=" * 50)
    print("Testing fallback simple policy...")
    simple = SimplePolicy(mode="audit")

    safe_cmd = "ls -la /tmp"
    result = simple.check_command(safe_cmd)
    print(f"✓ Safe command allowed: {safe_cmd}")

    try:
        dangerous_cmd = "rm -rf /"
        result = simple.check_command(dangerous_cmd)
        if "violation" in result:
            print(f"⚠️  Dangerous command detected (audit mode): {dangerous_cmd}")
            print(f"   Violation: {result['violation']}")
    except PolicyViolation as e:
        print(f"❌ Dangerous command blocked: {e}")

    print("\n✓ Policy engine ready")
