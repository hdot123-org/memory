"""Tests for log sanitization utilities."""
from __future__ import annotations

import logging

from memory_core.tools.log_utils import SanitizingFilter, get_sanitized_logger


class TestSanitizingFilter:
    def test_redacts_password(self) -> None:
        f = SanitizingFilter()
        result = f._redact("password=secret123")
        assert "secret123" not in result
        assert "***REDACTED***" in result

    def test_redacts_token(self) -> None:
        f = SanitizingFilter()
        result = f._redact("token=abc123def456")
        assert "abc123def456" not in result

    def test_redacts_bearer(self) -> None:
        f = SanitizingFilter()
        result = f._redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "***REDACTED***" in result

    def test_redacts_private_ip(self) -> None:
        f = SanitizingFilter()
        result = f._redact("connecting to 192.168.1.100:5432")
        assert "192.168.1.100" not in result
        assert "***REDACTED_IP***" in result

    def test_preserves_normal_text(self) -> None:
        f = SanitizingFilter()
        result = f._redact("memory-init completed successfully")
        assert result == "memory-init completed successfully"

    def test_filter_modifies_log_record(self) -> None:
        f = SanitizingFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "password=hunter2", (), None)
        f.filter(record)
        assert "hunter2" not in record.msg


class TestGetSanitizedLogger:
    def test_returns_logger_with_filter(self) -> None:
        logger = get_sanitized_logger("test.sanitized")
        filters = [f for f in logger.filters if isinstance(f, SanitizingFilter)]
        assert len(filters) >= 1

    def test_idempotent(self) -> None:
        logger = get_sanitized_logger("test.idempotent")
        count_before = sum(1 for f in logger.filters if isinstance(f, SanitizingFilter))
        get_sanitized_logger("test.idempotent")
        count_after = sum(1 for f in logger.filters if isinstance(f, SanitizingFilter))
        assert count_before == count_after
