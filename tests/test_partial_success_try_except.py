"""Test VAL-SYNC-003: partial-success path has try/except around write_text.

Verifies that last_sync_attempt_file.write_text in the partial-success else branch
is wrapped in try/except OSError, matching the pattern in the outer except block.

If write_text fails with OSError in the partial-success branch, the exception must
NOT propagate to the outer except block (which uses wrong pending_count).
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


class TestPartialSuccessTryExcept:
    """VAL-SYNC-003: partial-success else branch write_text is guarded by try/except OSError."""

    def test_partial_success_write_text_oserror_does_not_propagate(self, tmp_path):
        """If last_sync_attempt_file.write_text raises OSError in partial-success branch,
        the exception must be caught and NOT propagate to outer except block."""
        # File has 3 records with BATCH_SIZE=2 -> 2 chunks
        # Chunk 1 succeeds, chunk 2 fails -> partial success
        metrics_lines = [
            json.dumps({"event": "ev1"}) + "\n",
            json.dumps({"event": "ev2"}) + "\n",
            json.dumps({"event": "ev3"}) + "\n",
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            last_sync_success=time.time() - 7200,
        )

        mock_telemetry = MagicMock()
        call_count = [0]
        def batch_capture_side_effect(events):
            call_count[0] += 1
            if call_count[0] == 1:
                return True  # first chunk succeeds
            return False  # second chunk fails -> partial success
        mock_telemetry.batch_capture.side_effect = batch_capture_side_effect

        # Make last_sync_attempt_file.write_text raise OSError
        original_write_text = Path.write_text
        def write_text_side_effect(self_path, data, *args, **kwargs):
            if self_path.name == ".last_sync_attempt":
                raise OSError("disk full")
            return original_write_text(self_path, data, *args, **kwargs)

        # The function should NOT raise - it should handle the OSError gracefully
        with patch("socket.create_connection"), \
             patch.object(gw, "BATCH_SIZE", 2), \
             patch.object(Path, "write_text", write_text_side_effect), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            # This should NOT raise an exception
            gw._maybe_sync_telemetry(artifact_root)

        # Verify _write_sync_status was called with CORRECT partial-success values
        # (remaining=1 record, NOT pending_count=3 which outer except would use)
        sync_status_path = artifact_root / ".sync_status.json"
        assert sync_status_path.exists(), "sync_status.json should still be written"
        import json as json_mod
        status = json_mod.loads(sync_status_path.read_text(encoding="utf-8"))
        # CRITICAL: If OSError from write_text propagates to outer except,
        # it uses pending_count=3 instead of remaining=1
        assert status["pending_count"] == 1, \
            f"Expected remaining=1 (partial-success), got {status['pending_count']} (outer-except used wrong pending_count)"
        assert "last_failure_ts" in status, "Should have last_failure_ts (not last_success_ts)"
        assert "last_success_ts" not in status, "Should not have last_success_ts"

    def test_partial_success_write_text_oserror_uses_correct_remaining(self, tmp_path):
        """Verify the partial-success branch uses correct remaining count (not pending_count)."""
        # 5 records with BATCH_SIZE=2:
        # Chunk 1 (2 records): succeed
        # Chunk 2 (2 records): succeed
        # Chunk 3 (1 record): fail -> partial success with remaining=1
        metrics_lines = [
            json.dumps({"event": f"ev{i}"}) + "\n"
            for i in range(5)
        ]
        artifact_root = _setup_sync_artifacts(
            tmp_path,
            metrics_lines=metrics_lines,
            last_sync_success=time.time() - 7200,
        )

        mock_telemetry = MagicMock()
        call_count = [0]
        def batch_capture_side_effect(events):
            call_count[0] += 1
            return call_count[0] <= 2  # first 2 chunks succeed, 3rd fails
        mock_telemetry.batch_capture.side_effect = batch_capture_side_effect

        with patch("socket.create_connection"), \
             patch.object(gw, "BATCH_SIZE", 2), \
             patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": MagicMock(telemetry=mock_telemetry)}):
            gw._maybe_sync_telemetry(artifact_root)

        # Check sync_status.json has correct remaining count
        sync_status_path = artifact_root / ".sync_status.json"
        assert sync_status_path.exists()
        import json as json_mod
        status = json_mod.loads(sync_status_path.read_text(encoding="utf-8"))
        # remaining should be 1 (5 total - 4 synced = 1), not 5 (pending_count)
        assert status["pending_count"] == 1, f"Expected remaining=1, got {status['pending_count']}"
        # Verify it's marked as a failure (partial success = failure)
        assert "last_failure_ts" in status, "Should have last_failure_ts"
