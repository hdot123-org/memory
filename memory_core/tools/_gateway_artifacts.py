#!/usr/bin/env python3.12
"""Gateway 工件层：artifact 写入与错误日志。

依赖层级：依赖 _gateway_config。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ._gateway_config import (
    ERROR_LOG,
    EVENT_LOG,
    CONTEXT_ROOT,
    _logger,
    now_iso,
    _get_artifact_sink,
    _get_error_sink,
)


def _ensure_artifact_dirs() -> None:
    try:
        _get_artifact_sink().ensure_dirs()
    except RuntimeError:
        CONTEXT_ROOT.mkdir(parents=True, exist_ok=True)


def append_error_log(component: str, message: str, context: dict[str, Any]) -> None:
    """Append error to error log with fallback to direct file write."""
    try:
        sink = _get_error_sink()
        sink.log(component, message, context)
    except RuntimeError:
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        timestamp = now_iso()
        day = timestamp[:10]
        daily_error_log = ERROR_LOG.parent / "errors" / f"{day}.log"
        daily_error_log.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(context, ensure_ascii=False, sort_keys=True)
        line = f"[{timestamp}] [{component}] [error] {message} | context={rendered}\n"
        with daily_error_log.open("a", encoding="utf-8") as handle:
            handle.write(line)
        with ERROR_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line)


def write_artifacts(package: dict[str, Any]) -> dict[str, str]:
    """Write context package artifacts with fallback to direct file write."""
    from ._gateway_policy import _write_artifacts_via_sink
    try:
        return _write_artifacts_via_sink(package)
    except RuntimeError:
        _ensure_artifact_dirs()
        now = datetime.now()
        day = now.date().isoformat()
        timestamp = now.strftime("%Y%m%dT%H%M%S%f")
        daily_context_root = CONTEXT_ROOT / day
        daily_context_root.mkdir(parents=True, exist_ok=True)
        snapshot_path = daily_context_root / f"{timestamp}-{package['host']}-{package['event']}.json"
        suffix = 1
        while snapshot_path.exists():
            snapshot_path = daily_context_root / f"{timestamp}-{suffix:02d}-{package['host']}-{package['event']}.json"
            suffix += 1
        latest_path = CONTEXT_ROOT / f"latest-{package['host']}-{package['event']}.json"
        daily_latest_path = daily_context_root / f"latest-{package['host']}-{package['event']}.json"
        daily_event_log = EVENT_LOG.parent / "events" / f"{day}.jsonl"
        package["artifact_refs"] = {
            "snapshot": str(snapshot_path),
            "latest": str(latest_path),
            "daily_latest": str(daily_latest_path),
            "event_log": str(daily_event_log),
            "legacy_event_log": str(EVENT_LOG),
        }
        rendered = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
        snapshot_path.write_text(rendered, encoding="utf-8")
        latest_path.write_text(rendered, encoding="utf-8")
        daily_latest_path.write_text(rendered, encoding="utf-8")
        event_line = json.dumps(package, ensure_ascii=False) + "\n"
        daily_event_log.parent.mkdir(parents=True, exist_ok=True)
        with daily_event_log.open("a", encoding="utf-8") as handle:
            handle.write(event_line)
        with EVENT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(event_line)
        return {"snapshot": str(snapshot_path), "latest": str(latest_path), "event_log": str(daily_event_log)}
