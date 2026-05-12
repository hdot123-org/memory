#!/usr/bin/env python3
"""Tests for async health check observability (P2 fix).

Verifies that _launch_async_health_check writes structured failure records
when Popen fails (e.g., due to OSError, FileNotFoundError, etc.).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools import memory_hook_gateway as gateway


def test_launch_async_health_check_popen_failure_writes_structured_error(
    tmp_path: Path, monkeypatch
):
    """When subprocess.Popen raises, a structured failure record should be written."""
    # Create a fake cwd with memory/system structure
    cwd = tmp_path / "project"
    report_path = cwd / "memory" / "system" / "health-report.json"

    # Mock Popen to raise an exception
    def mock_popen(*args, **kwargs):
        raise OSError("No such file or directory: 'python'")

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # Call the function
    gateway._launch_async_health_check(cwd)

    # Verify the failure record was written
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["launch_status"] == "failed"
    assert "last_launch_error" in report
    assert "No such file or directory" in report["last_launch_error"]
    assert report["status"] == "error"
    assert "checked_at" in report


def test_launch_async_health_check_popen_failure_writes_to_error_log_on_write_failure(
    tmp_path: Path, monkeypatch, capsys
):
    """When health report write fails, error should be logged via append_error_log."""
    cwd = tmp_path / "project"
    _ = cwd / "memory" / "system" / "health-report.json"  # Path exists but will fail to write

    # Mock Popen to raise
    def mock_popen(*args, **kwargs):
        raise FileNotFoundError("python not found")

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # Mock Path.write_text to raise
    original_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if "health-report" in str(self):
            raise PermissionError("cannot write to system dir")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    # Track append_error_log calls
    error_logs = []
    original_append_error_log = gateway.append_error_log

    def track_append_error_log(component, message, context):
        error_logs.append({"component": component, "message": message, "context": context})
        return original_append_error_log(component, message, context)

    monkeypatch.setattr(gateway, "append_error_log", track_append_error_log)

    # Ensure ERROR_LOG directory exists
    error_log_dir = tmp_path / "memory" / "system"
    error_log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(gateway, "ERROR_LOG", error_log_dir / "errors.log")

    # Call the function
    gateway._launch_async_health_check(cwd)

    # Verify error log was called
    assert len(error_logs) == 1
    log = error_logs[0]
    assert log["component"] == "memory-hook-gateway"
    assert "failed to launch async health check" in log["message"]
    assert "cannot write to system dir" in log["context"].get("write_error", "")
    assert "python not found" in log["context"].get("launch_error", "")


def test_launch_async_health_check_success_does_not_write_failure(
    tmp_path: Path, monkeypatch
):
    """When Popen succeeds, no failure record should be written."""
    cwd = tmp_path / "project"
    report_path = cwd / "memory" / "system" / "health-report.json"

    # Track Popen calls
    popen_calls = []

    class MockPopen:
        def __init__(self, *args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(subprocess, "Popen", MockPopen)

    # Call the function
    gateway._launch_async_health_check(cwd)

    # Verify Popen was called
    assert len(popen_calls) == 1
    # Verify no failure report exists (since we mocked Popen to succeed)
    assert not report_path.exists()


def test_launch_async_health_check_includes_checked_at_timestamp(
    tmp_path: Path, monkeypatch
):
    """Failure record should include a valid ISO timestamp."""
    cwd = tmp_path / "project"
    report_path = cwd / "memory" / "system" / "health-report.json"

    # Mock Popen to raise
    def mock_popen(*args, **kwargs):
        raise subprocess.SubprocessError("subprocess failed")

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # Call the function
    gateway._launch_async_health_check(cwd)

    # Verify the timestamp
    report = json.loads(report_path.read_text())
    assert "checked_at" in report
    assert len(report["checked_at"]) > 10  # Should be a valid ISO timestamp
    assert "T" in report["checked_at"]
