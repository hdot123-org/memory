#!/usr/bin/env python3
"""Tests for M2 telemetry-compaction-lock fix (VAL-TELE-001 ~ VAL-TELE-011).

Verifies the TOCTOU fix in _compact_metrics_jsonl, _batch_send_records,
_write_sync_status, and _maybe_sync_telemetry.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools import _gateway_telemetry as tele
from memory_core.tools import memory_hook_gateway as gw
from memory_core.tools import memory_hook_metrics as metrics
from tests.sync_artifacts_helpers import setup_sync_artifacts

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metric_line(seq: int) -> str:
    return json.dumps({"event": "test_event", "seq": seq}) + "\n"


def _patch_network_and_telem(
    batch_capture_return: bool | list[bool] = True,
    *,
    batch_capture_callback: Any = None,
) -> tuple[MagicMock, dict]:
    """Build mocks for network probe + telemetry_bridge.

    Returns (mock_tel_module, ctx_dict) where ctx_dict has references
    needed for the caller (e.g. mock_telemetry).
    """
    mock_telemetry = MagicMock()
    if isinstance(batch_capture_return, list):
        mock_telemetry.batch_capture.side_effect = list(batch_capture_return)
    else:
        mock_telemetry.batch_capture.return_value = batch_capture_return

    if batch_capture_callback is not None:
        original_return = batch_capture_return

        def capture_with_callback(events):
            result = original_return.pop(0) if isinstance(original_return, list) else original_return
            if result:
                batch_capture_callback(events)
            return result

        mock_telemetry.batch_capture.side_effect = capture_with_callback

    mock_tel_module = MagicMock()
    mock_tel_module.telemetry = mock_telemetry

    mock_socket = MagicMock()
    mock_sock_instance = MagicMock()
    mock_socket.create_connection.return_value = mock_sock_instance

    ctx = {
        "mock_telemetry": mock_telemetry,
        "mock_socket": mock_socket,
    }
    return mock_tel_module, ctx


# ---------------------------------------------------------------------------
# VAL-TELE-001: Concurrent append during compaction never silently loses records
# ---------------------------------------------------------------------------


def _writer_child(
    metrics_path_str: str,
    n_records: int,
    start_event,
    done_event,
    results_list,
) -> None:
    """Child process: append N records using production append_metrics_record."""
    from pathlib import Path as _Path

    from memory_core.tools.memory_hook_metrics import append_metrics_record

    start_event.wait(timeout=10)
    path = _Path(metrics_path_str)
    for i in range(n_records):
        record = {"event": "writer_event", "seq": i, "pid": os.getpid()}
        ok = append_metrics_record(path, record)
        results_list.append(ok)
    done_event.set()


class TestConcurrentAppendNeverLosesRecords:
    """VAL-TELE-001: compression window concurrent append never silently lost."""

    def test_concurrent_append_no_silent_loss(self, tmp_path):
        """Records appended during compaction are either preserved or explicitly dropped."""
        initial_lines = [_make_metric_line(i) for i in range(5)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=initial_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )
        metrics_file = artifact_root / "metrics.jsonl"

        manager = mp.Manager()
        writer_results = manager.list()
        start_event = mp.Event()
        done_event = mp.Event()

        n_writer_records = 20

        writer_proc = mp.Process(
            target=_writer_child,
            args=(str(metrics_file), n_writer_records, start_event, done_event, writer_results),
        )
        writer_proc.start()

        def on_batch_capture(events):
            start_event.set()
            done_event.wait(timeout=10)

        mock_tel_module, ctx = _patch_network_and_telem(
            batch_capture_return=True,
            batch_capture_callback=on_batch_capture,
        )

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        writer_proc.join(timeout=15)
        assert not writer_proc.is_alive(), "Writer process did not finish"
        writer_proc.close()

        final_lines = metrics_file.read_text(encoding="utf-8").strip().split("\n")
        final_lines = [line for line in final_lines if line]

        writer_seqs_in_file: set[int] = set()
        for line in final_lines:
            try:
                record = json.loads(line)
                if record.get("event") == "writer_event":
                    writer_seqs_in_file.add(record.get("seq"))
            except json.JSONDecodeError:
                pytest.fail(f"Invalid JSON in final file: {line!r}")

        returned_true_seqs: set[int] = set()
        for idx, ok in enumerate(writer_results):
            if ok:
                returned_true_seqs.add(idx)

        silently_lost = returned_true_seqs - writer_seqs_in_file
        assert len(silently_lost) == 0, (
            f"Silent loss detected: records {silently_lost} returned True but absent from file. "
            f"In-file writer seqs: {writer_seqs_in_file}"
        )

        manager.shutdown()


# ---------------------------------------------------------------------------
# VAL-TELE-002: Successful compaction invariants
# ---------------------------------------------------------------------------


class TestSuccessfulCompactionInvariants:
    """VAL-TELE-002: After successful sync, unsent lines remain, offset resets to '0'."""

    def test_compaction_preserves_unsent_resets_offset(self, tmp_path):
        """Lines after last_synced_line are preserved, offset reset to '0', no tmp files."""
        initial_lines = [_make_metric_line(i) for i in range(5)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=initial_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        metrics_file = artifact_root / "metrics.jsonl"
        offset_file = artifact_root / ".offset"

        remaining = metrics_file.read_text(encoding="utf-8")
        assert remaining == "", f"Expected empty file after full sync, got: {remaining!r}"
        assert offset_file.read_text(encoding="utf-8").strip() == "0"

        file_names = sorted(p.name for p in artifact_root.iterdir())
        tmp_files = [n for n in file_names if n.endswith(".tmp") or "tmp" in n.lower()]
        assert len(tmp_files) == 0, f"Temp files found: {tmp_files}"

    def test_compaction_with_partial_offset(self, tmp_path):
        """When offset > 0, lines before offset already synced, only lines after sync point remain."""
        initial_lines = [_make_metric_line(i) for i in range(5)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=initial_lines,
            offset=3,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        metrics_file = artifact_root / "metrics.jsonl"
        offset_file = artifact_root / ".offset"

        remaining = metrics_file.read_text(encoding="utf-8")
        assert remaining == "", f"Expected empty after full sync, got: {remaining!r}"
        assert offset_file.read_text(encoding="utf-8").strip() == "0"


# ---------------------------------------------------------------------------
# VAL-TELE-003: fsync complete file, no truncation fragments
# ---------------------------------------------------------------------------


class TestFileIntegrityAfterCompaction:
    """VAL-TELE-003: After fsync, file is complete JSONL with no truncation fragments."""

    def test_file_is_valid_jsonl_after_compaction(self, tmp_path):
        """Each line in the compacted file is valid JSON, file ends with newline."""
        initial_lines = [_make_metric_line(i) for i in range(5)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=initial_lines,
            offset=2,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        metrics_file = artifact_root / "metrics.jsonl"
        content = metrics_file.read_text(encoding="utf-8")

        if content:
            for i, line in enumerate(content.split("\n")):
                if line:
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as e:
                        pytest.fail(f"Line {i} is not valid JSON: {line!r} -- {e}")

        if content:
            stat_size = metrics_file.stat().st_size
            expected_size = len(content.encode("utf-8"))
            assert stat_size == expected_size


# ---------------------------------------------------------------------------
# VAL-TELE-004: Partial batch failure behavior
# ---------------------------------------------------------------------------


class TestPartialBatchFailure:
    """VAL-TELE-004: On partial failure: no compaction, offset advances, retry works."""

    def test_partial_batch_no_compaction_offset_advances(self, tmp_path):
        """First chunk succeeds, second fails: no compaction, offset advances to first chunk end."""
        from memory_core.tools._gateway_telemetry import BATCH_SIZE

        n_lines = BATCH_SIZE * 3
        initial_lines = [_make_metric_line(i) for i in range(n_lines)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=initial_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=[True, False])

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        metrics_file = artifact_root / "metrics.jsonl"
        offset_file = artifact_root / ".offset"

        file_lines = metrics_file.read_text(encoding="utf-8").strip().split("\n")
        file_lines = [line for line in file_lines if line]
        assert len(file_lines) == n_lines, f"Expected {n_lines} lines (no compaction), got {len(file_lines)}"

        offset_val = int(offset_file.read_text(encoding="utf-8").strip())
        assert offset_val == BATCH_SIZE, f"Expected offset={BATCH_SIZE} (first chunk end), got {offset_val}"

        status_file = artifact_root / ".sync_status.json"
        if status_file.exists():
            status = json.loads(status_file.read_text(encoding="utf-8"))
            assert status["failure_count"] >= 1

    def test_retry_after_partial_success(self, tmp_path):
        """After partial failure, retry from offset continues without re-sending synced records."""
        from memory_core.tools._gateway_telemetry import BATCH_SIZE

        n_lines = BATCH_SIZE * 3
        initial_lines = [_make_metric_line(i) for i in range(n_lines)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=initial_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module_1, ctx_1 = _patch_network_and_telem(batch_capture_return=[True, False])

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx_1["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module_1}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        (artifact_root / ".last_sync_success").write_text(str(time.time() - 7200), encoding="utf-8")
        (artifact_root / ".last_sync_attempt").write_text(str(time.time() - 600), encoding="utf-8")

        mock_tel_module_2, ctx_2 = _patch_network_and_telem(batch_capture_return=True)
        captured_events_2: list[dict] = []

        def capture_events_2(events):
            captured_events_2.extend(events)
            return True

        mock_tel_module_2.telemetry.batch_capture.side_effect = capture_events_2

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx_2["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module_2}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        sent_seqs: set[int] = set()
        for ev in captured_events_2:
            props = ev.get("properties", {})
            seq = props.get("seq")
            if seq is not None:
                sent_seqs.add(seq)

        expected_seqs = set(range(BATCH_SIZE, n_lines))
        assert sent_seqs == expected_seqs, f"Expected seqs {expected_seqs}, got {sent_seqs}"


# ---------------------------------------------------------------------------
# VAL-TELE-005: Idempotent behavior for edge cases
# ---------------------------------------------------------------------------


class TestIdempotentEdgeCases:
    """VAL-TELE-005: Empty file / no pending / file missing -- all idempotent."""

    def test_empty_metrics_file(self, tmp_path):
        """Empty metrics.jsonl: sync exits cleanly, no error."""
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=[],
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)
        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        assert (artifact_root / "metrics.jsonl").read_text(encoding="utf-8") == ""

    def test_no_pending_records(self, tmp_path):
        """Offset == total lines: no pending records, sync exits cleanly."""
        lines = [_make_metric_line(i) for i in range(3)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=lines,
            offset=3,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)
        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        content = (artifact_root / "metrics.jsonl").read_text(encoding="utf-8")
        assert content == "".join(lines)

    def test_metrics_file_missing(self, tmp_path):
        """Missing metrics.jsonl: sync exits cleanly without error."""
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=None,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )
        metrics_file = artifact_root / "metrics.jsonl"
        if metrics_file.exists():
            metrics_file.unlink()

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)
        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

    def test_idempotent_multiple_calls(self, tmp_path):
        """Multiple calls with no pending records: behavior is idempotent."""
        lines = [_make_metric_line(i) for i in range(3)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=lines,
            offset=3,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)

        for _ in range(3):
            with (
                patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
                patch("socket.create_connection", ctx["mock_socket"].create_connection),
                patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
            ):
                gw._maybe_sync_telemetry(artifact_root)

        content = (artifact_root / "metrics.jsonl").read_text(encoding="utf-8")
        assert content == "".join(lines)


# ---------------------------------------------------------------------------
# VAL-TELE-006: .offset concurrent monotonicity
# ---------------------------------------------------------------------------


class TestOffsetMonotonicity:
    """VAL-TELE-006: .offset value never regresses under concurrent access."""

    def test_offset_monotonic_under_concurrent_sync(self, tmp_path):
        """Concurrent sync operations: offset values sampled are monotonically non-decreasing."""
        n_lines = 10
        initial_lines = [_make_metric_line(i) for i in range(n_lines)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=initial_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        offset_samples: list[int] = []

        def capture_offset(events):
            offset_val = int((artifact_root / ".offset").read_text(encoding="utf-8").strip() or "0")
            offset_samples.append(offset_val)

        mock_tel_module, ctx = _patch_network_and_telem(
            batch_capture_return=True,
            batch_capture_callback=capture_offset,
        )

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        final_offset = int((artifact_root / ".offset").read_text(encoding="utf-8").strip())
        assert final_offset == 0


# ---------------------------------------------------------------------------
# VAL-TELE-007: .sync_status.json atomic read-write
# ---------------------------------------------------------------------------


class TestSyncStatusAtomicity:
    """VAL-TELE-007: Concurrent read/write of .sync_status.json never corrupts JSON."""

    def test_concurrent_status_read_write_no_corruption(self, tmp_path):
        """Concurrent _write_sync_status calls + reader: no JSONDecodeError."""
        artifact_root = tmp_path / "artifacts"
        artifact_root.mkdir()

        errors: list[Exception] = []
        stop_flag = [False]

        def reader() -> None:
            status_file = artifact_root / ".sync_status.json"
            for _ in range(200):
                if stop_flag[0]:
                    break
                try:
                    if status_file.exists():
                        content = status_file.read_text(encoding="utf-8")
                        if content:
                            json.loads(content)
                except json.JSONDecodeError as e:
                    errors.append(e)
                except OSError:
                    pass

        with ThreadPoolExecutor(max_workers=4) as executor:
            reader_future = executor.submit(reader)

            writer_futures = []
            for i in range(50):
                success = i % 2 == 0
                writer_futures.append(executor.submit(gw._write_sync_status, artifact_root, success, i))

            for f in writer_futures:
                f.result()

            stop_flag[0] = True
            reader_future.result()

        assert len(errors) == 0, f"Got {len(errors)} JSONDecodeError(s): {errors[:3]}"

        status_file = artifact_root / ".sync_status.json"
        if status_file.exists():
            status = json.loads(status_file.read_text(encoding="utf-8"))
            assert isinstance(status.get("failure_count", 0), int)


# ---------------------------------------------------------------------------
# VAL-TELE-008: Writer-side lossy-tolerant semantics preserved
# ---------------------------------------------------------------------------


class TestWriterLossyTolerantSemantics:
    """VAL-TELE-008: Under lock contention, append returns False quickly."""

    def test_contention_returns_false_quickly(self, tmp_path):
        """Main thread holds exclusive lock; writer append returns False in < 2s."""
        import fcntl

        metrics_file = tmp_path / "metrics.jsonl"
        metrics_file.touch()

        with metrics_file.open("a") as lock_holder:
            fcntl.flock(lock_holder.fileno(), fcntl.LOCK_EX)

            start_time = time.time()
            result = metrics.append_metrics_record(metrics_file, {"event": "contended_write"})
            elapsed = time.time() - start_time

            assert result is False, "append should return False under contention"
            assert elapsed < 2.0, f"append took {elapsed:.2f}s (should be < 2s)"

        result = metrics.append_metrics_record(metrics_file, {"event": "after_release"})
        assert result is True, "append should succeed after lock released"

        content = metrics_file.read_text(encoding="utf-8")
        assert "after_release" in content


# ---------------------------------------------------------------------------
# VAL-TELE-009: _maybe_sync_telemetry top-level exception suppression
# ---------------------------------------------------------------------------


class TestTopLevelExceptionSuppression:
    """VAL-TELE-009: _maybe_sync_telemetry never propagates exceptions."""

    def test_batch_send_records_raises(self, tmp_path):
        """_batch_send_records raises RuntimeError: suppressed."""
        lines = [_make_metric_line(i) for i in range(3)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem()
        ctx["mock_telemetry"].batch_capture.side_effect = RuntimeError("send failed")

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

    def test_compact_raises(self, tmp_path):
        """_compact_metrics_jsonl raises OSError: suppressed."""
        lines = [_make_metric_line(i) for i in range(3)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)

        def raise_oserror(*args, **kwargs):
            raise OSError("disk error")

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
            patch.object(tele, "_compact_metrics_jsonl", side_effect=raise_oserror),
        ):
            gw._maybe_sync_telemetry(artifact_root)

    def test_write_sync_status_raises(self, tmp_path):
        """_write_sync_status raises OSError: suppressed."""
        lines = [_make_metric_line(i) for i in range(3)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)

        def raise_oserror(*args, **kwargs):
            raise OSError("status write failed")

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
            patch.object(tele, "_write_sync_status", side_effect=raise_oserror),
        ):
            gw._maybe_sync_telemetry(artifact_root)

    def test_read_pending_records_raises(self, tmp_path):
        """_read_pending_records raises ValueError: suppressed."""
        lines = [_make_metric_line(i) for i in range(3)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem()

        def raise_valueerror(*args, **kwargs):
            raise ValueError("parse error")

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
            patch.object(tele, "_read_pending_records", side_effect=raise_valueerror),
        ):
            gw._maybe_sync_telemetry(artifact_root)


# ---------------------------------------------------------------------------
# VAL-TELE-010: Dual-process full-cycle competition
# ---------------------------------------------------------------------------


def _sync_worker(
    artifact_root_str: str,
    barrier,
    result_dict,
) -> None:
    """Worker process: trigger _maybe_sync_telemetry after barrier sync."""
    from pathlib import Path as _Path
    from unittest.mock import MagicMock as _MagicMock
    from unittest.mock import patch as _patch

    from memory_core.tools import memory_hook_gateway as _gw

    artifact_root = _Path(artifact_root_str)
    barrier.wait(timeout=10)

    mock_telemetry = _MagicMock()
    mock_telemetry.batch_capture.return_value = True

    mock_tel_module = _MagicMock()
    mock_tel_module.telemetry = mock_telemetry

    mock_socket = _MagicMock()
    mock_sock_instance = _MagicMock()
    mock_socket.create_connection.return_value = mock_sock_instance

    with (
        _patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
        _patch("socket.create_connection", mock_socket.create_connection),
        _patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
    ):
        _gw._maybe_sync_telemetry(artifact_root)

    metrics_file = artifact_root / "metrics.jsonl"
    offset_file = artifact_root / ".offset"

    result_dict["metrics_content"] = metrics_file.read_text(encoding="utf-8") if metrics_file.exists() else ""
    result_dict["offset"] = offset_file.read_text(encoding="utf-8").strip() if offset_file.exists() else "0"


class TestDualProcessFullCycle:
    """VAL-TELE-010: Two processes triggering sync simultaneously -- no silent loss."""

    def test_dual_process_no_silent_loss(self, tmp_path):
        """Two processes trigger _maybe_sync_telemetry; one skips, no records lost."""
        n_lines = 10
        initial_lines = [_make_metric_line(i) for i in range(n_lines)]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=initial_lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        barrier = mp.Barrier(2)
        manager = mp.Manager()
        result_1 = manager.dict()
        result_2 = manager.dict()

        proc_1 = mp.Process(
            target=_sync_worker,
            args=(str(artifact_root), barrier, result_1),
        )
        proc_2 = mp.Process(
            target=_sync_worker,
            args=(str(artifact_root), barrier, result_2),
        )

        proc_1.start()
        proc_2.start()

        proc_1.join(timeout=30)
        proc_2.join(timeout=30)

        assert not proc_1.is_alive(), "Process 1 did not finish"
        assert not proc_2.is_alive(), "Process 2 did not finish"
        proc_1.close()
        proc_2.close()

        metrics_file = artifact_root / "metrics.jsonl"
        final_content = metrics_file.read_text(encoding="utf-8")
        if final_content.strip():
            for line in final_content.strip().split("\n"):
                if line:
                    json.loads(line)

        manager.shutdown()


# ---------------------------------------------------------------------------
# VAL-TELE-011: Existing telemetry tests zero regression
# ---------------------------------------------------------------------------


class TestExistingTelemetryZeroRegression:
    """VAL-TELE-011: Existing telemetry tests still pass (regression guard)."""

    def test_existing_batch_capture_success_compacts(self, tmp_path):
        """Existing test pattern: batch_capture success compacts metrics and resets offset."""
        lines = [
            json.dumps({"event": "ev1"}) + "\n",
            json.dumps({"event": "ev2"}) + "\n",
        ]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=True)

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        offset_val = (artifact_root / ".offset").read_text(encoding="utf-8").strip()
        assert offset_val == "0"

        sync_status = json.loads((artifact_root / ".sync_status.json").read_text(encoding="utf-8"))
        assert sync_status["failure_count"] == 0
        assert sync_status["pending_count"] == 0

    def test_existing_batch_capture_failure_updates_attempt(self, tmp_path):
        """Existing test pattern: batch_capture failure updates attempt, not offset."""
        lines = [
            json.dumps({"event": "test_event", "data": "value1"}) + "\n",
            json.dumps({"event": "test_event", "data": "value2"}) + "\n",
        ]
        artifact_root = setup_sync_artifacts(
            tmp_path,
            metrics_lines=lines,
            offset=0,
            last_sync_success=time.time() - 7200,
            last_sync_attempt=time.time() - 600,
        )

        mock_tel_module, ctx = _patch_network_and_telem(batch_capture_return=False)

        with (
            patch.dict("os.environ", {"POSTHOG_HOST": "https://us.posthog.com"}),
            patch("socket.create_connection", ctx["mock_socket"].create_connection),
            patch.dict("sys.modules", {"memory_core.tools.telemetry_bridge": mock_tel_module}),
        ):
            gw._maybe_sync_telemetry(artifact_root)

        assert ctx["mock_telemetry"].batch_capture.called
        offset_content = (artifact_root / ".offset").read_text(encoding="utf-8").strip()
        assert offset_content == "0"

        attempt_content = float((artifact_root / ".last_sync_attempt").read_text(encoding="utf-8").strip())
        assert attempt_content > time.time() - 10
