# -*- coding: utf-8 -*-
"""Unit tests for _rule_errors.py exception hierarchy."""
from __future__ import annotations

import pytest

from memory_core.tools._rule_errors import (
    GuardBlockError,
    MemoryCoreError,
    OwnershipError,
    PolicyViolationError,
    RuleViolationError,
    UnknownHostError,
    UnknownRouteKindError,
    UnsupportedScopeError,
)


def test_memory_core_error_base():
    """Test MemoryCoreError is base exception."""
    error = MemoryCoreError("test error")
    assert str(error) == "test error"
    assert isinstance(error, Exception)


def test_rule_violation_error():
    """Test RuleViolationError with rule name and details."""
    error = RuleViolationError(
        rule_name="test_rule",
        message="validation failed",
        detail={"field": "value"},
    )
    assert error.rule_name == "test_rule"
    assert error.detail == {"field": "value"}
    assert "test_rule" in str(error)
    assert "validation failed" in str(error)
    assert isinstance(error, MemoryCoreError)


def test_rule_violation_error_default_detail():
    """Test RuleViolationError default detail is empty dict."""
    error = RuleViolationError(rule_name="test", message="msg")
    assert error.detail == {}


def test_ownership_error():
    """Test OwnershipError is a MemoryCoreError."""
    error = OwnershipError("path violation")
    assert isinstance(error, MemoryCoreError)
    assert str(error) == "path violation"


def test_guard_block_error():
    """Test GuardBlockError with tool and reason."""
    error = GuardBlockError(tool="rm", reason="forbidden", path="/tmp/file")
    assert error.tool == "rm"
    assert error.reason == "forbidden"
    assert error.path == "/tmp/file"
    assert "rm" in str(error)
    assert "forbidden" in str(error)
    assert isinstance(error, MemoryCoreError)


def test_guard_block_error_default_path():
    """Test GuardBlockError default path is empty string."""
    error = GuardBlockError(tool="test", reason="blocked")
    assert error.path == ""


def test_policy_violation_error():
    """Test PolicyViolationError is a MemoryCoreError."""
    error = PolicyViolationError("policy failed")
    assert isinstance(error, MemoryCoreError)
    assert str(error) == "policy failed"


def test_unsupported_scope_error():
    """Test UnsupportedScopeError replaces ValueError."""
    error = UnsupportedScopeError("unknown scope")
    assert isinstance(error, MemoryCoreError)
    assert str(error) == "unknown scope"


def test_unknown_host_error():
    """Test UnknownHostError replaces ValueError."""
    error = UnknownHostError("unknown host")
    assert isinstance(error, MemoryCoreError)
    assert str(error) == "unknown host"


def test_unknown_route_kind_error():
    """Test UnknownRouteKindError replaces ValueError."""
    error = UnknownRouteKindError("unknown route kind")
    assert isinstance(error, MemoryCoreError)
    assert str(error) == "unknown route kind"


def test_exception_hierarchy():
    """Test all exceptions inherit from MemoryCoreError."""
    exceptions = [
        RuleViolationError("test", "msg"),
        OwnershipError("msg"),
        GuardBlockError("tool", "reason"),
        PolicyViolationError("msg"),
        UnsupportedScopeError("msg"),
        UnknownHostError("msg"),
        UnknownRouteKindError("msg"),
    ]

    for exc in exceptions:
        assert isinstance(exc, MemoryCoreError)
        assert isinstance(exc, Exception)


def test_can_catch_base_exception():
    """Test catching MemoryCoreError catches all subclasses."""
    with pytest.raises(MemoryCoreError):
        raise RuleViolationError("test", "msg")

    with pytest.raises(MemoryCoreError):
        raise GuardBlockError("tool", "reason")


def test_all_exceptions_importable():
    """Test all 7 exception classes are importable."""
    from memory_core.tools._rule_errors import (
        GuardBlockError,
        MemoryCoreError,
        OwnershipError,
        PolicyViolationError,
        RuleViolationError,
        UnknownHostError,
        UnknownRouteKindError,
        UnsupportedScopeError,
    )

    assert MemoryCoreError is not None
    assert RuleViolationError is not None
    assert OwnershipError is not None
    assert GuardBlockError is not None
    assert PolicyViolationError is not None
    assert UnsupportedScopeError is not None
    assert UnknownHostError is not None
    assert UnknownRouteKindError is not None
