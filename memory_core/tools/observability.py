"""Lightweight observability utilities for memory-core.

Provides request tracing, metrics collection, and error tracking
without external SaaS dependencies.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TraceContext:
    """Simple request/context trace with unique ID propagation."""
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.start_time) * 1000

    def child_span(self, **meta: Any) -> TraceContext:
        return TraceContext(
            trace_id=self.trace_id,
            parent_span_id=self.span_id,
            metadata={**self.metadata, **meta},
        )

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
    """Simple in-memory timing metrics."""
    name: str
    _timings: list[float] = field(default_factory=list)

    def time(self, duration_ms: float) -> None:
        self._timings.append(duration_ms)

    def measure(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.monotonic()
        result = func(*args, **kwargs)
        self._timings.append((time.monotonic() - start) * 1000)
        return result

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
    """Central metrics registry for the application."""

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


# Global instances
metrics = MetricsRegistry()
error_tracker = ErrorTracker()
