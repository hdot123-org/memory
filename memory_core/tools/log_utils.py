"""Log sanitization utilities for memory-core.

Provides a logging filter that redacts common sensitive patterns
(passwords, tokens, API keys, private IPs) from log output.
"""
from __future__ import annotations

import logging
import re
from typing import Any

# Patterns to redact from log output (order matters: Bearer first, then generic)
_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(Bearer\s+)\S+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.I), r"\1=***REDACTED***"),
    (re.compile(r"(token|api[_-]?key|secret|authorization)\s*[=:]\s*['\"]?\S+", re.I), r"\1=***REDACTED***"),
    (re.compile(r"192\.168\.\d{1,3}\.\d{1,3}"), "***REDACTED_IP***"),
    (re.compile(r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"), "***REDACTED_IP***"),
    (re.compile(r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"), "***REDACTED_IP***"),
]


class SanitizingFilter(logging.Filter):
    """Logging filter that redacts sensitive data from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            record.args = self._redact_args(record.args)
        return True

    @staticmethod
    def _redact(text: str) -> str:
        for pattern, replacement in _REDACT_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    @staticmethod
    def _redact_args(args: Any) -> Any:
        if isinstance(args, dict):
            return {k: SanitizingFilter._redact(str(v)) if isinstance(v, str) else v for k, v in args.items()}
        if isinstance(args, tuple):
            return tuple(SanitizingFilter._redact(str(a)) if isinstance(a, str) else a for a in args)
        return args


def get_sanitized_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Create a logger with the sanitizing filter attached."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not any(isinstance(f, SanitizingFilter) for f in logger.filters):
        logger.addFilter(SanitizingFilter())
    return logger
