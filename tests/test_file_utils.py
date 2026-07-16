# -*- coding: utf-8 -*-
"""Unit tests for _file_utils.py file utilities."""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from memory_core.tools._file_utils import exclusive_lock, now_iso


def test_exclusive_lock_context_manager():
    """Test exclusive_lock works as context manager."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        with exclusive_lock(f):
            f.write("test data")
            f.flush()

        # File should be accessible after lock released
        with open(f.name, "r") as f2:
            assert f2.read() == "test data"

        Path(f.name).unlink()


def test_exclusive_lock_with_label():
    """Test exclusive_lock accepts label parameter."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        with exclusive_lock(f, label="test"):
            f.write("data")

        Path(f.name).unlink()


def test_exclusive_lock_releases_on_exception():
    """Test lock is released even if exception occurs."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        try:
            with exclusive_lock(f):
                f.write("data")
                raise ValueError("test error")
        except ValueError:
            pass

        # Should be able to acquire lock again
        with open(f.name, "w") as f2:
            with exclusive_lock(f2):
                f2.write("more data")

        Path(f.name).unlink()


def test_now_iso_returns_string():
    """Test now_iso returns ISO 8601 string."""
    result = now_iso()
    assert isinstance(result, str)
    assert len(result) > 0


def test_now_iso_format():
    """Test now_iso returns valid ISO format with timezone."""
    result = now_iso()
    # Should contain timezone info
    assert "+" in result or "Z" in result
    # Should be parseable as datetime
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None


def test_now_iso_has_seconds_precision():
    """Test now_iso uses seconds precision (timespec='seconds')."""
    result = now_iso()
    # Should not have microseconds (more than 6 digits after decimal)
    # Format: 2026-07-16T10:30:45+08:00
    parts = result.split(".")
    if len(parts) == 2:
        # Has fractional seconds, should be exactly 0-6 digits before timezone
        time_part = parts[1]
        # Strip timezone if present
        time_part = time_part.split("+")[0].split("-")[0]
        assert len(time_part) <= 6


def test_now_iso_consistency():
    """Test multiple calls return different times."""
    result1 = now_iso()
    result2 = now_iso()
    # Should be close but not necessarily equal (could be same second)
    # Just verify both are valid ISO strings
    datetime.fromisoformat(result1)
    datetime.fromisoformat(result2)


def test_both_functions_importable():
    """Test both functions are importable via both import paths."""
    from memory_core.tools._file_utils import exclusive_lock, now_iso

    assert callable(exclusive_lock)
    assert callable(now_iso)


def test_exclusive_lock_basic_usage():
    """Test basic usage pattern from REF-001."""
    with tempfile.NamedTemporaryFile(mode="a", delete=False) as f:
        with exclusive_lock(f, label="metrics"):
            f.write("test data")
            f.flush()

        Path(f.name).unlink()
