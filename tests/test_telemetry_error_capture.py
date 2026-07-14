"""Tests for PostHog error capture in telemetry_bridge.

Covers VAL-PH-001 through VAL-PH-007: error events emitted from fail-safe
except blocks, recursion avoidance, structured properties, fail-safe
double-failure, disabled-state no-op, and event naming.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from memory_core.tools.telemetry_bridge import TelemetryBridge


@pytest.fixture
def bridge_with_mock():
    """Return a TelemetryBridge with a mock analytics client that is enabled."""
    bridge = TelemetryBridge()
    mock_analytics = MagicMock()
    mock_analytics._enabled = True
    bridge._analytics = mock_analytics
    return bridge, mock_analytics


class TestErrorCaptureEmission:
    """VAL-PH-001: except blocks emit memory.error events."""

    def test_safe_capture_emits_error_on_failure(self, bridge_with_mock):
        bridge, mock = bridge_with_mock
        mock.capture.side_effect = RuntimeError("connection refused")

        bridge.safe_capture("test_event", {"key": "value"})

        # The error event should have been captured
        error_calls = [c for c in mock.capture.call_args_list if c.kwargs.get("event_name") == "memory.error"]
        assert len(error_calls) == 1
        props = error_calls[0].kwargs["properties"]
        assert props["error_type"] == "RuntimeError"
        assert "connection refused" in props["error_message"]
        assert props["failed_event"] == "test_event"
        assert props["method"] == "safe_capture"

    def test_batch_capture_emits_error_on_failure(self, bridge_with_mock):
        bridge, mock = bridge_with_mock
        # Force batch_capture to fail by making urllib.urlopen raise
        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            result = bridge.batch_capture([{"event_name": "test", "properties": {}}])

        assert result is False
        error_calls = [c for c in mock.capture.call_args_list if c.kwargs.get("event_name") == "memory.error"]
        assert len(error_calls) == 1
        assert error_calls[0].kwargs["properties"]["method"] == "batch_capture"


class TestRecursionAvoidance:
    """VAL-PH-002: _capture_error does not call safe_capture (no recursion)."""

    def test_capture_error_calls_analytics_directly(self, bridge_with_mock):
        bridge, mock = bridge_with_mock

        bridge._capture_error(ValueError("test"), "test_event", "safe_capture")

        mock.capture.assert_called_once()
        call_kwargs = mock.capture.call_args.kwargs
        assert call_kwargs["event_name"] == "memory.error"

    def test_no_recursion_on_persistent_failure(self, bridge_with_mock):
        """When capture always fails, _capture_error must not recurse."""
        bridge, mock = bridge_with_mock
        call_count = [0]
        original_side_effect = RuntimeError("persistent")

        def counting_side_effect(*args, **kwargs):
            call_count[0] += 1
            raise original_side_effect

        mock.capture.side_effect = counting_side_effect

        bridge.safe_capture("test_event", {})

        # Should be exactly 2 calls: 1 original + 1 error event attempt
        # NOT infinite recursion
        assert call_count[0] == 2


class TestFailSafeDoubleFailure:
    """VAL-PH-004: double-failure does not propagate exceptions."""

    def test_double_failure_no_propagation(self, bridge_with_mock):
        bridge, mock = bridge_with_mock
        mock.capture.side_effect = RuntimeError("always fails")

        # Should not raise
        bridge.safe_capture("test", {})
        bridge.batch_capture([{"event_name": "x"}])
        bridge.flush()


class TestDisabledStateNoOp:
    """VAL-PH-005: error capture is no-op when disabled."""

    def test_no_capture_when_disabled(self):
        bridge = TelemetryBridge()
        mock_analytics = MagicMock()
        mock_analytics._enabled = False
        bridge._analytics = mock_analytics

        bridge._capture_error(ValueError("test"), "event", "method")

        mock_analytics.capture.assert_not_called()

    def test_no_capture_when_analytics_none(self):
        bridge = TelemetryBridge()
        bridge._analytics = None

        bridge._capture_error(ValueError("test"), "event", "method")
        # Should not raise


class TestEventNaming:
    """VAL-PH-006: error event uses memory.error prefix."""

    def test_error_event_name(self, bridge_with_mock):
        bridge, mock = bridge_with_mock
        mock.capture.side_effect = RuntimeError("fail")

        bridge.safe_capture("test_event", {})

        error_calls = [c for c in mock.capture.call_args_list if c.kwargs.get("event_name") == "memory.error"]
        assert len(error_calls) == 1
        # No double prefix
        assert error_calls[0].kwargs["event_name"] == "memory.error"
        assert "memory.memory" not in error_calls[0].kwargs["event_name"]


class TestErrorCaptureSanitization:
    """VAL-PRIV-001: _capture_error must sanitize absolute paths."""

    def test_capture_error_sanitizes_absolute_path_in_exception_message(self, bridge_with_mock):
        """Exception messages containing absolute paths must be reduced to basename."""
        bridge, mock = bridge_with_mock

        # Create exception with absolute path in message
        exc = ValueError("Failed to read /Users/testuser/project/data/file.txt")
        bridge._capture_error(exc, "test_event", "safe_capture")

        # Verify capture was called
        mock.capture.assert_called_once()
        call_kwargs = mock.capture.call_args.kwargs
        properties = call_kwargs["properties"]

        # The error_message should NOT contain the absolute path
        assert "error_message" in properties
        assert "/Users/testuser/project/data/" not in properties["error_message"]

        # The error_message should contain only the basename
        assert "file.txt" in properties["error_message"]

    def test_capture_error_applies_sanitize_properties_to_all_fields(self, bridge_with_mock):
        """All error properties must be sanitized before sending to PostHog."""
        bridge, mock = bridge_with_mock

        # Exception with absolute path
        exc = RuntimeError("Cannot access /home/user/secret/credentials.json")
        bridge._capture_error(exc, "another_event", "batch_capture")

        mock.capture.assert_called_once()
        call_kwargs = mock.capture.call_args.kwargs
        properties = call_kwargs["properties"]

        # Verify all path-like values are sanitized
        assert "/home/user/secret/" not in properties["error_message"]
        assert "credentials.json" in properties["error_message"]

        # Other fields should not be affected
        assert properties["error_type"] == "RuntimeError"
        assert properties["failed_event"] == "another_event"
        assert properties["method"] == "batch_capture"
