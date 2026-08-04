"""Log sanitization utilities for memory-core.

Provides a logging filter that redacts common sensitive patterns
(passwords, tokens, API keys, private IPs) from log output.
"""

import logging
from typing import Any

# Delegate to the shared redaction module
try:
    from ._redaction import redact as _shared_redact
except ImportError:
    from _redaction import redact as _shared_redact  # type: ignore


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
        """Redact sensitive data using the shared redaction module."""
        return _shared_redact(text, max_len=len(text) if text else 0)

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
