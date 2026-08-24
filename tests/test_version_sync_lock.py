"""Tests for INFRA-545: .sync.lock best-effort concurrency guard.

Covers:
- Lock is created during sync and cleaned up after (no residue)
- Concurrent holder (existing .sync.lock, fresh mtime) → sync skipped, no writes
- Stale lock (mtime older than SYNC_LOCK_STALE_SECONDS) → broken and sync proceeds
- Read-only filesystem (lock creation fails) → fail-safe skip, no raise
- Truncated wait budget → immediate skip without raising
- Thread-level concurrency: two syncs race, exactly one patches, files consistent
- .sync.lock never enters the integrity manifest (volatile pattern)
- Existing M1 behaviours preserved under the lock (minor bump, gate block, idempotent)
"""

import os
import stat
import threading
import time
from pathlib import Path

import pytest

from memory_core.tools.version_sync import (
    SYNC_LOCK_STALE_SECONDS,
    _sync_lock,
    sync_single_project,
)


def _make_consumer(base: Path, version: str = "0.39.0", target_files: bool = True) -> Path:
    """Create a fake consumer project with the three system files."""
    project = base / "consumer"
    sys_dir = project / "memory" / "system"
    sys_dir.mkdir(parents=True)
    if target_files:
        (sys_dir / "memory.lock").write_text(
            f'memory_version = "{version}"\n'
            'schema_version = "context-package-v1"\n'
            'locked_at = "2026-01-01T00:00:00+00:00"\n',
            encoding="utf-8",
        )
        (sys_dir / "adapter.toml").write_text(
            f'[core]\nversion = "{version}"\nadapter_name = "test"\n',
            encoding="utf-8",
        )
    (sys_dir / "ownership.toml").write_text(
        f'memory_version = "{version}"\nprotected = true\n',
        encoding="utf-8",
    )
    return project


