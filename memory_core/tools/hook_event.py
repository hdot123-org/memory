"""HookEvent — unified event normalization for Codex/Claude dual-host memory hooks.

This module provides:
- ``HookEvent`` dataclass: canonical event representation across hosts.
- ``from_codex_payload`` / ``from_claude_payload``: parsers for each host's raw input.
- ``to_context_package_input``: converts a HookEvent into the dict shape expected
  by the gateway's ``build_context_package(host, event, payload)``.
- ``parse_hook_event``: single-entry dispatcher that picks the right parser by host.

Claude event name mapping:
    SessionStart     → session-start
    UserPromptSubmit → prompt-submit
    Notification     → notification
    Stop             → stop

Codex event names are already in the canonical form (--event CLI arg).
"""


import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Import domain exceptions (REF-001 §4.8)
try:
    from memory_core.tools._rule_errors import UnknownHostError
except ImportError:
    from ._rule_errors import UnknownHostError

# Import now_iso utility (REF-001 §4.8)
try:
    from memory_core.tools._file_utils import now_iso
except ImportError:
    from ._file_utils import now_iso

# ---------------------------------------------------------------------------
# Claude event name mapping
# ---------------------------------------------------------------------------

_CLAUDE_EVENT_MAP: dict[str, str] = {
    "SessionStart": "session-start",
    "UserPromptSubmit": "prompt-submit",
    "Notification": "notification",
    "Stop": "stop",
}

_VALID_EVENT_TYPES = {"session-start", "prompt-submit", "notification", "stop"}


# ---------------------------------------------------------------------------
# HookEvent dataclass
# ---------------------------------------------------------------------------

@dataclass
class HookEvent:
    """Normalized hook event produced by either Codex or Claude host."""

    source: str  # "codex" | "claude"
    event_type: str  # "session-start" | "prompt-submit" | "notification" | "stop"
    payload: dict[str, Any]
    cwd: Path
    timestamp: str  # ISO format
    project_scope: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_now_iso = now_iso


def _parse_json(raw: str) -> dict[str, Any]:
    """Safely parse raw JSON string into a dict; empty string → {}."""
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {"payload": loaded}


def _extract_cwd(payload: dict[str, Any]) -> Path | None:
    """Extract cwd from payload if present and valid."""
    value = payload.get("cwd")
    if isinstance(value, str) and value:
        return Path(value).expanduser()
    return None


def _map_claude_event(raw_event: str) -> str:
    """Map Claude native event name to canonical gateway event type."""
    return _CLAUDE_EVENT_MAP.get(raw_event, raw_event)


def _is_valid_event_type(event_type: str) -> bool:
    return event_type in _VALID_EVENT_TYPES


# ---------------------------------------------------------------------------
# Public constructors
# ---------------------------------------------------------------------------

def from_codex_payload(raw: str, event: str = "", cwd: Path | None = None, source: str = "codex") -> HookEvent:
    """Parse a Codex-like hook invocation into a HookEvent.

    Args:
        raw: Raw stdin JSON payload from the host.
        event: Event type from --event CLI arg (already canonical).
        cwd: Optional cwd override; falls back to payload cwd or current dir.
        source: Normalized host label for the resulting HookEvent.
    """
    payload = _parse_json(raw)
    event_type = event or payload.get("event", "prompt-submit")
    if not _is_valid_event_type(event_type):
        event_type = "prompt-submit"

    resolved_cwd = cwd or _extract_cwd(payload) or Path.cwd()

    return HookEvent(
        source=source,
        event_type=event_type,
        payload=payload,
        cwd=resolved_cwd,
        timestamp=_now_iso(),
    )


def from_claude_payload(raw: str, cwd: Path | None = None) -> HookEvent:
    """Parse a Claude hook invocation into a HookEvent.

    Claude payloads may include an ``event`` field with the native event name
    (e.g. ``"SessionStart"``). This is mapped to the canonical event type.

    Args:
        raw: Raw stdin JSON payload from Claude.
        cwd: Optional cwd override; falls back to payload cwd or current dir.
    """
    payload = _parse_json(raw)
    raw_event = payload.get("event", "")
    event_type = _map_claude_event(raw_event) if raw_event else "prompt-submit"
    if not _is_valid_event_type(event_type):
        event_type = "prompt-submit"

    resolved_cwd = cwd or _extract_cwd(payload) or Path.cwd()

    return HookEvent(
        source="claude",
        event_type=event_type,
        payload=payload,
        cwd=resolved_cwd,
        timestamp=_now_iso(),
    )


# ---------------------------------------------------------------------------
# Output conversion
# ---------------------------------------------------------------------------

def to_context_package_input(event: HookEvent) -> dict[str, Any]:
    """Convert a HookEvent into the (host, event, payload) dict for gateway calls.

    The returned dict is compatible with:
        build_context_package(host, event, payload)

    Both Codex and Claude HookEvents produce the same output structure.
    """
    return {
        "host": event.source,
        "event": event.event_type,
        "payload": event.payload,
        "cwd": str(event.cwd),
    }


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def parse_hook_event(host: str, event: str, raw_payload: str) -> HookEvent:
    """Parse a raw hook invocation into a HookEvent.

    Only factory is supported (INV-6).

    Args:
        host: "factory".
        event: Event type string.
        raw_payload: Raw JSON string from stdin.

    Returns:
        A normalized HookEvent.

    Raises:
        UnknownHostError: If host is not "factory".
    """
    if host == "factory":
        return from_codex_payload(raw_payload, event=event, source="factory")
    else:
        raise UnknownHostError(f"unknown host: {host!r}")
