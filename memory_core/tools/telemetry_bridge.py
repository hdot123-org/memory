"""Unified telemetry bridge for memory-core.

Provides a centralized, fail-safe channel for reporting analytics events
to PostHog via the PostHogAnalytics singleton in posthog_client.

Key design principles:
- Fail-safe: all methods catch and log exceptions, never propagate
- Data sanitization: full paths are replaced with basename to prevent leaks
- distinct_id uses project_id from project_lifecycle (not hardcoded)
- Event names are prefixed with 'memory.' for namespace clarity
- atexit-registered flush ensures pending events are sent on process exit
"""
from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION, SUPPORTED_HOSTS

logger = logging.getLogger(__name__)

# Keys that likely contain file system paths and should be sanitized
_PATH_KEY_FRAGMENTS = ("path", "file", "cwd", "dir", "root")


def _looks_like_path_key(key: str) -> bool:
    """Return True if the key name suggests its value may be a file path."""
    lowered = key.lower()
    return any(fragment in lowered for fragment in _PATH_KEY_FRAGMENTS)


def _sanitize_value(value: Any) -> Any:
    """Replace string values that look like absolute paths with their basename."""
    if not isinstance(value, str):
        return value
    if not value:
        return value
    try:
        as_path = Path(value)
        # Check both POSIX absolute, current OS separator, and Windows drive letter
        is_abs = as_path.is_absolute() or os.sep in value or (len(value) >= 3 and value[1] == ':' and value[2] in ('\\', '/'))
        if is_abs:
            # Use PureWindowsPath for Windows-style paths to get correct basename
            if '\\' in value:
                from pathlib import PureWindowsPath
                return PureWindowsPath(value).name
            return as_path.name
    except (OSError, ValueError):
        pass
    return value


def _sanitize_properties(properties: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of properties with path-like values replaced by basenames."""
    if not properties:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in properties.items():
        if _looks_like_path_key(key):
            sanitized[key] = _sanitize_value(value)
        else:
            sanitized[key] = value
    return sanitized


def _resolve_host() -> str:
    """Resolve the current host identifier (factory, or hostname fallback)."""
    env_host = os.environ.get("MEMORY_HOST", "").strip()
    if env_host and env_host in SUPPORTED_HOSTS:
        return env_host
    return socket.gethostname() or "unknown"


def _fallback_project_id(cwd: Path | None) -> str:
    """Generate a deterministic project_id from the directory name when lifecycle fails."""
    if cwd is None:
        try:
            cwd = Path.cwd()
        except OSError:
            return "unknown-project"
    name = cwd.expanduser().name or "unknown-project"
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    safe_name = "".join(ch if ch.isalnum() else "-" for ch in name).strip("-").lower() or "unknown"
    return f"{safe_name}-{digest}"


class TelemetryBridge:
    """Singleton telemetry bridge.

    Wraps PostHogAnalytics with project-aware distinct_id, data sanitization,
    automatic common properties, and fail-safe semantics.
    """

    _instance: TelemetryBridge | None = None

    def __new__(cls) -> TelemetryBridge:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._analytics = None
        try:
            from memory_core.tools.posthog_client import analytics
            self._analytics = analytics
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("telemetry_bridge: posthog_client unavailable: %s", exc)

    def _is_enabled(self) -> bool:
        """Return True when the underlying analytics client is enabled."""
        if self._analytics is None:
            return False
        return bool(getattr(self._analytics, "_enabled", False))

    def get_project_id(self, cwd: Path | str | None = None) -> str:
        """Resolve a stable project_id for the given working directory.

        Attempts project_lifecycle.build_project_lifecycle_record(); falls back
        to a deterministic hash of the directory name on any failure.
        """
        try:
            from memory_core.tools.project_lifecycle import build_project_lifecycle_record

            path = Path(cwd).expanduser() if cwd else Path.cwd()
            record = build_project_lifecycle_record(
                cwd=path,
                host=_resolve_host(),
                event="telemetry_resolve_id",
                payload={"cwd": str(path)},
                now_iso_fn=lambda: datetime.now().astimezone().isoformat(timespec="seconds"),
            )
            project_id = record.get("project_id")
            if isinstance(project_id, str) and project_id:
                return project_id
        except Exception as exc:
            logger.debug("telemetry_bridge: project_lifecycle failed, using fallback: %s", exc)
        return _fallback_project_id(Path(cwd) if cwd else None)

    def safe_capture(
        self,
        event_name: str,
        properties: dict[str, Any] | None = None,
        cwd: Path | str | None = None,
    ) -> None:
        """Capture an event with sanitization and automatic common properties.

        Fail-safe: never raises. No-op when analytics is disabled.
        Event name is automatically prefixed with 'memory.' if not already.
        """
        if not self._is_enabled() or self._analytics is None:
            return

        try:
            final_event = event_name if event_name.startswith("memory.") else f"memory.{event_name}"

            sanitized = _sanitize_properties(properties)

            distinct_id = self.get_project_id(cwd)

            enriched: dict[str, Any] = {
                "memory_core_version": CURRENT_MEMORY_VERSION,
                "host": _resolve_host(),
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                **sanitized,
            }

            self._analytics.capture(
                event_name=final_event,
                properties=enriched,
                distinct_id=distinct_id,
            )
        except Exception as exc:
            # Analytics must never break the host application flow
            logger.debug("telemetry_bridge.safe_capture failed for '%s': %s", event_name, exc)

    def replay_unsent(self, metrics_path: Path | str) -> int:
        """Replay unsent metrics records from a JSONL file using a sidecar offset.

        The sidecar offset file is ``<metrics_path>.offset`` and stores the number
        of lines already processed. Records must contain a JSON-serializable
        payload; each record is forwarded to ``safe_capture`` as
        ``memory.replayed_event``.

        Returns the number of records successfully replayed. Always fail-safe.
        """
        try:
            path = Path(metrics_path).expanduser()
            if not path.exists():
                return 0

            offset_path = path.with_suffix(path.suffix + ".offset")
            last_offset = 0
            if offset_path.exists():
                try:
                    last_offset = int(offset_path.read_text(encoding="utf-8").strip())
                except (OSError, ValueError):
                    last_offset = 0

            replayed = 0
            current_line = 0
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    current_line += 1
                    if current_line <= last_offset:
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    if record.get("posthog_sent") is True:
                        continue

                    event_name = str(record.get("event") or "replayed_event")
                    props = {
                        "replayed_from": path.name,
                        "original_status": record.get("status"),
                        "original_event": record.get("event"),
                        "original_host": record.get("host"),
                        "original_timestamp": record.get("timestamp"),
                    }
                    self.safe_capture(event_name, props)
                    replayed += 1

            try:
                offset_path.write_text(str(current_line), encoding="utf-8")
            except OSError as exc:
                logger.debug("telemetry_bridge: offset write failed: %s", exc)

            return replayed
        except Exception as exc:
            logger.debug("telemetry_bridge.replay_unsent failed: %s", exc)
            return 0

    def flush(self) -> None:
        """Flush pending analytics events. Registered with atexit."""
        if self._analytics is None:
            return
        try:
            self._analytics.shutdown()
        except Exception as exc:
            logger.debug("telemetry_bridge.flush failed: %s", exc)


# Module-level singleton
telemetry = TelemetryBridge()

# Ensure pending events are flushed on process exit
atexit.register(telemetry.flush)
