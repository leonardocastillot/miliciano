#!/usr/bin/env python3
"""
Structured logging for Miliciano.

Provides JSON-formatted logs to files with automatic rotation,
and human-readable output to console.
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON line.

        Args:
            record: Log record to format

        Returns:
            JSON string
        """
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)

        return json.dumps(log_data, ensure_ascii=False)


class StructuredLogger:
    """
    Structured logging with JSON file output and console output.

    Features:
    - JSON logs to rotating file
    - Human-readable console output
    - Automatic log rotation (10MB, 5 backups)
    - Configurable log levels
    """

    def __init__(self, name: str = "miliciano", log_level: str = "INFO"):
        """
        Initialize structured logger.

        Args:
            name: Logger name
            log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        # Clear any existing handlers
        self.logger.handlers.clear()

        # Console handler (human-readable)
        self._setup_console_handler()

        # File handler (JSON structured)
        self._setup_file_handler()

    def _setup_console_handler(self):
        """Setup console handler with human-readable format."""
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)

        # Human-readable format
        console_format = logging.Formatter(
            '%(asctime)s [%(levelname)-7s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console.setFormatter(console_format)

        self.logger.addHandler(console)

    def _setup_file_handler(self):
        """Setup rotating file handler with JSON format."""
        # Create log directory
        log_dir = Path.home() / '.config' / 'miliciano' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / 'miliciano.log'

        # Rotating file handler (10MB, keep 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonFormatter())

        self.logger.addHandler(file_handler)

    def _log(self, level: int, message: str, **extra_fields):
        """
        Internal log method with extra fields.

        Args:
            level: Log level (logging.DEBUG, INFO, etc.)
            message: Log message
            **extra_fields: Additional fields to include in JSON
        """
        # Create log record with extra fields
        extra = {'extra_fields': extra_fields} if extra_fields else {}
        self.logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self._log(logging.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs):
        """Log exception with traceback."""
        self.logger.exception(message, extra={'extra_fields': kwargs} if kwargs else {})


# Global logger instance
_global_logger: Optional[StructuredLogger] = None


def get_logger(name: str = "miliciano") -> StructuredLogger:
    """
    Get or create global logger instance.

    Args:
        name: Logger name

    Returns:
        StructuredLogger instance
    """
    global _global_logger

    if _global_logger is None:
        # Check for debug mode
        log_level = "DEBUG" if os.environ.get("MILICIANO_DEBUG") else "INFO"
        _global_logger = StructuredLogger(name, log_level=log_level)

    return _global_logger


def log_operation(operation: str, **details):
    """
    Log an operation with details.

    Convenience function for logging operations.

    Args:
        operation: Operation name
        **details: Operation details
    """
    logger = get_logger()
    logger.info(f"Operation: {operation}", operation=operation, **details)


def log_error(error: str, **details):
    """
    Log an error with details.

    Args:
        error: Error message
        **details: Error details
    """
    logger = get_logger()
    logger.error(f"Error: {error}", error=error, **details)


def log_security_event(event: str, **details):
    """
    Log a security-related event.

    Args:
        event: Event description
        **details: Event details
    """
    logger = get_logger()
    logger.warning(f"Security event: {event}", event_type="security", event=event, **details)


if __name__ == "__main__":
    # Self-test
    print("Miliciano Logging Module")
    print("=" * 50)

    # Create logger
    logger = get_logger()

    log_dir = Path.home() / '.config' / 'miliciano' / 'logs'
    log_file = log_dir / 'miliciano.log'

    print(f"Log directory: {log_dir}")
    print(f"Log file: {log_file}")

    # Test different log levels
    logger.debug("Debug message", detail="debug info")
    logger.info("Info message", detail="info data")
    logger.warning("Warning message", detail="warning info")
    logger.error("Error message", detail="error data")

    # Test convenience functions
    log_operation("test_operation", status="success", duration_ms=123)
    log_error("test_error", error_code="TEST001", details="Test error details")
    log_security_event("test_security_event", threat_level="low", action="logged")

    # Test exception logging
    try:
        raise ValueError("Test exception")
    except Exception:
        logger.exception("Caught test exception", context="self_test")

    print("\n✓ Logging test complete")
    print(f"\nCheck logs at: {log_file}")

    # Show last few log lines
    if log_file.exists():
        print("\nLast 5 log entries:")
        with open(log_file) as f:
            lines = f.readlines()
            for line in lines[-5:]:
                try:
                    entry = json.loads(line)
                    print(f"  [{entry['level']}] {entry['message']}")
                except:
                    print(f"  {line.strip()}")
