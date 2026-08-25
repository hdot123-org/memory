#!/usr/bin/env python3
"""Discrimination + storm tests for .sync_status.json / .offset pre-creation race.

Root cause: _write_sync_status pre-creates with write_text('{}') = open('w') O_TRUNC + write.
Interleaving: B pre-creates open('w') truncates, suspended before write → C opens 'r+' + LOCK_EX
writes N bytes JSON, releases → B resumes at offset 0 writes '{}' without truncating → disk
tear '{}'+C[2:] → LOCK_SH reader json.loads reports "Extra data: line 1 column 3 (char 2)".

Fix: pre-creation changed to touch() (O_CREAT single syscall, no truncate, no data write).

Discrimination strategy (concurrency-test-discrimination.md round-3 form 4):
monkeypatch Path.open — .sync_status.json opened with 'w' mode → real open + sleep 0.5s.
This deterministically widens the pre-creation window from sub-millisecond to 0.5s.

RED on main@85862ad: tear '{}' + tail observable.
GREEN on fix branch: touch() doesn't go through 'w' open → injection not triggered.
"""

from __future__ import annotations

import fcntl
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import patch

import pytest

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools import _gateway_telemetry as tele
from memory_core.tools import memory_hook_gateway as gw

# ---------------------------------------------------------------------------
# Discrimination test: deterministic tear detection via Path.open monkeypatch
# ---------------------------------------------------------------------------


class TestPrecreationRaceDiscrimination:
    """Deterministic discrimination: monkeypatch Path.open to widen O_TRUNC window.

    On main@85862ad (write_text pre-creation): tear IS observable → test RED.
    On fix (touch pre-creation): touch() uses O_CREAT → no 'w' open → injection
    not triggered → test GREEN.
    """

    def test_sync_status_precreation_tear_deterministic(self, tmp_path):
        """Monkeypatch Path.open to inject delay on 'w' mode for .sync_status.json.

        Orchestration:
        1. Thread B calls _write_sync_status (file doesn't exist → pre-create path)
        2. B's write_text('{}') internally calls open('w') → monkeypatched to sleep 0.5s
        3. During B's sleep, thread C calls _write_sync_status (file exists, skip pre-create)
        4. C acquires LOCK_EX on 'r+' handle, writes full JSON (~80 bytes), releases
        5. B resumes, writes '{}' at offset 0 on B's handle (no truncation)
        6. Final file: '{}'+C[2:] → torn → JSONDecodeError

        On fix: touch() doesn't use 'w' mode → no delay → B completes pre-create instantly
        → C sees file with '{}' → C's lock-protected write overwrites cleanly → valid JSON.
        """
        artifact_root = tmp_path / "artifacts"
        artifact_root.mkdir()
        status_file = artifact_root / ".sync_status.json"

        # Ensure file doesn't exist (triggers pre-create path)
        assert not status_file.exists()

        original_path_open = Path.open
        b_started = threading.Event()
        c_can_proceed = threading.Event()

        def patched_path_open(self_path, mode="r", *args, **kwargs):
            """Inject delay when .sync_status.json is opened in 'w' mode."""
            if "w" in mode and str(self_path).endswith(".sync_status.json"):
                # Do the real open first (truncates file)
                handle = original_path_open(self_path, mode, *args, **kwargs)
                # Signal that B has entered the pre-create open('w')
                b_started.set()
                # Wait until C has finished its lock-protected write
                c_can_proceed.wait(timeout=10)
                # Small extra delay to ensure C has fully released
                time.sleep(0.1)
                return handle
            return original_path_open(self_path, mode, *args, **kwargs)

        def thread_b():
            """Thread B: first writer, hits pre-create path with injected delay."""
            tele._write_sync_status(artifact_root, success=True, pending_count=0)

        def thread_c():
            """Thread C: second writer, waits for B to enter pre-create then writes."""
            # Wait for B to enter the 'w' open (and be sleeping)
            b_started.wait(timeout=10)
            # Give B a moment to be truly suspended inside the patched open
            time.sleep(0.1)
            # Now C writes — on main: C opens 'r+', acquires LOCK_EX, writes full JSON
            tele._write_sync_status(artifact_root, success=False, pending_count=5)
            # Signal B can proceed (resume from sleep and write '{}')
            c_can_proceed.set()

        with patch.object(Path, "open", patched_path_open), ThreadPoolExecutor(max_workers=2) as executor:
            future_b = executor.submit(thread_b)
            future_c = executor.submit(thread_c)
            future_b.result(timeout=30)
            future_c.result(timeout=30)

        # Now check the final file state
        content = status_file.read_text(encoding="utf-8")
        print(f"DEBUG: Final file content: {content!r} (len={len(content)})")

        # Try to parse as JSON
        try:
            parsed = json.loads(content)
            print(f"DEBUG: Successfully parsed JSON: {parsed}")
        except json.JSONDecodeError as e:
            # On main@85862ad: tear is observable → JSONDecodeError
            # This means the test correctly discriminates the bug
            pytest.fail(
                f"TORN FILE DETECTED (expected on unfixed code): "
                f"content={content!r}, error={e}. "
                f"This confirms the O_TRUNC pre-creation race."
            )

        # On fix: file should be valid JSON with expected fields
        assert isinstance(parsed, dict)
        # C's write should be the final one (or B's, but either should be valid)
        assert "pending_count" in parsed


