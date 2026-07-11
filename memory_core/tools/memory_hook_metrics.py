"""Observability metrics for memory-hook-gateway.

Emits structured JSONL metrics to memory/artifacts/memory-hook/metrics.jsonl after
each gateway invocation. Disabled via MEMORY_HOOK_METRICS_DISABLED=1.

Failure is non-blocking: callers should wrap emit_metrics in try/except.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

METRICS_FILENAME = "metrics.jsonl"
ENV_DISABLE = "MEMORY_HOOK_METRICS_DISABLED"
ENV_METRICS_PATH = "MEMORY_HOOK_METRICS_PATH"


def is_metrics_disabled() -> bool:
    return os.environ.get(ENV_DISABLE) == "1"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _package_size_bytes(package: dict[str, Any]) -> int:
    try:
        return len(json.dumps(package, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def collect_metrics(
    host: str,
    event: str,
    package: dict[str, Any],
    now_iso: str | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    """Extract observability metrics from a context-package.

    Returns a flat dict ready for JSONL serialization. Never raises.
    """
    if not isinstance(package, dict):
        package = {}
    status = str(package.get("status", "unknown"))
    validation_errors = package.get("validation_errors") or []
    missing_paths = package.get("missing_paths") or []
    system_context = package.get("system_context") or {}
    core_provider = ""
    if isinstance(system_context, dict):
        core_provider = str(system_context.get("core_provider", ""))
    return {
        "timestamp": now_iso or _now_iso(),
        "host": str(host),
        "event": str(event),
        "status": status,
        "context_package_size_bytes": _package_size_bytes(package),
        "validation_error_count": len(validation_errors) if isinstance(validation_errors, list) else 0,
        "missing_paths_count": len(missing_paths) if isinstance(missing_paths, list) else 0,
        "degraded": status != "ok",
        "core_provider": core_provider,
        "package_kind": str(package.get("package_kind", "")),
        "duration_ms": duration_ms,
    }


def _resolve_metrics_path(artifact_root: Path) -> Path:
    override = os.environ.get(ENV_METRICS_PATH)
    if override:
        return Path(override).expanduser()
    return Path(artifact_root) / METRICS_FILENAME


def write_metrics(metrics_path: Path, record: dict[str, Any]) -> bool:
    """Append a metrics record as one JSONL line. Returns True on success."""
    try:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return True
    except OSError as exc:
        _logger.debug("metrics write failed: %s", exc)
        return False


def emit_metrics(
    artifact_root: Path,
    host: str,
    event: str,
    package: dict[str, Any],
    duration_ms: int = 0,
) -> Path | None:
    """Collect + write metrics. Non-blocking; returns None when disabled or on failure."""
    if is_metrics_disabled():
        return None
    try:
        record = collect_metrics(host, event, package, duration_ms=duration_ms)
        path = _resolve_metrics_path(artifact_root)
        if write_metrics(path, record):
            return path
        return None
    except Exception as exc:  # pragma: no cover - defensive
        _logger.debug("emit_metrics skipped: %s", exc)
        return None
