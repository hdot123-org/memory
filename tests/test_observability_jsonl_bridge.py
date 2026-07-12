"""Tests for observability.py → JSONL metrics bridge.

Verifies that MetricsTimer, TraceContext, and MetricsRegistry
write timing/trace data to the JSONL metrics pipeline.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def metrics_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up a temp JSONL metrics path and ensure metrics are enabled."""
    path = tmp_path / "metrics.jsonl"
    monkeypatch.setenv("MEMORY_HOOK_METRICS_PATH", str(path))
    monkeypatch.delenv("MEMORY_HOOK_METRICS_DISABLED", raising=False)
    return path


def read_records(path: Path) -> list[dict]:
    """Read JSONL records from a metrics file."""
    text = path.read_text().strip()
    if not text:
        return []
    return [json.loads(line) for line in text.split("\n") if line.strip()]


class TestMetricsTimerJSONL:
    """MetricsTimer should write timing data to JSONL on __exit__."""

    def test_timer_context_manager_writes_jsonl(self, metrics_path: Path) -> None:
        from memory_core.tools.observability import MetricsTimer

        timer = MetricsTimer("test_op")
        with timer:
            time.sleep(0.01)

        records = read_records(metrics_path)
        assert len(records) >= 1, "Expected at least one JSONL record from MetricsTimer"

        timer_records = [r for r in records if r.get("metric_type") == "timer"]
        assert len(timer_records) >= 1, "Expected a timer-type record"

        rec = timer_records[0]
        assert rec["name"] == "test_op"
        assert rec["elapsed_ms"] > 0, "elapsed_ms should be positive"
        assert "timestamp" in rec, "Record should have a timestamp"

    def test_timer_measure_also_writes_jsonl(self, metrics_path: Path) -> None:
        from memory_core.tools.observability import MetricsTimer

        timer = MetricsTimer("measure_op")
        result = timer.measure(lambda: 42)

        assert result == 42
        records = read_records(metrics_path)
        timer_records = [r for r in records if r.get("metric_type") == "timer"]
        assert len(timer_records) >= 1
        assert timer_records[0]["name"] == "measure_op"
        assert timer_records[0]["elapsed_ms"] >= 0

    def test_timer_disabled_no_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from memory_core.tools.observability import MetricsTimer

        path = tmp_path / "metrics.jsonl"
        monkeypatch.setenv("MEMORY_HOOK_METRICS_PATH", str(path))
        monkeypatch.setenv("MEMORY_HOOK_METRICS_DISABLED", "1")

        timer = MetricsTimer("noop")
        with timer:
            time.sleep(0.01)

        # When disabled, no file should be created (or empty)
        if path.exists():
            assert path.read_text().strip() == "", "Disabled metrics should produce no output"

    def test_timer_disabled_then_enabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ensure disabled flag is checked at write time, not import time."""
        from memory_core.tools.observability import MetricsTimer

        path = tmp_path / "metrics.jsonl"
        monkeypatch.setenv("MEMORY_HOOK_METRICS_PATH", str(path))
        monkeypatch.setenv("MEMORY_HOOK_METRICS_DISABLED", "1")

        t1 = MetricsTimer("disabled_op")
        with t1:
            pass

        # Now enable
        monkeypatch.delenv("MEMORY_HOOK_METRICS_DISABLED", raising=False)
        t2 = MetricsTimer("enabled_op")
        with t2:
            time.sleep(0.01)

        records = read_records(path)
        names = [r.get("name") for r in records if r.get("metric_type") == "timer"]
        assert "disabled_op" not in names
        assert "enabled_op" in names


class TestTraceContextJSONL:
    """TraceContext should write span data to JSONL."""

    def test_record_span_writes_jsonl(self, metrics_path: Path) -> None:
        from memory_core.tools.observability import TraceContext

        ctx = TraceContext()
        time.sleep(0.01)
        ctx.record_span("db_query")

        records = read_records(metrics_path)
        assert len(records) >= 1

        span_records = [r for r in records if r.get("metric_type") == "trace_span"]
        assert len(span_records) >= 1, "Expected a trace_span record"

        rec = span_records[0]
        assert rec["trace_id"] == ctx.trace_id
        assert rec["span_name"] == "db_query"
        assert rec["elapsed_ms"] >= 0
        assert "timestamp" in rec

    def test_child_span_inherits_trace_id(
        self, metrics_path: Path
    ) -> None:
        from memory_core.tools.observability import TraceContext

        parent = TraceContext()
        child = parent.child_span(operation="validate")
        time.sleep(0.01)
        child.record_span("validation_step")

        records = read_records(metrics_path)
        span_records = [r for r in records if r.get("metric_type") == "trace_span"]
        assert len(span_records) >= 1
        assert span_records[0]["trace_id"] == parent.trace_id

    def test_trace_disabled_no_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from memory_core.tools.observability import TraceContext

        path = tmp_path / "metrics.jsonl"
        monkeypatch.setenv("MEMORY_HOOK_METRICS_PATH", str(path))
        monkeypatch.setenv("MEMORY_HOOK_METRICS_DISABLED", "1")

        ctx = TraceContext()
        ctx.record_span("should_not_appear")

        if path.exists():
            assert path.read_text().strip() == ""


class TestMetricsRegistryJSONL:
    """MetricsRegistry.publish() should emit collected metrics to JSONL."""

    def test_publish_writes_timer_metrics(self, metrics_path: Path) -> None:
        from memory_core.tools.observability import MetricsRegistry

        registry = MetricsRegistry()
        timer = registry.timer("db_query")
        timer.time(5.0)
        timer.time(10.0)

        registry.publish()

        records = read_records(metrics_path)
        assert len(records) >= 1

        timer_records = [r for r in records if r.get("metric_type") == "timer"]
        assert len(timer_records) >= 1
        timer_rec = timer_records[0]
        assert timer_rec["name"] == "db_query"
        assert timer_rec["count"] == 2
        assert timer_rec["avg_ms"] == 7.5

    def test_publish_writes_counter_metrics(self, metrics_path: Path) -> None:
        from memory_core.tools.observability import MetricsRegistry

        registry = MetricsRegistry()
        counter = registry.counter("http_requests")
        counter.inc("GET", 5)
        counter.inc("POST", 3)

        registry.publish()

        records = read_records(metrics_path)
        counter_records = [r for r in records if r.get("metric_type") == "counter"]
        assert len(counter_records) >= 1
        assert counter_records[0]["name"] == "http_requests"
        assert counter_records[0]["counts"] == {"GET": 5, "POST": 3}

    def test_publish_empty_registry_no_output(self, metrics_path: Path) -> None:
        from memory_core.tools.observability import MetricsRegistry

        registry = MetricsRegistry()
        registry.publish()

        # Empty registry should produce no records
        if metrics_path.exists():
            assert metrics_path.read_text().strip() == ""

    def test_publish_disabled_no_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from memory_core.tools.observability import MetricsRegistry

        path = tmp_path / "metrics.jsonl"
        monkeypatch.setenv("MEMORY_HOOK_METRICS_PATH", str(path))
        monkeypatch.setenv("MEMORY_HOOK_METRICS_DISABLED", "1")

        registry = MetricsRegistry()
        registry.timer("t1").time(5.0)
        registry.publish()

        if path.exists():
            assert path.read_text().strip() == ""