# ---------------------------------------------------------------------------
# Storm regression: 4 threads × multiple fresh roots, 0 JSONDecodeError
# ---------------------------------------------------------------------------


class TestPrecreationStormRegression:
    """Storm regression: 4 threads × multiple fresh artifact_roots.

    Concurrent first-write + LOCK_SH reader per root. 0 JSONDecodeError.
    Each root's final file must be valid JSON.
    """

    @staticmethod
    def _reader(root_idx: int, status_file: Path, stop_flags: dict[int, bool], errors: list[Exception]) -> None:
        """Reader: try to parse .sync_status.json 100 times."""
        for _ in range(100):
            if stop_flags.get(root_idx, False):
                break
            try:
                if status_file.exists():
                    with status_file.open("r", encoding="utf-8") as f:
                        try:
                            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                            content = f.read()
                        finally:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    if content:
                        json.loads(content)
            except json.JSONDecodeError as e:
                errors.append(e)
            except OSError:
                pass

    def test_storm_concurrent_first_write_no_corruption(self, tmp_path):
        """4 threads × 10 fresh roots = 40 concurrent _write_sync_status calls."""
        n_roots = 10
        errors: list[Exception] = []
        stop_flags: dict[int, bool] = {}
        futures = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            for root_idx in range(n_roots):
                root = tmp_path / f"root_{root_idx}"
                root.mkdir()
                stop_flags[root_idx] = False
                status_file = root / ".sync_status.json"

                futures.append(executor.submit(self._reader, root_idx, status_file, stop_flags, errors))

                for w_idx in range(4):
                    success = w_idx % 2 == 0
                    futures.append(executor.submit(tele._write_sync_status, root, success, w_idx))

            for f in as_completed(futures):
                f.result()

            for root_idx in range(n_roots):
                stop_flags[root_idx] = True

            for f in futures:
                if f.done():
                    f.result()

        assert len(errors) == 0, f"Storm: got {len(errors)} JSONDecodeError(s) across {n_roots} roots: {errors[:3]}"

        for root_idx in range(n_roots):
            status_file = tmp_path / f"root_{root_idx}" / ".sync_status.json"
            if status_file.exists():
                content = status_file.read_text(encoding="utf-8")
                if content:
                    parsed = json.loads(content)
                    assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# .offset pre-creation regression: #1029 B1 fresh-root zero regression
# ---------------------------------------------------------------------------


class TestOffsetPrecreationRegression:
    """Verify #1029 B1 fresh-root regression passes after .offset pre-creation fix."""

    def _make_metric_line(self, seq: int) -> str:
        return json.dumps({"event": "test_event", "seq": seq}) + "\n"

    def test_fresh_root_offset_creation(self, tmp_path):
        """B1: fresh artifact root (no .offset) syncs successfully."""

        artifact_root = tmp_path / "artifacts"
        artifact_root.mkdir()

        metrics_file = artifact_root / "metrics.jsonl"
        initial_lines = [self._make_metric_line(i) for i in range(5)]
        metrics_file.write_text("".join(initial_lines), encoding="utf-8")

        (artifact_root / ".last_sync_success").write_text(str(time.time() - 7200), encoding="utf-8")
        (artifact_root / ".last_sync_attempt").write_text(str(time.time() - 600), encoding="utf-8")

        offset_file = artifact_root / ".offset"
        assert not offset_file.exists()

        sent_events: list[dict] = []

        def capture_and_track(events):
            sent_events.extend(events)
            return True

        mock_telemetry = pytest.importorskip("unittest.mock").MagicMock()
        mock_telemetry.batch_capture.side_effect = capture_and_track
        mock_tel_module = pytest.importorskip("unittest.mock").MagicMock()
        mock_tel_module.telemetry = mock_telemetry

        mock_socket = pytest.importorskip("unittest.mock").MagicMock()
        mock_sock_instance = pytest.importorskip("unittest.mock").MagicMock()
        mock_socket.create_connection.return_value = mock_sock_instance

        import os
        from unittest.mock import patch

        with (
            patch.dict(os.environ, {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", mock_socket.create_connection),
            patch.dict(sys.modules, {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        assert offset_file.exists(), ".offset must be created after first sync"
        offset_val = int(offset_file.read_text(encoding="utf-8").strip())
        assert offset_val == 0, f"Expected offset=0 after compaction, got {offset_val}"

        remaining = metrics_file.read_text(encoding="utf-8")
        assert remaining == "", f"Expected empty after full sync, got: {remaining!r}"
        assert len(sent_events) == 5
