# -*- coding: utf-8 -*-
"""Unit tests for _rule_errors.py exception hierarchy."""

import pytest

from memory_core.tools._rule_errors import (
    MemoryCoreError,
    UnknownHostError,
    UnknownRouteKindError,
    UnsupportedScopeError,
)


def test_memory_core_error_base():
    """Test MemoryCoreError is base exception."""
    error = MemoryCoreError("test error")
    assert str(error) == "test error"
    assert isinstance(error, Exception)


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
        raise UnsupportedScopeError("msg")

    with pytest.raises(MemoryCoreError):
        raise UnknownHostError("msg")

    with pytest.raises(MemoryCoreError):
        raise UnknownRouteKindError("msg")


def test_all_exceptions_importable():
    """Test all 4 exception classes are importable."""
    from memory_core.tools._rule_errors import (
        MemoryCoreError,
        UnknownHostError,
        UnknownRouteKindError,
        UnsupportedScopeError,
    )

    assert MemoryCoreError is not None
    assert UnsupportedScopeError is not None
    assert UnknownHostError is not None
    assert UnknownRouteKindError is not None
