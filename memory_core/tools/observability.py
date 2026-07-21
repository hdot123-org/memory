"""Lightweight observability utilities for memory-core.

Provides request tracing, metrics collection, and error tracking
without external SaaS dependencies.

MetricsTimer, TraceContext, and MetricsRegistry bridge timing/trace data
to the JSONL metrics pipeline via append_metrics_record.
"""

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Import now_iso utility (REF-001 §4.8)
try:
    from ._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore

logger = logging.getLogger(__name__)


def _is_metrics_disabled() -> bool:
    """Check if metrics emission is disabled via env var."""
    return os.environ.get("MEMORY_HOOK_METRICS_DISABLED") == "1"


def _resolve_jsonl_path(artifact_root: Path | None) -> Path:
    """Resolve the JSONL metrics file path.

    Uses MEMORY_HOOK_METRICS_PATH env var if set, otherwise
    falls back to artifact_root / metrics.jsonl.
    """
    override = os.environ.get("MEMORY_HOOK_METRICS_PATH")
    if override:
        return Path(override).expanduser()
    if artifact_root is not None:
        return artifact_root / "metrics.jsonl"
    return Path.cwd() / "memory" / "artifacts" / "memory-hook" / "metrics.jsonl"


def _emit_to_jsonl(record: dict[str, Any], artifact_root: Path | None = None) -> None:
    """Write a record to the JSONL metrics file. Non-blocking; never raises."""
    if _is_metrics_disabled():
        return
    try:
        from memory_core.tools.memory_hook_metrics import append_metrics_record
        path = _resolve_jsonl_path(artifact_root)
        append_metrics_record(path, record)
    except Exception as exc:
        logger.debug("observability JSONL emit skipped: %s", exc)


_now_iso = now_iso


@dataclass
class TraceContext:
    """Request trace with JSONL bridge.

    Creates a trace context with unique IDs. Calling record_span()
    writes the span's timing data to the JSONL metrics pipeline.
    """
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.start_time) * 1000

    def child_span(self, **meta: Any) -> "TraceContext":
        return TraceContext(
            trace_id=self.trace_id,
            parent_span_id=self.span_id,
            metadata={**self.metadata, **meta},
        )

    def record_span(self, span_name: str) -> None:
        """Record this span's timing to JSONL metrics."""
        if _is_metrics_disabled():
            return
        record = {
            "metric_type": "trace_span",
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "span_name": span_name,
            "elapsed_ms": round(self.elapsed_ms(), 3),
            "timestamp": _now_iso(),
            **self.metadata,
        }
        _emit_to_jsonl(record)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "elapsed_ms": round(self.elapsed_ms(), 2),
            **self.metadata,
        }


@dataclass
class MetricsCounter:
    """Simple in-memory metrics counter."""
    name: str
    _counts: dict[str, int] = field(default_factory=dict)

    def inc(self, label: str = "default", value: int = 1) -> None:
        self._counts[label] = self._counts.get(label, 0) + value

    def get(self, label: str = "default") -> int:
        return self._counts.get(label, 0)

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)


@dataclass
class MetricsTimer:
    """In-memory timing metrics with JSONL bridge.

    Can be used as a context manager to automatically record timing:
        with MetricsTimer("operation_name") as timer:
            do_work()
        # Automatically writes to JSONL on exit

    Or used directly:
        timer = MetricsTimer("operation_name")
        timer.measure(some_func)
        # Writes to JSONL after each measurement
    """
    name: str
    _timings: list[float] = field(default_factory=list)
    _start: float = field(default=0.0, init=False, repr=False)

    def time(self, duration_ms: float) -> None:
        self._timings.append(duration_ms)

    def measure(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.monotonic()
        result = func(*args, **kwargs)
        elapsed_ms = (time.monotonic() - start) * 1000
        self._timings.append(elapsed_ms)
        self._emit_to_jsonl(elapsed_ms)
        return result

    def __enter__(self) -> "MetricsTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type: Any, _exc_val: Any, exc_tb: Any) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        self._timings.append(elapsed_ms)
        self._emit_to_jsonl(elapsed_ms)

    def _emit_to_jsonl(self, elapsed_ms: float) -> None:
        if _is_metrics_disabled():
            return
        record = {
            "metric_type": "timer",
            "name": self.name,
            "elapsed_ms": round(elapsed_ms, 3),
            "timestamp": _now_iso(),
        }
        _emit_to_jsonl(record)

    def stats(self) -> dict[str, float]:
        if not self._timings:
            return {"count": 0, "avg_ms": 0, "min_ms": 0, "max_ms": 0}
        return {
            "count": len(self._timings),
            "avg_ms": round(sum(self._timings) / len(self._timings), 2),
            "min_ms": round(min(self._timings), 2),
            "max_ms": round(max(self._timings), 2),
        }


class MetricsRegistry:
    """Central metrics registry with JSONL publish.

    Accumulates counters and timers, then publishes them to JSONL.
    """

    def __init__(self) -> None:
        self._counters: dict[str, MetricsCounter] = {}
        self._timers: dict[str, MetricsTimer] = {}

    def counter(self, name: str) -> MetricsCounter:
        if name not in self._counters:
            self._counters[name] = MetricsCounter(name)
        return self._counters[name]

    def timer(self, name: str) -> MetricsTimer:
        if name not in self._timers:
            self._timers[name] = MetricsTimer(name)
        return self._timers[name]

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": {n: c.snapshot() for n, c in self._counters.items()},
            "timers": {n: t.stats() for n, t in self._timers.items()},
        }

    def publish(self) -> None:
        """Emit all collected metrics to JSONL."""
        if _is_metrics_disabled():
            return

        # Publish counters
        for name, counter in self._counters.items():
            counts = counter.snapshot()
            if counts:
                record = {
                    "metric_type": "counter",
                    "name": name,
                    "counts": counts,
                    "timestamp": _now_iso(),
                }
                _emit_to_jsonl(record)

        # Publish timers
        for name, timer in self._timers.items():
            stats = timer.stats()
            if stats["count"] > 0:
                timer_record: dict[str, Any] = {
                    "metric_type": "timer",
                    "name": name,
                    "count": stats["count"],
                    "avg_ms": stats["avg_ms"],
                    "min_ms": stats["min_ms"],
                    "max_ms": stats["max_ms"],
                    "timestamp": _now_iso(),
                }
                _emit_to_jsonl(timer_record)

        # Clear after publishing
        self._counters.clear()
        self._timers.clear()


class ErrorTracker:
    """Simple error tracker that logs structured error events."""

    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = log_path
        self._errors: list[dict[str, Any]] = []

    def capture(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> str:
        error_id = hashlib.sha256(f"{time.time()}{error}".encode()).hexdigest()[:12]
        entry = {
            "error_id": error_id,
            "type": type(error).__name__,
            "message": str(error),
            "trace_id": trace_id,
            "context": context or {},
            "timestamp": time.time(),
        }
        self._errors.append(entry)
        logger.error("error_id=%s type=%s message=%s", error_id, type(error).__name__, error)

        if self._log_path:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")

        return error_id

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._errors[-limit:]


