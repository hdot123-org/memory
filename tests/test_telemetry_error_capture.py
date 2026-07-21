"""Tests for PostHog error capture in telemetry_bridge.

Covers VAL-PH-001 through VAL-PH-007: error events emitted from fail-safe
except blocks, recursion avoidance, structured properties, fail-safe
double-failure, disabled-state no-op, and event naming.
"""

from unittest.mock import MagicMock, patch

import pytest

from memory_core.tools.telemetry_bridge import TelemetryBridge


@pytest.fixture(autouse=True)
def _restore_telemetry_singleton():
    """Restore TelemetryBridge singleton state after each test."""
    from memory_core.tools.telemetry_bridge import telemetry
    original = telemetry._analytics
    yield
    telemetry._analytics = original


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

        bridge._capture_error(ValueError("test"), "test_event", "batch_capture")

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

        # batch_capture will fail and call _capture_error, which should not recurse
        with patch.object(bridge, '_is_enabled', return_value=True):
            with patch("urllib.request.urlopen", side_effect=OSError("network down")):
                bridge.batch_capture([{"event_name": "test", "properties": {}}])

        # Should be exactly 1 call: _capture_error's attempt to emit error event
        # NOT infinite recursion
        assert call_count[0] == 1


class TestFailSafeDoubleFailure:
    """VAL-PH-004: double-failure does not propagate exceptions."""

    def test_double_failure_no_propagation(self, bridge_with_mock):
        bridge, mock = bridge_with_mock
        mock.capture.side_effect = RuntimeError("always fails")

        # Should not raise
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

        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            bridge.batch_capture([{"event_name": "test", "properties": {}}])

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
        bridge._capture_error(exc, "test_event", "batch_capture")

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


class TestBatchCaptureRetryLogic:
    """VAL-PH-008: batch_capture retries transient failures (429, 5xx, URLError)."""

    @pytest.fixture
    def bridge_with_client(self):
        """Return a TelemetryBridge with mock analytics + client for batch_capture."""
        bridge = TelemetryBridge()
        mock_analytics = MagicMock()
        mock_analytics._enabled = True
        mock_client = MagicMock()
        mock_client.api_key = "phc_test_key"
        mock_analytics._client = mock_client
        bridge._analytics = mock_analytics
        return bridge, mock_analytics

    def test_http_400_not_retried(self, bridge_with_client):
        """HTTP 400 is non-retryable - should fail immediately without retry."""
        bridge, mock = bridge_with_client
        import urllib.error

        http_err = urllib.error.HTTPError(
            url="https://test/batch/",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=__import__("io").BytesIO(b'{"detail": "invalid payload"}'),
        )

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            raise http_err

        with patch("urllib.request.urlopen", side_effect=side_effect), \
             patch("time.sleep"):
            result = bridge.batch_capture([{"event_name": "test", "properties": {}}])

        assert result is False
        assert call_count[0] == 1  # No retries

    def test_http_429_not_retried(self, bridge_with_client):
        """HTTP 429 (rate limit) is NOT retried. Telemetry is lossy-tolerant and
        the hook budget is ~10s, so batch_capture does not retry (max_retries=0).
        The event is dropped and retried on the next session instead."""
        bridge, mock = bridge_with_client

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.status = 200

        import urllib.error
        http_429 = urllib.error.HTTPError(
            url="https://test/batch/",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=__import__("io").BytesIO(b'{"detail": "rate limited"}'),
        )

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise http_429
            return mock_response

        with patch("urllib.request.urlopen", side_effect=side_effect), \
             patch("time.sleep"):
            result = bridge.batch_capture([{"event_name": "test", "properties": {}}])

        # No retry: the 429 fails the batch, dropped this session (retry next session)
        assert result is False
        assert call_count[0] == 1  # No retries (max_retries=0)

    def test_http_500_not_retried(self, bridge_with_client):
        """HTTP 500 is NOT retried. Telemetry is lossy-tolerant; the hook budget
        (~10s) cannot afford retries, so the batch fails immediately (max_retries=0)."""
        bridge, mock = bridge_with_client
        import urllib.error

        http_500 = urllib.error.HTTPError(
            url="https://test/batch/",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=__import__("io").BytesIO(b'{"detail": "server error"}'),
        )

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            raise http_500

        with patch("urllib.request.urlopen", side_effect=side_effect), \
             patch("time.sleep"):
            result = bridge.batch_capture([{"event_name": "test", "properties": {}}])

        assert result is False
        assert call_count[0] == 1  # No retries (max_retries=0)

    def test_urlerror_not_retried(self, bridge_with_client):
        """URLError (timeout/network) is NOT retried. Telemetry is lossy-tolerant;
        the hook budget (~10s) cannot afford retries, so it fails immediately."""
        bridge, mock = bridge_with_client

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.status = 200

        import urllib.error
        url_err = urllib.error.URLError("handshake timed out")

        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise url_err
            return mock_response

        with patch("urllib.request.urlopen", side_effect=side_effect), \
             patch("time.sleep"):
            result = bridge.batch_capture([{"event_name": "test", "properties": {}}])

        # No retry: the URLError fails the batch, dropped this session (retry next session)
        assert result is False
        assert call_count[0] == 1  # No retries (max_retries=0)


