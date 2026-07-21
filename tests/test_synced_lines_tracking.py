"""Tests for synced_lines tracking in _maybe_sync_telemetry.

This test file verifies that the offset tracking correctly uses file line numbers
(not record count) to handle blank lines and malformed JSON without causing
duplicate telemetry on retry.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from memory_core.tools import memory_hook_gateway as gw


def _setup_sync_artifacts(tmp_path: Path, *, metrics_lines: list[str] | None = None,
                          offset: int = 0, last_sync_success: float = 0.0,
                          last_sync_attempt: float = 0.0) -> Path:
    """Create artifact root with metrics.jsonl and sidecar files for sync tests."""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()

    metrics_file = artifact_root / "metrics.jsonl"
    if metrics_lines is not None:
        metrics_file.write_text("".join(metrics_lines), encoding="utf-8")
    else:
        metrics_file.write_text("", encoding="utf-8")

    offset_file = artifact_root / ".offset"
    offset_file.write_text(str(offset), encoding="utf-8")

    last_sync_success_file = artifact_root / ".last_sync_success"
    last_sync_success_file.write_text(str(last_sync_success), encoding="utf-8")

    last_sync_attempt_file = artifact_root / ".last_sync_attempt"
    last_sync_attempt_file.write_text(str(last_sync_attempt), encoding="utf-8")

    return artifact_root


class TestSyncedLinesTracking:
    """Test VAL-SYNC-001: offset tracks actual file line numbers, not record count."""

    def test_offset_correct_with_blank_lines(self, tmp_path):
        """metrics.jsonl with blank lines: offset must match actual file position."""
        # File has 5 lines: 3 valid records, 2 blank lines
        # Line 1: record 1
        # Line 2: blank
        # Line 3: record 2
        # Line 4: blank
        # Line 5: record 3
        # After successful sync, offset should be 5 (last line number)
        metrics_lines = [
            json.dumps({"event": "ev1"}) + "\n",
            "\n",
            json.dumps({"event": "ev2"}) + "\n",
            "\n",
            json.dumps({"event": "ev3"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            last_sync_success=time.time() - 7200,
        )

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = True

        with patch("socket.create_connection"), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            gw._maybe_sync_telemetry(artifact_root)

        # After full sync, metrics are compacted and offset reset to 0
        offset_val = int((artifact_root / ".offset").read_text().strip())
        assert offset_val == 0

        # Metrics file should be empty after compaction
        remaining = (artifact_root / "metrics.jsonl").read_text()
        assert remaining == ""

    def test_offset_correct_with_malformed_json(self, tmp_path):
        """metrics.jsonl with malformed JSON: offset must match actual file position."""
        # Line 1: valid record 1
        # Line 2: malformed JSON
        # Line 3: valid record 2
        # Line 4: malformed JSON
        # Line 5: valid record 3
        # After successful sync, offset should be 5 (last line number)
        metrics_lines = [
            json.dumps({"event": "ev1"}) + "\n",
            "{bad json\n",
            json.dumps({"event": "ev2"}) + "\n",
            "not valid json\n",
            json.dumps({"event": "ev3"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            last_sync_success=time.time() - 7200,
        )

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = True

        with patch("socket.create_connection"), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            gw._maybe_sync_telemetry(artifact_root)

        # After full sync, metrics are compacted and offset reset to 0
        offset_val = int((artifact_root / ".offset").read_text().strip())
        assert offset_val == 0

        remaining = (artifact_root / "metrics.jsonl").read_text()
        assert remaining == ""

    def test_offset_correct_with_mixed_blank_and_malformed(self, tmp_path):
        """metrics.jsonl with both blank lines and malformed JSON."""
        # Line 1: valid record 1
        # Line 2: blank
        # Line 3: malformed JSON
        # Line 4: valid record 2
        # Line 5: blank
        # Line 6: valid record 3
        metrics_lines = [
            json.dumps({"event": "ev1"}) + "\n",
            "\n",
            "{bad\n",
            json.dumps({"event": "ev2"}) + "\n",
            "\n",
            json.dumps({"event": "ev3"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            last_sync_success=time.time() - 7200,
        )

        mock_telemetry = MagicMock()
        mock_telemetry.batch_capture.return_value = True

        with patch("socket.create_connection"), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            gw._maybe_sync_telemetry(artifact_root)

        # After full sync, metrics are compacted and offset reset to 0
        offset_val = int((artifact_root / ".offset").read_text().strip())
        assert offset_val == 0

        remaining = (artifact_root / "metrics.jsonl").read_text()
        assert remaining == ""


class TestNoDuplicateOnPartialFailure:
    """Test VAL-SYNC-002: partial failure does not cause duplicate telemetry."""

    def test_partial_failure_no_duplicate(self, tmp_path):
        """After partial failure, retry only sends remaining records."""
        # File has 4 lines: 3 valid records, 1 blank
        # Line 1: record 1
        # Line 2: blank
        # Line 3: record 2
        # Line 4: record 3
        #
        # With BATCH_SIZE=2, we'll have chunks:
        # Chunk 1: [record1, record2] (lines 1, 3) - succeed, offset = 3
        # Chunk 2: [record3] (line 4) - fail, offset stays at 3
        #
        # On retry, we should only send record3 (line 4), not records 1-2

        metrics_lines = [
            json.dumps({"event": "ev1"}) + "\n",
            "\n",
            json.dumps({"event": "ev2"}) + "\n",
            json.dumps({"event": "ev3"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            last_sync_success=time.time() - 7200,
        )

        # First sync: chunk 1 succeeds, chunk 2 fails
        mock_telemetry = MagicMock()
        call_count = [0]
        def batch_capture_side_effect(events):
            call_count[0] += 1
            if call_count[0] == 1:
                return True
            return False
        mock_telemetry.batch_capture.side_effect = batch_capture_side_effect

        with patch("socket.create_connection"), \
             patch.object(gw, "BATCH_SIZE", 2), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            gw._maybe_sync_telemetry(artifact_root)

        # After partial failure, offset should be 3 (line of last successful record)
        offset_val = int((artifact_root / ".offset").read_text().strip())
        assert offset_val == 3, f"Expected offset=3, got {offset_val}"

        # Metrics file should NOT be compacted (partial failure)
        remaining_lines = (artifact_root / "metrics.jsonl").read_text().strip().split("\n")
        assert len(remaining_lines) == 4, "All lines should remain after partial failure"

        # Second sync: only record3 (line 4) should be sent
        # Reset both success and attempt timestamps to allow retry
        (artifact_root / ".last_sync_success").write_text(str(time.time() - 7200))
        (artifact_root / ".last_sync_attempt").write_text(str(time.time() - 7200))
        mock_telemetry.reset_mock()
        mock_telemetry.batch_capture.return_value = True

        with patch("socket.create_connection"), \
             patch.object(gw, "BATCH_SIZE", 2), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            gw._maybe_sync_telemetry(artifact_root)

        # Verify only record3 was sent
        assert mock_telemetry.batch_capture.called
        events_sent = mock_telemetry.batch_capture.call_args[0][0]
        event_names = [e["event_name"] for e in events_sent]
        assert event_names == ["ev3"], f"Expected only ['ev3'], got {event_names}"

    def test_partial_failure_preserves_unsynced_records(self, tmp_path):
        """After partial failure, unsynced records are preserved for retry."""
        # Line 1: record 1
        # Line 2: blank
        # Line 3: record 2
        # Line 4: record 3
        #
        # With BATCH_SIZE=2:
        # Chunk 1: [record1, record2] (lines 1, 3) - succeed, offset = 3
        # Chunk 2: [record3] (line 4) - fail, offset stays at 3
        #
        # On retry, we should send record3 (line 4)

        metrics_lines = [
            json.dumps({"event": "ev1"}) + "\n",
            "\n",
            json.dumps({"event": "ev2"}) + "\n",
            json.dumps({"event": "ev3"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            last_sync_success=time.time() - 7200,
        )

        # First sync: chunk 1 succeeds, chunk 2 fails
        mock_telemetry = MagicMock()
        call_count = [0]
        def batch_capture_side_effect(events):
            call_count[0] += 1
            if call_count[0] == 1:
                return True
            return False
        mock_telemetry.batch_capture.side_effect = batch_capture_side_effect

        with patch("socket.create_connection"), \
             patch.object(gw, "BATCH_SIZE", 2), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            gw._maybe_sync_telemetry(artifact_root)

        # After partial failure, offset should be 3 (line of last successful record)
        offset_val = int((artifact_root / ".offset").read_text().strip())
        assert offset_val == 3, f"Expected offset=3, got {offset_val}"

        # Second sync: reset both success and attempt timestamps to allow retry
        (artifact_root / ".last_sync_success").write_text(str(time.time() - 7200))
        (artifact_root / ".last_sync_attempt").write_text(str(time.time() - 7200))
        mock_telemetry.reset_mock()
        mock_telemetry.batch_capture.return_value = True

        with patch("socket.create_connection"), \
             patch.object(gw, "BATCH_SIZE", 2), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            gw._maybe_sync_telemetry(artifact_root)

        # Verify record 3 was sent (NOT records 1 and 2)
        assert mock_telemetry.batch_capture.called
        events_sent = mock_telemetry.batch_capture.call_args[0][0]
        event_names = [e["event_name"] for e in events_sent]
        assert event_names == ["ev3"], f"Expected ['ev3'], got {event_names}"
