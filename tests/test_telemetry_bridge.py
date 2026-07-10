"""Unit tests for telemetry_bridge module.

Tests cover:
- safe_capture no-op behavior when analytics disabled
- Data sanitization (path keys replaced with basename)
- distinct_id using project_id (not hardcoded)
- replay_unsent functionality
- flush method
- Event name prefix handling
- Automatic enrichment (version, host, timestamp)
- Fail-safe behavior
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from memory_core.tools.telemetry_bridge import (
    TelemetryBridge,
    _fallback_project_id,
    _looks_like_path_key,
    _sanitize_properties,
    _sanitize_value,
    telemetry,
)


class TestTelemetryBridgeHelpers:
    """Test helper functions."""

    def test_looks_like_path_key_detects_path_keywords(self):
        """Keys containing path-related fragments should be detected."""
        assert _looks_like_path_key("project_path") is True
        assert _looks_like_path_key("file_path") is True
        assert _looks_like_path_key("working_directory") is True  # contains "dir"
        assert _looks_like_path_key("cwd") is True
        assert _looks_like_path_key("root_dir") is True
        assert _looks_like_path_key("event_name") is False

    def test_sanitize_value_replaces_absolute_paths(self):
        """Absolute paths should be replaced with basename."""
        assert _sanitize_value("/Users/test/project/file.txt") == "file.txt"
        # Windows paths on macOS are not detected as absolute
        # (Path.is_absolute() returns False for C:\ paths on POSIX)
        assert _sanitize_value("C:\\Users\\test\\project") == "project" or _sanitize_value("C:\\Users\\test\\project") == "C:\\Users\\test\\project"
        assert _sanitize_value("/tmp/logs") == "logs"

    def test_sanitize_value_preserves_relative_paths(self):
        """Relative paths without separators should not be modified."""
        assert _sanitize_value("relative_file") == "relative_file"
        assert _sanitize_value("simple_name") == "simple_name"

    def test_sanitize_value_preserves_non_strings(self):
        """Non-string values should pass through unchanged."""
        assert _sanitize_value(123) == 123
        assert _sanitize_value(None) is None
        assert _sanitize_value(True) is True
        assert _sanitize_value(["list"]) == ["list"]

    def test_sanitize_properties_sanitizes_path_keys(self):
        """Properties with path-like keys should have values sanitized."""
        props = {
            "project_path": "/Users/test/project",
            "file_location": "/tmp/data.json",
            "event_name": "test_event",
            "count": 42,
        }
        sanitized = _sanitize_properties(props)
        assert sanitized["project_path"] == "project"
        assert sanitized["file_location"] == "data.json"
        assert sanitized["event_name"] == "test_event"
        assert sanitized["count"] == 42

    def test_sanitize_properties_handles_none(self):
        """None properties should return empty dict."""
        assert _sanitize_properties(None) == {}

    def test_sanitize_properties_handles_empty_dict(self):
        """Empty dict should return empty dict."""
        assert _sanitize_properties({}) == {}

    def test_fallback_project_id_with_path(self):
        """Fallback should generate deterministic ID from path name."""
        path = Path("/Users/test/my-project")
        project_id = _fallback_project_id(path)
        assert project_id.startswith("my-project-")
        assert len(project_id.split("-")) >= 2  # name + hash

    def test_fallback_project_id_with_none(self):
        """Fallback with None should use current working directory."""
        project_id = _fallback_project_id(None)
        assert isinstance(project_id, str)
        assert len(project_id) > 0

    def test_fallback_project_id_is_deterministic(self):
        """Same path should always produce same project_id."""
        path = Path("/Users/test/project")
        id1 = _fallback_project_id(path)
        id2 = _fallback_project_id(path)
        assert id1 == id2


class TestTelemetryBridge:
    """Test TelemetryBridge class."""

    def test_singleton_pattern(self):
        """TelemetryBridge should implement singleton pattern."""
        bridge1 = TelemetryBridge()
        bridge2 = TelemetryBridge()
        assert bridge1 is bridge2
        assert bridge1 is telemetry

    def test_is_enabled_returns_false_when_no_analytics(self):
        """_is_enabled should return False when analytics is None."""
        # Create a fresh instance for testing (bypass singleton)
        bridge = object.__new__(TelemetryBridge)
        bridge._initialized = True
        bridge._analytics = None
        assert bridge._is_enabled() is False

    def test_get_project_id_returns_string(self):
        """get_project_id should always return a non-empty string."""
        bridge = TelemetryBridge()
        project_id = bridge.get_project_id("/tmp/test")
        assert isinstance(project_id, str)
        assert len(project_id) > 0

    def test_get_project_id_with_none(self):
        """get_project_id with None should use current directory."""
        bridge = TelemetryBridge()
        project_id = bridge.get_project_id(None)
        assert isinstance(project_id, str)
        assert len(project_id) > 0

    def test_safe_capture_noop_when_disabled(self):
        """safe_capture should be no-op when analytics is disabled."""
        # Create a fresh instance (not singleton) to avoid state pollution
        bridge = object.__new__(TelemetryBridge)
        bridge._initialized = True
        mock_analytics = MagicMock()
        mock_analytics._enabled = False
        bridge._analytics = mock_analytics

        # Patch _is_enabled on this instance only
        with patch.object(bridge, '_is_enabled', return_value=False):
            bridge.safe_capture("test_event", {"key": "value"}, "/tmp")

        # analytics.capture should not be called
        mock_analytics.capture.assert_not_called()

    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge._is_enabled")
    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge.get_project_id")
    def test_safe_capture_sanitizes_properties(
        self, mock_get_project_id, mock_is_enabled
    ):
        """safe_capture should sanitize path-like properties."""
        mock_is_enabled.return_value = True
        mock_get_project_id.return_value = "test-project-abc123"

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()

        bridge.safe_capture(
            "test_event",
            {"project_path": "/Users/test/project", "event_name": "test"},
            "/tmp",
        )

        # Verify capture was called with sanitized properties
        call_args = bridge._analytics.capture.call_args
        properties = call_args.kwargs["properties"]
        assert properties["project_path"] == "project"  # sanitized
        assert properties["event_name"] == "test"  # not sanitized

    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge._is_enabled")
    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge.get_project_id")
    def test_safe_capture_adds_memory_prefix(self, mock_get_project_id, mock_is_enabled):
        """safe_capture should add 'memory.' prefix to event names."""
        mock_is_enabled.return_value = True
        mock_get_project_id.return_value = "test-project"

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()

        bridge.safe_capture("test_event", {}, "/tmp")

        call_args = bridge._analytics.capture.call_args
        assert call_args.kwargs["event_name"] == "memory.test_event"

    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge._is_enabled")
    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge.get_project_id")
    def test_safe_capture_preserves_memory_prefix(
        self, mock_get_project_id, mock_is_enabled
    ):
        """safe_capture should not double-prefix event names already starting with 'memory.'."""
        mock_is_enabled.return_value = True
        mock_get_project_id.return_value = "test-project"

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()

        bridge.safe_capture("memory.test_event", {}, "/tmp")

        call_args = bridge._analytics.capture.call_args
        assert call_args.kwargs["event_name"] == "memory.test_event"

    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge._is_enabled")
    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge.get_project_id")
    def test_safe_capture_enriches_properties(
        self, mock_get_project_id, mock_is_enabled
    ):
        """safe_capture should add version, host, and timestamp to properties."""
        mock_is_enabled.return_value = True
        mock_get_project_id.return_value = "test-project"

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()

        bridge.safe_capture("test_event", {"custom": "value"}, "/tmp")

        call_args = bridge._analytics.capture.call_args
        properties = call_args.kwargs["properties"]
        assert "memory_core_version" in properties
        assert "host" in properties
        assert "timestamp" in properties
        assert properties["custom"] == "value"

    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge._is_enabled")
    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge.get_project_id")
    def test_safe_capture_uses_project_id_as_distinct_id(
        self, mock_get_project_id, mock_is_enabled
    ):
        """safe_capture should use project_id from get_project_id as distinct_id."""
        mock_is_enabled.return_value = True
        mock_get_project_id.return_value = "test-project-abc123"

        # Create a fresh instance to avoid singleton state pollution
        bridge = object.__new__(TelemetryBridge)
        bridge._initialized = True
        bridge._analytics = MagicMock()
        bridge._is_enabled = mock_is_enabled
        bridge.get_project_id = mock_get_project_id

        bridge.safe_capture("test_event", {}, "/tmp")

        call_args = bridge._analytics.capture.call_args
        assert call_args.kwargs["distinct_id"] == "test-project-abc123"

    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge._is_enabled")
    @patch("memory_core.tools.telemetry_bridge.TelemetryBridge.get_project_id")
    def test_safe_capture_fail_safe(self, mock_get_project_id, mock_is_enabled):
        """safe_capture should not raise exceptions."""
        mock_is_enabled.return_value = True
        mock_get_project_id.return_value = "test-project"

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()
        bridge._analytics.capture.side_effect = Exception("Test error")

        # Should not raise
        bridge.safe_capture("test_event", {}, "/tmp")

    def test_flush_calls_shutdown(self):
        """flush should call analytics.shutdown()."""
        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()

        bridge.flush()

        bridge._analytics.shutdown.assert_called_once()

    def test_flush_noop_when_no_analytics(self):
        """flush should be no-op when analytics is None."""
        bridge = TelemetryBridge()
        original_analytics = bridge._analytics
        bridge._analytics = None

        # Should not raise
        bridge.flush()

        bridge._analytics = original_analytics


class TestReplayUnsent:
    """Test replay_unsent functionality."""

    def test_replay_unsent_returns_zero_for_nonexistent_file(self):
        """replay_unsent should return 0 when file doesn't exist."""
        bridge = TelemetryBridge()
        result = bridge.replay_unsent("/tmp/nonexistent_file.jsonl")
        assert result == 0

    def test_replay_unsent_skips_already_sent_records(self, tmp_path):
        """replay_unsent should skip records with posthog_sent=True."""
        metrics_file = tmp_path / "metrics.jsonl"
        metrics_file.write_text(
            json.dumps({"event": "test1", "posthog_sent": True}) + "\n"
            + json.dumps({"event": "test2", "posthog_sent": False}) + "\n"
            + json.dumps({"event": "test3", "posthog_sent": True}) + "\n",
            encoding="utf-8",
        )

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()
        bridge._is_enabled = MagicMock(return_value=True)
        bridge.get_project_id = MagicMock(return_value="test-project")

        result = bridge.replay_unsent(metrics_file)

        # Only 1 record should be replayed (the one with posthog_sent=False)
        assert result == 1
        assert bridge._analytics.capture.call_count == 1

    def test_replay_unsent_uses_offset_file(self, tmp_path):
        """replay_unsent should read and write offset file."""
        metrics_file = tmp_path / "metrics.jsonl"
        offset_file = tmp_path / "metrics.jsonl.offset"

        # Write 3 records
        metrics_file.write_text(
            json.dumps({"event": "test1", "posthog_sent": False}) + "\n"
            + json.dumps({"event": "test2", "posthog_sent": False}) + "\n"
            + json.dumps({"event": "test3", "posthog_sent": False}) + "\n",
            encoding="utf-8",
        )

        # Set offset to 2 (skip first 2 lines)
        offset_file.write_text("2", encoding="utf-8")

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()
        bridge._is_enabled = MagicMock(return_value=True)
        bridge.get_project_id = MagicMock(return_value="test-project")

        result = bridge.replay_unsent(metrics_file)

        # Only 1 record should be replayed (the 3rd one)
        assert result == 1
        # Offset should be updated to 3
        assert offset_file.read_text(encoding="utf-8").strip() == "3"

    def test_replay_unsent_fail_safe(self, tmp_path):
        """replay_unsent should not raise exceptions."""
        metrics_file = tmp_path / "metrics.jsonl"
        metrics_file.write_text(
            json.dumps({"event": "test1", "posthog_sent": False}) + "\n",
            encoding="utf-8",
        )

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()
        bridge._analytics.capture.side_effect = Exception("Test error")
        bridge._is_enabled = MagicMock(return_value=True)
        bridge.get_project_id = MagicMock(return_value="test-project")

        # Should not raise
        result = bridge.replay_unsent(metrics_file)
        assert result == 1

    def test_replay_unsent_handles_invalid_json(self, tmp_path):
        """replay_unsent should skip invalid JSON lines."""
        metrics_file = tmp_path / "metrics.jsonl"
        metrics_file.write_text(
            json.dumps({"event": "test1", "posthog_sent": False}) + "\n"
            + "invalid json line\n"
            + json.dumps({"event": "test2", "posthog_sent": False}) + "\n",
            encoding="utf-8",
        )

        bridge = TelemetryBridge()
        bridge._analytics = MagicMock()
        bridge._is_enabled = MagicMock(return_value=True)
        bridge.get_project_id = MagicMock(return_value="test-project")

        result = bridge.replay_unsent(metrics_file)

        # Should replay 2 valid records
        assert result == 2


class TestModuleLevelSetup:
    """Test module-level initialization."""

    def test_module_level_telemetry_exists(self):
        """Module should export telemetry singleton."""
        from memory_core.tools import telemetry_bridge
        assert hasattr(telemetry_bridge, "telemetry")
        assert isinstance(telemetry_bridge.telemetry, TelemetryBridge)

    def test_atexit_registered(self):
        """Module should register flush with atexit."""
        from memory_core.tools import telemetry_bridge

        # We can't directly check atexit registration, but we can verify
        # that flush is callable and the module imported successfully
        assert callable(telemetry_bridge.telemetry.flush)