class TestBatchCaptureHTTPErrorBodyCapture:
    """VAL-PH-009: HTTPError response body is captured in error event."""

    @pytest.fixture
    def bridge_with_client(self):
        bridge = TelemetryBridge()
        mock_analytics = MagicMock()
        mock_analytics._enabled = True
        mock_client = MagicMock()
        mock_client.api_key = "phc_test_key"
        mock_analytics._client = mock_client
        bridge._analytics = mock_analytics
        return bridge, mock_analytics

    def test_http_error_body_included_in_error_message(self, bridge_with_client):
        """When HTTP 400 occurs, the response body should be captured for diagnostics."""
        bridge, mock = bridge_with_client
        import urllib.error

        http_err = urllib.error.HTTPError(
            url="https://test/batch/",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=__import__("io").BytesIO(b"event submitted without a distinct_id"),
        )

        with patch("urllib.request.urlopen", side_effect=http_err), \
             patch("time.sleep"):
            result = bridge.batch_capture([{"event_name": "test", "properties": {}}])

        assert result is False

        # Check the error event
        error_calls = [
            c for c in mock.capture.call_args_list
            if c.kwargs.get("event_name") == "memory.error"
        ]
        assert len(error_calls) == 1
        error_msg = error_calls[0].kwargs["properties"]["error_message"]
        assert "400" in error_msg
        assert "Bad Request" in error_msg
        assert "distinct_id" in error_msg  # Response body was captured


class TestBatchCapturePayloadEnhancements:
    """VAL-PH-010: batch payload includes uuid and sentAt (matches SDK behavior)."""

    @pytest.fixture
    def bridge_with_client(self):
        bridge = TelemetryBridge()
        mock_analytics = MagicMock()
        mock_analytics._enabled = True
        mock_client = MagicMock()
        mock_client.api_key = "phc_test_key"
        mock_analytics._client = mock_client
        bridge._analytics = mock_analytics
        return bridge, mock_analytics

    def test_payload_includes_uuid_and_sentat(self, bridge_with_client):
        """Batch payload should include uuid per event and sentAt timestamp."""
        bridge, mock = bridge_with_client

        import json as json_module

        captured_payloads = []
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.status = 200

        def side_effect(req, **kwargs):
            body = json_module.loads(req.data.decode("utf-8"))
            captured_payloads.append(body)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = bridge.batch_capture([
                {"event_name": "test_event", "properties": {"key": "value"}}
            ])

        assert result is True
        assert len(captured_payloads) == 1
        payload = captured_payloads[0]

        # sentAt should be present at top level
        assert "sentAt" in payload

        # Each batch item should have a uuid
        assert len(payload["batch"]) == 1
        assert "uuid" in payload["batch"][0]
        assert payload["batch"][0]["uuid"]  # non-empty


