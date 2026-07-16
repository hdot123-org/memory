"""Unified telemetry bridge for memory-core.

Provides a centralized, fail-safe channel for reporting analytics events
to PostHog via the PostHogAnalytics singleton in posthog_client.

Key design principles:
- Fail-safe: all methods catch and log exceptions, never propagate
- Data sanitization: full paths are replaced with basename to prevent leaks
- distinct_id uses project_id from project_lifecycle (not hardcoded)
- Event names are prefixed with 'memory.' for namespace clarity
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION, SUPPORTED_HOSTS

# Import now_iso utility (REF-001 §4.8)
try:
    from ._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore

logger = logging.getLogger(__name__)

# PostHog ingestion host remapping (mirrors posthog SDK's determine_server_host).
# PostHog migrated batch ingestion to dedicated i.posthog.com subdomains.
_INGESTION_HOST_MAP = {
    "https://app.posthog.com": "https://us.i.posthog.com",
    "https://us.posthog.com": "https://us.i.posthog.com",
    "https://eu.posthog.com": "https://eu.i.posthog.com",
}

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


def _resolve_ingestion_host(host: str) -> str:
    """Resolve the PostHog ingestion host, mirroring the SDK's determine_server_host.

    PostHog migrated batch ingestion to dedicated i.posthog.com subdomains.
    Sending to the app/dashboard domain (us.posthog.com) can intermittently
    return HTTP 400 Bad Request for batch API calls.

    See: posthog.request.determine_server_host in the posthog SDK.
    """
    return _INGESTION_HOST_MAP.get(host.rstrip("/"), host)


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
    _initialized: bool = False

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
                now_iso_fn=now_iso,
            )
            project_id = record.get("project_id")
            if isinstance(project_id, str) and project_id:
                return project_id
        except Exception as exc:
            logger.debug("telemetry_bridge: project_lifecycle failed, using fallback: %s", exc)
        return _fallback_project_id(Path(cwd) if cwd else None)

    def _capture_error(self, exc: Exception, failed_event: str, method: str) -> None:
        """Emit a memory.error event to PostHog without risking recursion.

        Calls _analytics.capture() directly (NOT safe_capture) to avoid
        infinite recursion when the original failure is persistent.
        Wrapped in its own try/except for double-fail-safe semantics.
        """
        try:
            if self._analytics is None or not self._is_enabled():
                return
            properties = {
                "error_type": type(exc).__name__,
                "error_message": _sanitize_value(str(exc)[:500]),
                "failed_event": failed_event,
                "method": method,
            }
            sanitized_properties = _sanitize_properties(properties)
            self._analytics.capture(
                event_name="memory.error",
                properties=sanitized_properties,
                distinct_id=self.get_project_id(None),
            )
        except Exception:
            logger.debug("telemetry_bridge._capture_error: failed to emit error event")

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
                "timestamp": now_iso(),
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
            self._capture_error(exc, event_name, "safe_capture")

    def batch_capture(
        self,
        events: list[dict[str, Any]],
        cwd: Path | str | None = None,
    ) -> bool:
        """Batch send multiple events to PostHog in a single HTTP request.

        This method builds a batch payload and sends it directly to PostHog's
        batch API endpoint, avoiding per-event SDK overhead.

        Args:
            events: List of event dicts with keys: event_name, properties
            cwd: Optional working directory for project_id resolution

        Returns:
            True if batch send succeeded, False otherwise (HTTP error, exception, or client=None)
        """
        # Check client and enabled state first
        client = self._analytics._client if self._analytics else None
        if client is None or not self._is_enabled() or not events:
            return False

        try:
            # Build batch payload
            distinct_id = self.get_project_id(cwd)
            batch_items = []

            for event_data in events:
                if not isinstance(event_data, dict):
                    continue

                event_name = str(event_data.get("event_name") or "memory.batched_event")
                if not event_name.startswith("memory."):
                    event_name = f"memory.{event_name}"

                properties = event_data.get("properties") or {}
                sanitized = _sanitize_properties(properties)

                # Mirror PostHog SDK _enqueue: add $geoip_disable and $is_server
                # to match the wire format the server expects. Without these,
                # some PostHog API versions reject the batch with HTTP 400.
                enriched: dict[str, Any] = {
                    "memory_core_version": CURRENT_MEMORY_VERSION,
                    "host": _resolve_host(),
                    "$geoip_disable": True,
                    "$is_server": True,
                    **sanitized,
                }

                # Top-level timestamp is required by the PostHog batch API.
                # The SDK's _enqueue always adds it; omitting it can trigger 400.
                item_timestamp = datetime.now(timezone.utc).isoformat()

                batch_items.append({
                    "event": event_name,
                    "properties": enriched,
                    "distinct_id": distinct_id,
                    "timestamp": item_timestamp,
                    "uuid": str(__import__("uuid").uuid4()),
                })

            if not batch_items:
                return False

            # Direct HTTP POST to PostHog batch API using stdlib
            import urllib.error
            import urllib.request

            # Resolve ingestion host (mirrors SDK's determine_server_host)
            raw_host = os.environ.get("POSTHOG_HOST", "https://us.posthog.com").strip()
            host = _resolve_ingestion_host(raw_host)
            api_key = client.api_key

            batch_url = f"{host}/batch/"
            headers = {"Content-Type": "application/json"}
            payload = json.dumps({
                "api_key": api_key,
                "batch": batch_items,
                "sentAt": now_iso(),
            }).encode("utf-8")

            # Send with retry for transient failures (timeouts, 5xx, 429).
            # Matches SDK defaults: 15s timeout, up to 2 retries with exponential backoff.
            max_retries = 2
            for attempt in range(max_retries + 1):
                req = urllib.request.Request(
                    batch_url, data=payload, headers=headers, method="POST"
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as response:
                        response.read()  # Consume full response
                    logger.debug(
                        "telemetry_bridge.batch_capture: sent %d events", len(batch_items)
                    )
                    return True

                except urllib.error.HTTPError as http_exc:
                    # Read response body for diagnostics (str(HTTPError) omits it)
                    body_text = ""
                    try:
                        body_text = http_exc.read().decode(
                            "utf-8", errors="replace"
                        )[:300]
                    except Exception:
                        pass

                    # Retry on 429 (rate limit) and 5xx (server errors)
                    should_retry = http_exc.code == 429 or http_exc.code >= 500
                    if should_retry and attempt < max_retries:
                        logger.debug(
                            "telemetry_bridge.batch_capture: HTTP %d, retrying %d/%d",
                            http_exc.code, attempt + 1, max_retries,
                        )
                        time.sleep(2 ** attempt)
                        continue

                    # Non-retryable or exhausted retries: enrich message with body
                    if body_text:
                        http_exc.msg = f"{http_exc.msg} [body: {body_text}]"
                    logger.debug(
                        "telemetry_bridge.batch_capture: HTTP error: %s", http_exc
                    )
                    self._capture_error(http_exc, "batch", "batch_capture")
                    return False

                except urllib.error.URLError as url_exc:
                    # Network-level error (timeout, DNS, connection refused)
                    if attempt < max_retries:
                        logger.debug(
                            "telemetry_bridge.batch_capture: URLError, retrying %d/%d: %s",
                            attempt + 1, max_retries, url_exc,
                        )
                        time.sleep(2 ** attempt)
                        continue
                    logger.debug(
                        "telemetry_bridge.batch_capture: exhausted retries: %s", url_exc
                    )
                    self._capture_error(url_exc, "batch", "batch_capture")
                    return False

            return False  # Should not reach here, but safety net

        except Exception as exc:
            # Analytics must never break the host application flow
            logger.debug("telemetry_bridge.batch_capture failed: %s", exc)
            self._capture_error(exc, "batch", "batch_capture")
            return False

    def flush(self) -> None:
        """Flush pending analytics events."""
        if self._analytics is None:
            return
        try:
            self._analytics.shutdown()
        except Exception as exc:
            logger.debug("telemetry_bridge.flush failed: %s", exc)
            self._capture_error(exc, "flush", "flush")


# Module-level singleton
telemetry = TelemetryBridge()