class TestSyncLockLifecycle:
    """Lock created during sync, removed after; no residue on any path."""

    def test_lock_removed_after_successful_sync(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import memory_core.tools.version_sync as vs

        monkeypatch.setattr(vs, "_try_resign_all", lambda p, c: {"resigned": True, "paths": c})

        project = _make_consumer(tmp_path)
        lock_file = project / "memory" / "system" / ".sync.lock"

        result = sync_single_project(project, "0.40.0")

        assert result["patched"] is True
        assert not lock_file.exists(), "lock must be cleaned up after sync"

    def test_lock_removed_after_gate_block(self, tmp_path: Path) -> None:
        project = _make_consumer(tmp_path, version="1.5.0")
        lock_file = project / "memory" / "system" / ".sync.lock"

        result = sync_single_project(project, "0.40.0")

        assert result.get("gate_blocked") is True
        assert not lock_file.exists(), "gate block returns before lock; no residue"

    def test_lock_removed_after_idempotent_skip(self, tmp_path: Path) -> None:
        project = _make_consumer(tmp_path, version="0.40.0")
        lock_file = project / "memory" / "system" / ".sync.lock"

        result = sync_single_project(project, "0.40.0")

        assert result["patched"] is False
        assert "up-to-date" in result["reason"]
        assert not lock_file.exists()


class TestConcurrentHolderSkips:
    """A fresh lock held by another process → sync skips without writes."""

    def test_fresh_lock_blocks_sync(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("memory_core.tools.version_sync.SYNC_LOCK_WAIT_SECONDS", 0.0)

        project = _make_consumer(tmp_path)
        lock_file = project / "memory" / "system" / ".sync.lock"
        lock_file.write_text("99999", encoding="utf-8")  # fresh mtime = live holder

        ownership = project / "memory" / "system" / "ownership.toml"
        before = ownership.read_text(encoding="utf-8")

        result = sync_single_project(project, "0.40.0")

        assert result["patched"] is False
        assert result.get("lock_skipped") is True
        assert ownership.read_text(encoding="utf-8") == before, "no writes while lock held"
        # Lock must NOT be removed by the loser (holder still owns it)
        assert lock_file.exists()

    def test_fresh_lock_contention_via_context_manager(self, tmp_path: Path) -> None:
        project = _make_consumer(tmp_path)
        lock_file = project / "memory" / "system" / ".sync.lock"
        lock_file.write_text("1", encoding="utf-8")

        with _sync_lock(project) as acquired:
            assert acquired is False
        # Loser must not unlink the winner's lock
        assert lock_file.exists()


class TestStaleLockBroken:
    """A stale lock (older than SYNC_LOCK_STALE_SECONDS) is broken and sync proceeds."""

    def test_stale_lock_is_broken_and_sync_runs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import memory_core.tools.version_sync as vs

        monkeypatch.setattr(vs, "_try_resign_all", lambda p, c: {"resigned": True, "paths": c})

        project = _make_consumer(tmp_path)
        lock_file = project / "memory" / "system" / ".sync.lock"
        lock_file.write_text("dead-process", encoding="utf-8")
        stale = time.time() - (SYNC_LOCK_STALE_SECONDS + 5)
        os.utime(lock_file, (stale, stale))

        result = sync_single_project(project, "0.40.0")

        assert result["patched"] is True
        ownership = (project / "memory" / "system" / "ownership.toml").read_text(encoding="utf-8")
        assert 'memory_version = "0.40.0"' in ownership
        assert not lock_file.exists(), "stale lock broken then cleaned up"

    def test_stale_lock_via_context_manager(self, tmp_path: Path) -> None:
        project = _make_consumer(tmp_path)
        lock_file = project / "memory" / "system" / ".sync.lock"
        lock_file.write_text("x", encoding="utf-8")
        stale = time.time() - (SYNC_LOCK_STALE_SECONDS + 1)
        os.utime(lock_file, (stale, stale))

        with _sync_lock(project) as acquired:
            assert acquired is True
        assert not lock_file.exists()


class TestLockCreationFailureFailSafe:
    """Lock creation failure (read-only fs) → fail-safe skip, never raise."""

    def test_read_only_system_dir_skips_without_raise(self, tmp_path: Path) -> None:
        project = _make_consumer(tmp_path)
        sys_dir = project / "memory" / "system"
        ownership = sys_dir / "ownership.toml"
        before = ownership.read_text(encoding="utf-8")

        # Read-only dir: O_CREAT|O_EXCL fails with OSError (EACCES/EROFS)
        sys_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            result = sync_single_project(project, "0.40.0")

            assert isinstance(result, dict)
            assert result["patched"] is False
            assert result.get("lock_skipped") is True
            assert ownership.read_text(encoding="utf-8") == before
        finally:
            sys_dir.chmod(stat.S_IRWXU)


class TestWaitBudget:
    """Truncated wait budget skips promptly; expired-wait path covered."""

    def test_zero_wait_budget_immediate_skip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("memory_core.tools.version_sync.SYNC_LOCK_WAIT_SECONDS", 0.0)

        project = _make_consumer(tmp_path)
        (project / "memory" / "system" / ".sync.lock").write_text("1", encoding="utf-8")

        start = time.monotonic()
        with _sync_lock(project) as acquired:
            assert acquired is False
        assert time.monotonic() - start < 1.0

    def test_short_budget_times_out_then_skips(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("memory_core.tools.version_sync.SYNC_LOCK_WAIT_SECONDS", 0.15)

        project = _make_consumer(tmp_path)
        (project / "memory" / "system" / ".sync.lock").write_text("1", encoding="utf-8")

        start = time.monotonic()
        with _sync_lock(project) as acquired:
            assert acquired is False
        elapsed = time.monotonic() - start
        assert elapsed >= 0.1, "should have retried for at least the budget"
        assert elapsed < 5.0


class TestThreadLevelConcurrency:
    """Two threads race on the same project: exactly one patches, files stay consistent."""

    def test_two_threads_one_winner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import memory_core.tools.version_sync as vs

        # Track resign calls to detect double-execution of the critical section
        resign_calls: list[list[str]] = []
        lock_resign = threading.Lock()

        def fake_resign(project_path: Path, changed_paths: list[str]) -> dict[str, object]:
            with lock_resign:
                resign_calls.append(list(changed_paths))
            return {"resigned": True, "paths": changed_paths}

        monkeypatch.setattr(vs, "_try_resign_all", fake_resign)
        # Short wait budget so the loser skips fast instead of retrying long
        monkeypatch.setattr(vs, "SYNC_LOCK_WAIT_SECONDS", 0.3)

        project = _make_consumer(tmp_path, version="0.39.0")

        results: list[dict[str, object]] = []
        results_lock = threading.Lock()

        def run_sync() -> None:
            r = sync_single_project(project, "0.40.0")
            with results_lock:
                results.append(r)

        t1 = threading.Thread(target=run_sync)
        t2 = threading.Thread(target=run_sync)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert len(results) == 2
        winners = [r for r in results if r.get("patched")]
        # Exactly one winner; the loser either lost the lock race
        # (lock_skipped) or observed the winner's patch via the under-lock
        # re-read (already up-to-date). Both are safe no-write outcomes.
        assert len(winners) == 1, f"exactly one sync should patch, got {results}"
        for r in results:
            if r is winners[0]:
                continue
            assert r.get("patched") is False
            assert r.get("lock_skipped") is True or "up-to-date" in str(r.get("reason", "")), results

        # Files are consistent at target regardless of interleaving
        sys_dir = project / "memory" / "system"
        ownership = (sys_dir / "ownership.toml").read_text(encoding="utf-8")
        lock_content = (sys_dir / "memory.lock").read_text(encoding="utf-8")
        adapter = (sys_dir / "adapter.toml").read_text(encoding="utf-8")
        assert 'memory_version = "0.40.0"' in ownership
        assert 'memory_version = "0.40.0"' in lock_content
        assert 'version = "0.40.0"' in adapter

        # Lock file fully cleaned up
        assert not (sys_dir / ".sync.lock").exists()

    def test_reread_under_lock_detects_concurrent_patch(self, tmp_path: Path) -> None:
        """Simulate: gate passed pre-lock, winner patched while we waited, re-read catches it."""
        import memory_core.tools.version_sync as vs

        project = _make_consumer(tmp_path, version="0.39.0")
        sys_dir = project / "memory" / "system"

        # Pre-create the winner's lock so our sync blocks...
        lock_file = sys_dir / ".sync.lock"
        lock_file.write_text("winner", encoding="utf-8")

        # ...and patch the files to target while we are blocked (as the winner would)
        vs.patch_ownership_memory_version(sys_dir / "ownership.toml", "0.40.0")
        vs.patch_memory_lock(sys_dir / "memory.lock", "0.40.0")
        vs.patch_adapter_toml_version(sys_dir / "adapter.toml", "0.40.0")

        # Release the lock just before our sync runs: our sync acquires it,
        # then the under-lock re-read must see the winner's patch and skip.
        lock_file.unlink()

        result = sync_single_project(project, "0.40.0")
        assert result["patched"] is False
        assert "up-to-date" in result["reason"]


class TestSyncLockVolatileInManifest:
    """INFRA-545: .sync.lock must never be signed into the integrity manifest."""

    def test_sync_lock_in_volatile_patterns(self) -> None:
        from memory_core.tools.memory_hook_integrity_manifest import VOLATILE_PATTERNS, _is_volatile

        assert "memory/system/.sync.lock" in VOLATILE_PATTERNS
        assert _is_volatile("memory/system/.sync.lock") is True

    def test_full_sign_while_lock_held_excludes_lock(self, tmp_path: Path) -> None:
        from memory_core.tools.memory_hook_integrity_keys import generate_key
        from memory_core.tools.memory_hook_integrity_manifest import sign_project
        from memory_core.tools.memory_hook_integrity_verify import verify_project

        project = _make_consumer(tmp_path, version="0.40.0")
        sys_dir = project / "memory" / "system"

        # Simulate a full-sign fallback while the sync lock exists
        lock_file = sys_dir / ".sync.lock"
        lock_file.write_text("12345", encoding="utf-8")

        key = generate_key()
        manifest = sign_project(project, key)
        assert manifest is not None

        signed_rels = [e["rel_path"] for e in manifest["entries"]]
        assert "memory/system/.sync.lock" not in signed_rels

        # And after the lock is released, verify stays clean (no missing error)
        lock_file.unlink()
        result = verify_project(project, key)
        assert result.ok, f"verify must stay ok after lock release, errors: {result.errors}"

    def test_verify_with_lock_present_no_new_unsigned_warning(self, tmp_path: Path) -> None:
        from memory_core.tools.memory_hook_integrity_keys import generate_key
        from memory_core.tools.memory_hook_integrity_manifest import sign_project
        from memory_core.tools.memory_hook_integrity_verify import verify_project

        project = _make_consumer(tmp_path, version="0.40.0")
        sys_dir = project / "memory" / "system"

        key = generate_key()
        manifest = sign_project(project, key)
        assert manifest is not None

        # Lock appears (concurrent sync in progress) — verify must not warn
        (sys_dir / ".sync.lock").write_text("1", encoding="utf-8")
        result = verify_project(project, key)
        assert result.ok
        new_unsigned = [w for w in result.warnings if w.get("kind") == "new_unsigned"]
        sync_lock_warnings = [w for w in new_unsigned if ".sync.lock" in w.get("rel_path", "")]
        assert not sync_lock_warnings, f".sync.lock must not be flagged unsigned: {sync_lock_warnings}"


class TestM1BehaviourPreserved:
    """M1 gate and patch semantics unchanged under the new lock."""

    def test_minor_bump_still_patches(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import memory_core.tools.version_sync as vs

        monkeypatch.setattr(vs, "_try_resign_all", lambda p, c: {"resigned": True, "paths": c})
        project = _make_consumer(tmp_path, version="0.39.0")

        result = sync_single_project(project, "0.40.0")

        assert result["patched"] is True
        assert result["files_changed"] == [
            "memory/system/ownership.toml",
            "memory/system/memory.lock",
            "memory/system/adapter.toml",
        ]

    def test_missing_memory_system_returns_early(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty-project"
        empty.mkdir()
        result = sync_single_project(empty, "0.40.0")
        assert result["patched"] is False
        assert result["reason"] == "no ownership.toml"
