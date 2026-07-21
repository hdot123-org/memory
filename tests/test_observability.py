"""Tests for observability utilities."""

import time

from memory_core.tools.observability import (
    ErrorTracker,
    MetricsCounter,
    MetricsRegistry,
    MetricsTimer,
    TraceContext,
)


class TestTraceContext:
    def test_unique_trace_id(self) -> None:
        t1 = TraceContext()
        t2 = TraceContext()
        assert t1.trace_id != t2.trace_id

    def test_child_span(self) -> None:
        parent = TraceContext()
        child = parent.child_span(operation="validate")
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id
        assert child.metadata["operation"] == "validate"

    def test_elapsed_ms(self) -> None:
        ctx = TraceContext()
        ctx.start_time = time.monotonic() - 0.1  # 100ms ago
        assert ctx.elapsed_ms() > 90

    def test_to_dict(self) -> None:
        ctx = TraceContext(trace_id="abc123")
        d = ctx.to_dict()
        assert d["trace_id"] == "abc123"
        assert "elapsed_ms" in d


class TestMetricsCounter:
    def test_increment(self) -> None:
        c = MetricsCounter("requests")
        c.inc("ok")
        c.inc("ok")
        c.inc("error")
        assert c.get("ok") == 2
        assert c.get("error") == 1

    def test_snapshot(self) -> None:
        c = MetricsCounter("ops")
        c.inc("a", 5)
        assert c.snapshot() == {"a": 5}


class TestMetricsTimer:
    def test_stats_empty(self) -> None:
        t = MetricsTimer("latency")
        assert t.stats()["count"] == 0

    def test_measure(self) -> None:
        t = MetricsTimer("latency")
        t.measure(lambda: 42)
        assert t.stats()["count"] == 1
        assert t.stats()["avg_ms"] >= 0


class TestMetricsRegistry:
    def test_counter(self) -> None:
        r = MetricsRegistry()
        c = r.counter("http_requests")
        c.inc("GET")
        snap = r.snapshot()
        assert "http_requests" in snap["counters"]

    def test_timer(self) -> None:
        r = MetricsRegistry()
        t = r.timer("db_query")
        t.time(5.0)
        snap = r.snapshot()
        assert "db_query" in snap["timers"]


class TestErrorTracker:
    def test_capture(self) -> None:
        tracker = ErrorTracker()
        error_id = tracker.capture(ValueError("test error"), context={"step": "init"})
        assert len(error_id) == 12
        assert len(tracker.recent()) == 1
        assert tracker.recent()[0]["type"] == "ValueError"

    def test_recent_limit(self) -> None:
        tracker = ErrorTracker()
        for i in range(20):
            tracker.capture(RuntimeError(f"err-{i}"))
        assert len(tracker.recent(limit=5)) == 5
