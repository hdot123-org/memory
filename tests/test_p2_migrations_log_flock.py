"""Concurrency test for migrations.log fcntl.flock.

Spawns 5 threads that simultaneously call the internal _append_migrations_log
helper; asserts that exactly 5 lines are written, each line parses as valid
migration-log format, with no truncation or corruption.
"""

import json
import threading
from pathlib import Path

from memory_core.constants import MIGRATION_LOG_LINE_PATTERN

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_append(log_path: Path, thread_id: int) -> None:
    """Invoke _append_migrations_log from a worker thread."""
    from memory_core.tools.migrate_project_memory import (
        _append_migrations_log,
    )

    line = json.dumps({"thread": thread_id, "status": "test"})
    _append_migrations_log(log_path, line)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrationsLogFlock:
    """5-thread concurrent write to migrations.log."""

    def test_five_threads_exactly_five_lines(self, tmp_path: Path) -> None:
        """5 threads each write one line; result must have exactly 5 lines."""
        log_file = tmp_path / "migrations.log"
        log_file.write_text("# Migrations Log\n", encoding="utf-8")

        num_threads = 5
        threads: list[threading.Thread] = []
        for i in range(num_threads):
            t = threading.Thread(target=_run_append, args=(log_file, i))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        content = log_file.read_text(encoding="utf-8")
        # Filter out comment lines (starting with #)
        lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
        assert len(lines) == num_threads, (
            f"Expected {num_threads} data lines, got {len(lines)}:\n{content}"
        )

    def test_all_lines_parseable_json(self, tmp_path: Path) -> None:
        """Every written line must be valid JSON (our test format)."""
        log_file = tmp_path / "migrations.log"
        log_file.write_text("# Migrations Log\n", encoding="utf-8")

        num_threads = 5
        threads: list[threading.Thread] = []
        for i in range(num_threads):
            t = threading.Thread(target=_run_append, args=(log_file, i))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        content = log_file.read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
        for line in lines:
            # Each line should be parseable JSON (our test writes JSON payloads)
            data = json.loads(line)
            assert "thread" in data
            assert "status" in data

    def test_no_truncated_lines(self, tmp_path: Path) -> None:
        """No line should be truncated or corrupted."""
        log_file = tmp_path / "migrations.log"
        log_file.write_text("# Migrations Log\n", encoding="utf-8")

        num_threads = 5
        threads: list[threading.Thread] = []
        for i in range(num_threads):
            t = threading.Thread(target=_run_append, args=(log_file, i))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        content = log_file.read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]

        for line in lines:
            # Must be valid JSON (no truncation)
            data = json.loads(line)
            assert data["status"] == "test"

    def test_log_line_matches_pattern(self, tmp_path: Path) -> None:
        """Real migration log lines (from append_migration_log) match MIGRATION_LOG_LINE_PATTERN."""

        from memory_core.tools.migrate_project_memory import append_migration_log

        num_threads = 5

        def _write_real_log(thread_id: int) -> None:

            # Use a fake target directory just to get a log path
            mem_root = tmp_path / f"mem_{thread_id}"
            mem_root.mkdir()
            append_migration_log(
                mem_root,
                from_version="0.1.0",
                to_version="0.2.0",
                status="success",
                detail=f"Thread {thread_id}",
            )

        # Since each thread creates its own dir, collect all logs
        threads: list[threading.Thread] = []
        for i in range(num_threads):
            t = threading.Thread(target=_write_real_log, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Verify each log file has exactly one valid line
        for i in range(num_threads):
            log_file_i = tmp_path / f"mem_{i}" / "migrations.log"
            content = log_file_i.read_text(encoding="utf-8")
            data_lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
            assert len(data_lines) == 1
            assert MIGRATION_LOG_LINE_PATTERN.match(data_lines[0]) is not None