class TestBatchCaptureSDKCompliance:
    """VAL-PH-012: batch items match PostHog SDK wire format to prevent HTTP 400.

    The PostHog batch API rejects payloads missing required fields that the
    Python SDK's _enqueue always adds. This test class verifies our manual
    batch_capture includes those same fields.
    """

    @pytest.fixture
    def bridge_with_client(self):
        bridge = TelemetryBridge()
        mock_analytics = MagicMock()
        mock_analytics._enabled = True
        mock_client = MagicMock()
        mock_client.api_key = "phc_test_key"
        mock_analytics._client = mock_client
        bridge._analytics = mock_analytics
        return bridge, mock_analytics

    def test_batch_item_has_top_level_timestamp(self, bridge_with_client):
        """Each batch item must include a top-level ISO timestamp (SDK requirement)."""
        bridge, mock = bridge_with_client

        import json as json_module
        captured_payloads = []
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.status = 200

        def side_effect(req, **kwargs):
            body = json_module.loads(req.data.decode("utf-8"))
            captured_payloads.append(body)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=side_effect):
            bridge.batch_capture([{"event_name": "test_event", "properties": {}}])

        item = captured_payloads[0]["batch"][0]
        assert "timestamp" in item, "Batch item must have top-level timestamp field"
        # Should be a valid ISO 8601 string
        assert "T" in item["timestamp"]

    def test_batch_item_has_geoip_disable(self, bridge_with_client):
        """Each batch item properties must include $geoip_disable=True (SDK parity)."""
        bridge, mock = bridge_with_client

        import json as json_module
        captured_payloads = []
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.status = 200

        def side_effect(req, **kwargs):
            body = json_module.loads(req.data.decode("utf-8"))
            captured_payloads.append(body)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=side_effect):
            bridge.batch_capture([{"event_name": "test_event", "properties": {}}])

        item = captured_payloads[0]["batch"][0]
        assert item["properties"]["$geoip_disable"] is True

    def test_batch_item_has_is_server(self, bridge_with_client):
        """Each batch item properties must include $is_server=True (SDK parity)."""
        bridge, mock = bridge_with_client

        import json as json_module
        captured_payloads = []
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.status = 200

        def side_effect(req, **kwargs):
            body = json_module.loads(req.data.decode("utf-8"))
            captured_payloads.append(body)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=side_effect):
            bridge.batch_capture([{"event_name": "test_event", "properties": {}}])

        item = captured_payloads[0]["batch"][0]
        assert item["properties"]["$is_server"] is True


class TestResolveIngestionHost:
    """VAL-PH-011: _resolve_ingestion_host remaps app domains to ingestion domains."""

    def test_remaps_us_posthog(self):
        from memory_core.tools.telemetry_bridge import _resolve_ingestion_host
        assert _resolve_ingestion_host("https://us.posthog.com") == "https://us.i.posthog.com"

    def test_remaps_app_posthog(self):
        from memory_core.tools.telemetry_bridge import _resolve_ingestion_host
        assert _resolve_ingestion_host("https://app.posthog.com") == "https://us.i.posthog.com"

    def test_remaps_eu_posthog(self):
        from memory_core.tools.telemetry_bridge import _resolve_ingestion_host
        assert _resolve_ingestion_host("https://eu.posthog.com") == "https://eu.i.posthog.com"

    def test_passthrough_custom_host(self):
        from memory_core.tools.telemetry_bridge import _resolve_ingestion_host
        custom = "https://custom.posthog.example.com"
        assert _resolve_ingestion_host(custom) == custom

    def test_handles_trailing_slash(self):
        from memory_core.tools.telemetry_bridge import _resolve_ingestion_host
        assert _resolve_ingestion_host("https://us.posthog.com/") == "https://us.i.posthog.com"

