#!/usr/bin/env python3
"""Tests for VAL-TEL-004 and VAL-TEL-005: gateway main() records non-zero duration_ms.

VAL-TEL-004: Gateway main() records duration_ms > 0 in emitted metrics
VAL-TEL-005: Gateway duration_ms reflects actual execution time
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def _setup_gateway_mocks(gw, monkeypatch, tmp_path, emit_fn, build_fn=None):
    """Set up all mocks needed for main() to reach emit_metrics. Uses monkeypatch for cleanup."""
    pkg = {
        "status": "ok",
        "missing_paths": [],
        "validation_errors": [],
        "host": "factory",
        "event": "session-start",
        "package_kind": "context-package-v1",
    }
    if build_fn is None:
        build_fn = lambda *a, **kw: pkg  # noqa: E731

    # Mock stdin/argv/stdout
    mock_stdin = MagicMock()
    mock_stdin.read.return_value = "{}"
    monkeypatch.setattr(sys, "stdin", mock_stdin)
    monkeypatch.setattr(sys, "argv", ["gw", "--host", "factory", "--event", "session-start", "--no-delegate"])
    monkeypatch.setattr(sys, "stdout", MagicMock())

    # Mock gateway module attributes
    monkeypatch.setattr(gw, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(gw, "is_memory_core_source_repo", lambda cwd: True)
    monkeypatch.setattr(gw, "get_source_repo_mode", lambda cwd: "develop")
    monkeypatch.setattr(gw, "is_denied_project_root", lambda cwd: False)
    monkeypatch.setattr(gw, "_should_noop_for_external_context", lambda payload: False)
    monkeypatch.setattr(gw, "_discover_cwd", lambda payload: tmp_path)
    monkeypatch.setattr(gw, "determine_project_scope", lambda cwd: "default")
    monkeypatch.setattr(gw, "build_context_package", build_fn)
    mock_writer = MagicMock()
    mock_writer.write.return_value = True
    monkeypatch.setattr(gw, "ArtifactWriter", lambda *a, **kw: mock_writer)
    monkeypatch.setattr(gw, "_integrity_verify", lambda cwd: None)
    monkeypatch.setattr(gw, "_integrity_sign", lambda cwd: None)
    monkeypatch.setattr(gw, "_execute_delegate", lambda *a, **kw: 0)
    monkeypatch.setattr(gw, "_launch_async_health_check", lambda cwd: None)
    monkeypatch.setattr(gw, "_update_state_dynamic_fields", lambda *a, **kw: None)
    monkeypatch.setattr(gw, "_maybe_sync_telemetry", lambda *a, **kw: None)
    monkeypatch.setattr(gw, "_log_prompt_submit", lambda *a, **kw: None)

    # Patch emit_metrics using monkeypatch for reliable cleanup
    from memory_core.tools import memory_hook_metrics
    monkeypatch.setattr(memory_hook_metrics, "emit_metrics", emit_fn)


def test_gateway_main_records_nonzero_duration_ms(tmp_path, monkeypatch):
    """VAL-TEL-004: Gateway main() records duration_ms > 0 in emitted metrics."""
    from memory_core.tools import memory_hook_gateway as gw

    captured_records = []

    def fake_emit(artifact_root, host, event, package, duration_ms=0):
        captured_records.append({"duration_ms": duration_ms, "host": host, "event": event})
        return None

    _setup_gateway_mocks(gw, monkeypatch, tmp_path, fake_emit)
    gw.main()

    # VAL-TEL-004: duration_ms should be > 0
    assert len(captured_records) == 1, f"Expected 1 emit call, got {len(captured_records)}"
    assert captured_records[0]["duration_ms"] > 0, (
        f"duration_ms should be > 0, got {captured_records[0]['duration_ms']}"
    )


def test_gateway_duration_ms_reflects_actual_time(tmp_path, monkeypatch):
    """VAL-TEL-005: duration_ms reflects actual execution time, not hardcoded."""
    from memory_core.tools import memory_hook_gateway as gw

    captured_records = []

    def fake_emit(artifact_root, host, event, package, duration_ms=0):
        captured_records.append({"duration_ms": duration_ms})
        return None

    # Run 1: fast (small sleep for reliable timing)
    def fast_build(*args, **kwargs):
        time.sleep(0.01)  # 10ms sleep
        return {
            "status": "ok", "missing_paths": [], "validation_errors": [],
            "host": "factory", "event": "session-start", "package_kind": "context-package-v1",
        }
    _setup_gateway_mocks(gw, monkeypatch, tmp_path, fake_emit, build_fn=fast_build)
    gw.main()
    fast_duration = captured_records[0]["duration_ms"]

    # Run 2: slow (add sleep inside build_context_package)
    captured_records.clear()

    def slow_build(*args, **kwargs):
        time.sleep(0.15)  # 150ms sleep
        return {
            "status": "ok", "missing_paths": [], "validation_errors": [],
            "host": "factory", "event": "session-start", "package_kind": "context-package-v1",
        }

    _setup_gateway_mocks(gw, monkeypatch, tmp_path, fake_emit, build_fn=slow_build)
    gw.main()
    slow_duration = captured_records[0]["duration_ms"]

    # VAL-TEL-005: slow run should have larger duration_ms than fast run
    assert slow_duration > fast_duration, (
        f"Slow run ({slow_duration}ms) should have larger duration_ms than fast run ({fast_duration}ms)"
    )
    # Slow run should be at least 100ms (since we sleep 150ms)
    assert slow_duration >= 100, f"Slow run should be >= 100ms, got {slow_duration}ms"
    # fast_duration can be 0 if execution is very fast (< 1ms), but slow_duration must be > 0
    assert slow_duration > 0, f"Slow run duration_ms should be > 0, got {slow_duration}"


def test_gateway_excepthook_includes_duration_ms_and_status(tmp_path, monkeypatch):
    """VAL-TEL-004 supplement: _gateway_excepthook records include duration_ms and status."""
    from memory_core.tools import memory_hook_gateway as gw

    monkeypatch.setattr(gw, "ARTIFACT_ROOT", tmp_path)

    metrics_file = tmp_path / "metrics.jsonl"

    # Simulate the excepthook being called
    try:
        raise ValueError("test error for excepthook")
    except ValueError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        gw._gateway_excepthook(exc_type, exc_value, exc_tb)

    assert metrics_file.exists(), "metrics.jsonl should be written by excepthook"
    line = metrics_file.read_text().strip()
    record = json.loads(line)

    # Verify duration_ms and status fields exist
    assert "duration_ms" in record, f"excepthook record should have duration_ms, got keys: {list(record.keys())}"
    assert "status" in record, f"excepthook record should have status, got keys: {list(record.keys())}"
    assert record["event"] == "hook_error"
    assert record["error_type"] == "ValueError"
