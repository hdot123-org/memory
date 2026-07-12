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
from unittest.mock import MagicMock, patch

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def _run_gateway_main(gw, tmp_path, emit_fn, build_fn=None):
    """Run gateway main() with all necessary mocks, calling emit_fn for emit_metrics."""
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

    original_stdin = sys.stdin
    original_argv = sys.argv
    original_stdout = sys.stdout
    # Save original gateway functions
    orig_attrs = {}
    try:
        sys.stdin = MagicMock()
        sys.stdin.read.return_value = "{}"
        sys.argv = ["gw", "--host", "factory", "--event", "session-start", "--no-delegate"]
        sys.stdout = MagicMock()

        gw.ARTIFACT_ROOT = tmp_path
        # Save and monkeypatch gateway functions
        for attr in ["is_memory_core_source_repo", "get_source_repo_mode", "is_denied_project_root",
                     "_should_noop_for_external_context", "build_context_package", "write_artifacts",
                     "_integrity_verify", "_integrity_sign", "_execute_delegate",
                     "_launch_async_health_check", "_update_state_dynamic_fields",
                     "_maybe_sync_telemetry", "_log_prompt_submit"]:
            orig_attrs[attr] = getattr(gw, attr)

        gw.is_memory_core_source_repo = lambda cwd: True
        gw.get_source_repo_mode = lambda cwd: "develop"
        gw.is_denied_project_root = lambda cwd: False
        gw._should_noop_for_external_context = lambda payload: False
        gw.build_context_package = build_fn
        gw.write_artifacts = lambda package: {"snapshot": "x"}
        gw._integrity_verify = lambda cwd: None
        gw._integrity_sign = lambda cwd: None
        gw._execute_delegate = lambda *a, **kw: 0
        gw._launch_async_health_check = lambda cwd: None
        gw._update_state_dynamic_fields = lambda *a, **kw: None
        gw._maybe_sync_telemetry = lambda *a, **kw: None
        gw._log_prompt_submit = lambda *a, **kw: None

        # Patch emit_metrics in the memory_hook_metrics module so the
        # `from .memory_hook_metrics import emit_metrics` inside main() gets our fake.
        from memory_core.tools import memory_hook_metrics
        original_emit = memory_hook_metrics.emit_metrics
        memory_hook_metrics.emit_metrics = emit_fn
        try:
            return gw.main()
        finally:
            memory_hook_metrics.emit_metrics = original_emit
    finally:
        sys.stdin = original_stdin
        sys.argv = original_argv
        sys.stdout = original_stdout
        # Restore original gateway functions
        for attr, val in orig_attrs.items():
            setattr(gw, attr, val)


def test_gateway_main_records_nonzero_duration_ms(tmp_path, monkeypatch):
    """VAL-TEL-004: Gateway main() records duration_ms > 0 in emitted metrics."""
    from memory_core.tools import memory_hook_gateway as gw

    captured_records = []

    def fake_emit(artifact_root, host, event, package, duration_ms=0):
        captured_records.append({"duration_ms": duration_ms, "host": host, "event": event})
        return None

    _run_gateway_main(gw, tmp_path, fake_emit)

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
    _run_gateway_main(gw, tmp_path, fake_emit, build_fn=fast_build)
    fast_duration = captured_records[0]["duration_ms"]

    # Run 2: slow (add sleep inside build_context_package)
    captured_records.clear()

    def slow_build(*args, **kwargs):
        time.sleep(0.15)  # 150ms sleep
        return {
            "status": "ok", "missing_paths": [], "validation_errors": [],
            "host": "factory", "event": "session-start", "package_kind": "context-package-v1",
        }

    _run_gateway_main(gw, tmp_path, fake_emit, build_fn=slow_build)
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
        with patch.object(sys, "__excepthook__"):  # Don't actually print traceback
            gw._gateway_excepthook(exc_type, exc_value, exc_tb)

    assert metrics_file.exists(), "metrics.jsonl should be written by excepthook"
    line = metrics_file.read_text().strip()
    record = json.loads(line)

    # Verify duration_ms and status fields exist
    assert "duration_ms" in record, f"excepthook record should have duration_ms, got keys: {list(record.keys())}"
    assert "status" in record, f"excepthook record should have status, got keys: {list(record.keys())}"
    assert record["event"] == "hook_error"
    assert record["error_type"] == "ValueError"
