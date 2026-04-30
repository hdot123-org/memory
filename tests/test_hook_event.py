"""Tests for workspace/tools/hook_event.py — HookEvent normalization.

Covers:
- from_codex_payload: parsing Codex raw JSON into HookEvent
- from_claude_payload: parsing Claude raw JSON with event name mapping
- to_context_package_input: output structure consistency
- parse_hook_event: unified entry point dispatch
- Edge cases: empty payload, invalid JSON, unknown event types
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "memory_core" / "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from hook_event import (
    HookEvent,
    from_codex_payload,
    from_claude_payload,
    to_context_package_input,
    parse_hook_event,
    _CLAUDE_EVENT_MAP,
    _VALID_EVENT_TYPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_codex_payload(repo_root) -> str:
    return json.dumps({
        "session_id": "codex-session-001",
        "cwd": str(repo_root),
        "message": "Hello world",
    })


@pytest.fixture
def sample_claude_session_start(repo_root) -> str:
    return json.dumps({
        "event": "SessionStart",
        "session_id": "claude-session-001",
        "cwd": str(repo_root),
        "model": "claude-sonnet-4-20250514",
    })


@pytest.fixture
def sample_claude_prompt_submit() -> str:
    return json.dumps({
        "event": "UserPromptSubmit",
        "session_id": "claude-session-002",
        "cwd": "/Users/busiji/project",
        "user_message": "Fix the bug",
    })


# ---------------------------------------------------------------------------
# 1. from_codex_payload tests
# ---------------------------------------------------------------------------

class TestFromCodexPayload:

    def test_basic_parse(self, sample_codex_payload, repo_root):
        event = from_codex_payload(sample_codex_payload, event="session-start")
        assert event.source == "codex"
        assert event.event_type == "session-start"
        assert event.payload["session_id"] == "codex-session-001"
        assert event.cwd == repo_root

    def test_default_event_when_not_provided(self, sample_codex_payload):
        event = from_codex_payload(sample_codex_payload)
        assert event.event_type == "prompt-submit"

    def test_event_from_cli_overrides_payload(self, sample_codex_payload):
        # CLI event should take precedence
        event = from_codex_payload(sample_codex_payload, event="stop")
        assert event.event_type == "stop"

    def test_cwd_from_payload(self):
        raw = json.dumps({"cwd": "/tmp/test"})
        event = from_codex_payload(raw, event="notification")
        assert event.cwd == Path("/tmp/test")

    def test_cwd_override(self):
        raw = json.dumps({"cwd": "/tmp/ignored"})
        event = from_codex_payload(raw, event="session-start", cwd=Path("/override"))
        assert event.cwd == Path("/override")

    def test_empty_payload(self):
        event = from_codex_payload("", event="session-start")
        assert event.source == "codex"
        assert event.event_type == "session-start"
        assert event.payload == {}

    def test_invalid_json(self):
        event = from_codex_payload("not json {{{", event="prompt-submit")
        assert event.payload == {}
        assert event.source == "codex"

    def test_non_dict_json_wrapped(self):
        raw = json.dumps([1, 2, 3])
        event = from_codex_payload(raw, event="notification")
        assert event.payload == {"payload": [1, 2, 3]}

    def test_invalid_event_type_defaults(self):
        raw = json.dumps({})
        event = from_codex_payload(raw, event="unknown-event")
        assert event.event_type == "prompt-submit"

    def test_timestamp_is_iso(self, sample_codex_payload):
        event = from_codex_payload(sample_codex_payload, event="session-start")
        assert event.timestamp
        # Should be parseable as ISO
        from datetime import datetime
        datetime.fromisoformat(event.timestamp)

    def test_all_event_types(self):
        for et in _VALID_EVENT_TYPES:
            event = from_codex_payload("{}", event=et)
            assert event.event_type == et


# ---------------------------------------------------------------------------
# 2. from_claude_payload tests
# ---------------------------------------------------------------------------

class TestFromClaudePayload:

    def test_session_start_mapping(self, sample_claude_session_start):
        event = from_claude_payload(sample_claude_session_start)
        assert event.source == "claude"
        assert event.event_type == "session-start"
        assert event.payload["session_id"] == "claude-session-001"

    def test_prompt_submit_mapping(self, sample_claude_prompt_submit):
        event = from_claude_payload(sample_claude_prompt_submit)
        assert event.event_type == "prompt-submit"
        assert event.payload["user_message"] == "Fix the bug"

    def test_notification_mapping(self):
        raw = json.dumps({"event": "Notification", "cwd": "/tmp"})
        event = from_claude_payload(raw)
        assert event.event_type == "notification"

    def test_stop_mapping(self):
        raw = json.dumps({"event": "Stop"})
        event = from_claude_payload(raw)
        assert event.event_type == "stop"

    def test_unknown_event_defaults(self):
        raw = json.dumps({"event": "UnknownEvent"})
        event = from_claude_payload(raw)
        assert event.event_type == "prompt-submit"

    def test_missing_event_field_defaults(self):
        raw = json.dumps({"session_id": "xyz"})
        event = from_claude_payload(raw)
        assert event.event_type == "prompt-submit"

    def test_empty_payload(self):
        event = from_claude_payload("")
        assert event.source == "claude"
        assert event.event_type == "prompt-submit"
        assert event.payload == {}

    def test_invalid_json(self):
        event = from_claude_payload("{broken")
        assert event.payload == {}

    def test_cwd_from_payload(self):
        raw = json.dumps({"event": "SessionStart", "cwd": "/my/path"})
        event = from_claude_payload(raw)
        assert event.cwd == Path("/my/path")

    def test_cwd_override(self):
        raw = json.dumps({"event": "Stop", "cwd": "/ignored"})
        event = from_claude_payload(raw, cwd=Path("/forced"))
        assert event.cwd == Path("/forced")

    def test_timestamp_is_iso(self, sample_claude_session_start):
        event = from_claude_payload(sample_claude_session_start)
        from datetime import datetime
        datetime.fromisoformat(event.timestamp)


# ---------------------------------------------------------------------------
# 3. Claude event mapping completeness
# ---------------------------------------------------------------------------

class TestClaudeEventMapping:

    def test_all_mappings_present(self):
        assert "SessionStart" in _CLAUDE_EVENT_MAP
        assert "UserPromptSubmit" in _CLAUDE_EVENT_MAP
        assert "Notification" in _CLAUDE_EVENT_MAP
        assert "Stop" in _CLAUDE_EVENT_MAP

    def test_all_mappings_valid(self):
        for native, canonical in _CLAUDE_EVENT_MAP.items():
            assert canonical in _VALID_EVENT_TYPES


# ---------------------------------------------------------------------------
# 4. to_context_package_input tests
# ---------------------------------------------------------------------------

class TestToContextPackageInput:

    def test_codex_output_structure(self):
        event = HookEvent(
            source="codex",
            event_type="session-start",
            payload={"key": "value"},
            cwd=Path("/test/path"),
            timestamp="2026-04-30T10:00:00+08:00",
        )
        result = to_context_package_input(event)
        assert result == {
            "host": "codex",
            "event": "session-start",
            "payload": {"key": "value"},
            "cwd": "/test/path",
        }

    def test_claude_output_structure(self):
        event = HookEvent(
            source="claude",
            event_type="prompt-submit",
            payload={"user": "test"},
            cwd=Path("/another/path"),
            timestamp="2026-04-30T11:00:00+08:00",
        )
        result = to_context_package_input(event)
        assert result == {
            "host": "claude",
            "event": "prompt-submit",
            "payload": {"user": "test"},
            "cwd": "/another/path",
        }

    def test_structure_consistency(self):
        """Both hosts produce the same output keys."""
        codex_event = from_codex_payload('{"cwd":"/a"}', event="session-start")
        claude_event = from_claude_payload('{"event":"SessionStart","cwd":"/b"}')

        codex_out = to_context_package_input(codex_event)
        claude_out = to_context_package_input(claude_event)

        assert set(codex_out.keys()) == set(claude_out.keys())
        assert {"host", "event", "payload", "cwd"} == set(codex_out.keys())

    def test_cwd_is_string(self):
        event = HookEvent(
            source="codex",
            event_type="stop",
            payload={},
            cwd=Path("/some/dir"),
            timestamp="now",
        )
        result = to_context_package_input(event)
        assert isinstance(result["cwd"], str)
        assert result["cwd"] == "/some/dir"

    def test_payload_preserved(self):
        payload = {"complex": {"nested": True}, "list": [1, 2]}
        event = HookEvent(
            source="claude",
            event_type="notification",
            payload=payload,
            cwd=Path("."),
            timestamp="now",
        )
        result = to_context_package_input(event)
        assert result["payload"] is payload


# ---------------------------------------------------------------------------
# 5. parse_hook_event tests
# ---------------------------------------------------------------------------

class TestParseHookEvent:

    def test_codex_dispatch(self):
        raw = json.dumps({"cwd": "/test"})
        event = parse_hook_event("codex", "session-start", raw)
        assert event.source == "codex"
        assert event.event_type == "session-start"

    def test_claude_dispatch(self):
        raw = json.dumps({"event": "Stop"})
        event = parse_hook_event("claude", "ignored", raw)
        assert event.source == "claude"
        assert event.event_type == "stop"

    def test_unknown_host_raises(self):
        with pytest.raises(ValueError, match="unknown host"):
            parse_hook_event("unknown", "session-start", "{}")

    def test_codex_empty_event_uses_default(self):
        event = parse_hook_event("codex", "", "{}")
        assert event.event_type == "prompt-submit"

    def test_claude_event_from_payload(self):
        raw = json.dumps({"event": "UserPromptSubmit", "cwd": "/x"})
        event = parse_hook_event("claude", "stop", raw)
        # Claude ignores the event arg; reads from payload
        assert event.event_type == "prompt-submit"


# ---------------------------------------------------------------------------
# 6. Cross-host normalization
# ---------------------------------------------------------------------------

class TestCrossHostNormalization:

    def test_same_event_type_after_normalization(self):
        """Claude SessionStart and Codex session-start map to same type."""
        claude_raw = json.dumps({"event": "SessionStart", "cwd": "/repo"})
        codex_raw = json.dumps({"cwd": "/repo"})

        claude_event = from_claude_payload(claude_raw)
        codex_event = from_codex_payload(codex_raw, event="session-start")

        assert claude_event.event_type == codex_event.event_type == "session-start"

    def test_both_produce_compatible_context_input(self):
        """Both hosts produce structurally compatible context package input."""
        claude_raw = json.dumps({
            "event": "UserPromptSubmit",
            "session_id": "s1",
            "cwd": "/repo",
        })
        codex_raw = json.dumps({
            "session_id": "s2",
            "cwd": "/repo",
        })

        claude_event = from_claude_payload(claude_raw)
        codex_event = from_codex_payload(codex_raw, event="prompt-submit")

        claude_input = to_context_package_input(claude_event)
        codex_input = to_context_package_input(codex_event)

        # Same keys
        assert set(claude_input.keys()) == set(codex_input.keys())
        # Same event type
        assert claude_input["event"] == codex_input["event"]
        # Same host label (source)
        assert claude_input["host"] == "claude"
        assert codex_input["host"] == "codex"
        # Payloads are dicts
        assert isinstance(claude_input["payload"], dict)
        assert isinstance(codex_input["payload"], dict)
