#!/usr/bin/env python3.12
"""Gateway 遥测层：PostHog 指标同步与 backoff 状态管理。

依赖层级：依赖 _gateway_config（REPO_ROOT/WORKSPACE_ROOT 等常量不在此模块使用，
但 _logger 与 now_iso/exclusive_lock 来自基础工具）。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

try:
    from ._file_utils import exclusive_lock, now_iso
except ImportError:
    from _file_utils import exclusive_lock, now_iso  # type: ignore

_logger = logging.getLogger(__name__)

# Batch size for telemetry sync
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Timestamp / backoff helpers
# ---------------------------------------------------------------------------


def _read_sync_timestamp(file_path: Path) -> float:
    """Read timestamp from file, returning 0.0 on any error."""
    if not file_path.exists():
        return 0.0
    try:
        return float(file_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0.0


def _should_skip_sync(now: float, last_success: float, last_attempt: float) -> bool:
    """Check if sync should be skipped based on backoff windows."""
    # Skip if within 1-hour success window
    if (now - last_success) < 3600:
        return True
    # Skip if within 5-minute backoff after recent attempt
    return (now - last_attempt) < 300


# ---------------------------------------------------------------------------
# Network / PostHog helpers
# ---------------------------------------------------------------------------


def _normalize_posthog_host() -> str:
    """Normalize PostHog host URL to ingestion endpoint and extract hostname."""
    posthog_host = os.environ.get("POSTHOG_HOST", "https://us.posthog.com").strip()
    _trimmed = posthog_host.rstrip("/")
    if _trimmed in ("https://app.posthog.com", "https://us.posthog.com"):
        posthog_host = "https://us.i.posthog.com"
    elif _trimmed == "https://eu.posthog.com":
        posthog_host = "https://eu.i.posthog.com"
    # Extract hostname from URL
    if "://" in posthog_host:
        return posthog_host.split("://", 1)[1].rstrip("/")
    return posthog_host.rstrip("/")


def _probe_posthog_network(hostname: str) -> bool:
    """Probe network connectivity to PostHog host. Returns True if reachable."""
    try:
        sock = socket.create_connection((hostname, 443), timeout=2)
        sock.close()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Metrics reading / sending
# ---------------------------------------------------------------------------


def _read_pending_records(metrics_file: Path, offset: int) -> list[tuple[int, dict[str, Any]]]:
    """Read incremental records from metrics.jsonl starting after offset.

    Returns list of (line_number, record) tuples to handle blank/malformed lines.
    """
    records_with_lines = []
    current_line = 0
    with metrics_file.open("r", encoding="utf-8") as f:
        for line in f:
            current_line += 1
            if current_line <= offset:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    records_with_lines.append((current_line, record))
            except json.JSONDecodeError:
                continue
    return records_with_lines


def _batch_send_records(
    records_with_lines: list[tuple[int, dict[str, Any]]],
    batch_size: int,
    offset_file: Path,
) -> tuple[int, int]:
    """Batch send records via telemetry_bridge. Returns (synced_count, last_synced_line)."""
    from memory_core.tools.telemetry_bridge import telemetry

    synced_records = 0
    last_synced_line = 0

    for chunk_start in range(0, len(records_with_lines), batch_size):
        chunk = records_with_lines[chunk_start : chunk_start + batch_size]
        events = []
        for _line_num, record in chunk:
            event_name = str(record.get("event") or "memory.replayed_event")
            events.append({"event_name": event_name, "properties": {**record}})

        chunk_success = telemetry.batch_capture(events)
        if not chunk_success:
            break  # stop on first failure

        synced_records += len(chunk)
        last_synced_line = chunk[-1][0]
        offset_file.write_text(str(last_synced_line), encoding="utf-8")

    return synced_records, last_synced_line


def _compact_metrics_jsonl(
    metrics_file: Path, last_synced_line: int, offset_file: Path
) -> None:
    """Compact metrics.jsonl after successful sync, keeping only unsent records."""
    try:
        remaining_lines = []
        with metrics_file.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                if line_num > last_synced_line:
                    remaining_lines.append(line)

        with metrics_file.open("w", encoding="utf-8") as f, exclusive_lock(f):
            f.writelines(remaining_lines)
            f.flush()
            os.fsync(f.fileno())

        offset_file.write_text("0", encoding="utf-8")
    except OSError as exc:
        _logger.debug("metrics.jsonl compaction failed: %s", exc)


# ---------------------------------------------------------------------------
# Sync outcome / status
# ---------------------------------------------------------------------------


def _write_sync_status(
    artifact_root: Path, success: bool, pending_count: int
) -> None:
    """Write .sync_status.json with lifecycle tracking fields."""
    status_file = artifact_root / ".sync_status.json"
    now_iso_val = now_iso()

    status: dict[str, Any] = {}
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = {}

    if success:
        status["last_success_ts"] = now_iso_val
        status["failure_count"] = 0
    else:
        status["last_failure_ts"] = now_iso_val
        status["failure_count"] = int(status.get("failure_count", 0)) + 1

    status["pending_count"] = pending_count

    try:
        status_file.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        _logger.warning("Failed to write sync status to %s: %s", status_file, exc)
        print(
            f"Warning: failed to write sync status to {status_file}: {exc}",
            file=sys.stderr,
        )


def _record_sync_outcome(
    artifact_root: Path,
    success: bool,
    pending_count: int,
    now: float,
    attempt_file: Path,
) -> None:
    """Record sync outcome: update timestamps and write status."""
    if success:
        success_file = artifact_root / ".last_sync_success"
        with contextlib.suppress(OSError):
            success_file.write_text(str(now), encoding="utf-8")
    else:
        with contextlib.suppress(OSError):
            attempt_file.write_text(str(now), encoding="utf-8")
    _write_sync_status(artifact_root, success, pending_count)


# ---------------------------------------------------------------------------
# Top-level sync entry
# ---------------------------------------------------------------------------


def _maybe_sync_telemetry(artifact_root: Path) -> None:
    """Synchronize local telemetry metrics to PostHog during session-start.

    Implements a lightweight sync mechanism with separate backoff for failures:
    1. Check .last_sync_success; skip if < 3600s ago (hourly sync window)
    2. Check .last_sync_attempt; skip if < 300s ago (short backoff after failure)
    3. Probe network connectivity to PostHog host (socket timeout=2s)
    4. If probe fails, update .last_sync_attempt and exit
    5. If probe succeeds, read .offset sidecar and incremental records from metrics.jsonl
    6. Batch send via telemetry_bridge.batch_capture (passes all record fields)
    7. On success: update .offset and .last_sync_success, compact metrics.jsonl
       On failure: update .last_sync_attempt (not .offset, retry next time)
    8. Write .sync_status.json with lifecycle tracking fields
    9. All operations wrapped in try/except (exceptions never propagate)

    Args:
        artifact_root: Path to the artifacts directory containing metrics.jsonl
    """
    try:
        metrics_file = artifact_root / "metrics.jsonl"
        last_sync_success_file = artifact_root / ".last_sync_success"
        last_sync_attempt_file = artifact_root / ".last_sync_attempt"
        offset_file = artifact_root / ".offset"

        # Step 1-2: Check backoff windows
        now = time.time()
        last_sync_success = _read_sync_timestamp(last_sync_success_file)
        last_sync_attempt = _read_sync_timestamp(last_sync_attempt_file)

        if _should_skip_sync(now, last_sync_success, last_sync_attempt):
            return

        # Step 3: Probe network connectivity
        posthog_hostname = _normalize_posthog_host()
        if not _probe_posthog_network(posthog_hostname):
            _record_sync_outcome(artifact_root, False, 0, now, last_sync_attempt_file)
            return

        # Step 4: Read offset and incremental records
        if not metrics_file.exists():
            return

        offset = 0
        if offset_file.exists():
            try:
                offset = int(offset_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                offset = 0

        records_with_lines = _read_pending_records(metrics_file, offset)
        if not records_with_lines:
            return

        pending_count = len(records_with_lines)

        # Step 5-8: Batch send and handle outcome
        try:
            synced_count, last_synced_line = _batch_send_records(
                records_with_lines, BATCH_SIZE, offset_file
            )

            all_synced = synced_count == len(records_with_lines)
            if all_synced:
                _record_sync_outcome(artifact_root, True, 0, now, last_sync_attempt_file)
                _compact_metrics_jsonl(metrics_file, last_synced_line, offset_file)
            else:
                remaining = len(records_with_lines) - synced_count
                _record_sync_outcome(
                    artifact_root, False, remaining, now, last_sync_attempt_file
                )

        except Exception as exc:
            _logger.debug("telemetry sync send failed: %s", exc)
            _record_sync_outcome(
                artifact_root, False, pending_count, now, last_sync_attempt_file
            )

    except Exception as exc:
        # Top-level catch: sync must never break gateway flow
        _logger.debug("_maybe_sync_telemetry failed: %s", exc)


# ---------------------------------------------------------------------------
# Prompt-submit logging helpers
# ---------------------------------------------------------------------------


def _read_last_user_message_from_transcript(transcript_path: str | None) -> str | None:
    """Read last user message from transcript file."""
    if not transcript_path:
        return None
    path = Path(transcript_path)
    if not path.exists():
        return None
    try:
        last_user: str | None = None
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("role") == "user":
                    content = entry.get("content", "")
                    if isinstance(content, str) and content:
                        last_user = content
        return last_user
    except OSError:
        return None


def _sanitize_for_log(text: str, max_len: int = 2000) -> str:
    """Sanitize text for logging (truncate and escape)."""
    try:
        from ._redaction import redact as _shared_redact
    except ImportError:
        from _redaction import redact as _shared_redact  # type: ignore
    return _shared_redact(text, max_len=max_len)


def _log_prompt_submit(project_root: Path, payload: dict[str, Any]) -> None:
    """Log prompt-submit event to session file."""
    import signal
    import re
    from datetime import datetime
    
    class HookTimeoutError(Exception):
        pass
    
    session_id: str = payload.get("session_id", "unknown")
    transcript_path: str | None = payload.get("transcript_path")
    
    prompt: str | None = payload.get("prompt")
    if not prompt:
        prompt = _read_last_user_message_from_transcript(transcript_path)
    if not prompt:
        prompt = "(no prompt captured)"
    
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    session_prefix = session_id[:8]
    
    log_dir = project_root / "memory" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{date_str}-sessions.md"
    
    prompt_count = 1
    if log_file.exists():
        try:
            content = log_file.read_text(encoding="utf-8")
            pattern = re.compile(rf"#### [^\n]+— {re.escape(session_prefix)} \[?heartbeat")
            matches = pattern.findall(content)
            prompt_count = len(matches) + 1
        except OSError:
            pass
    
    preview = _sanitize_for_log(prompt)[:100]
    
    heartbeat = (
        f"#### {time_str} — {session_prefix} [heartbeat]\n"
        f"- **用户消息**: {preview}\n"
        f"- **累计 prompt 数**: {prompt_count}\n"
        "---\n"
    )
    
    def _write_handler(_signum, _frame):
        raise HookTimeoutError("prompt-submit log write timed out")
    
    old_handler = None
    try:
        old_handler = signal.signal(signal.SIGALRM, _write_handler)
        signal.alarm(2)
        
        with log_file.open("a", encoding="utf-8") as fh, exclusive_lock(fh):
            fh.write(heartbeat)
            fh.flush()
    except HookTimeoutError:
        _logger.warning("_log_prompt_submit: write timed out for session %s", session_prefix)
    finally:
        signal.alarm(0)
        if old_handler is not None:
            signal.signal(signal.SIGALRM, old_handler)
