"""Tests for auto-version-follow mechanism (M1).

Six branches:
1. Version match → no write (zero side effects)
2. Minor bump → allowed, three files updated
3. Major bump → blocked, no write
4. Downgrade → blocked, no write
5. Corrupt lock → no crash (fail-safe)
6. Write failure → no raise, main chain continues
"""

import stat
from pathlib import Path

from memory_core.constants import CURRENT_MEMORY_VERSION

# ---------------------------------------------------------------------------
# Helpers: build a fake consumer project in tmp_path
# ---------------------------------------------------------------------------

def _make_fake_consumer(
    base: Path,
    lock_version: str,
    ownership_version: str | None = None,
    adapter_version: str | None = None,
    corrupt_lock: bool = False,
) -> Path:
    """Create a minimal fake consumer project with memory/system files.

    Returns the project root path.
    """
    if ownership_version is None:
        ownership_version = lock_version
    if adapter_version is None:
        adapter_version = lock_version

    project = base / "fake_consumer"
    sys_dir = project / "memory" / "system"
    sys_dir.mkdir(parents=True)

    if corrupt_lock:
        (sys_dir / "memory.lock").write_text("THIS IS NOT VALID TOML {{{garbage", encoding="utf-8")
    else:
        lock_content = f"""\
memory_version = "{lock_version}"
locked_at = "2026-01-01T00:00:00+00:00"
schema_version = "context-package-v1"
"""
        (sys_dir / "memory.lock").write_text(lock_content, encoding="utf-8")

    ownership_content = f"""\
memory_version = "{ownership_version}"
protected = true
"""
    (sys_dir / "ownership.toml").write_text(ownership_content, encoding="utf-8")

    adapter_content = f"""\
[core]
version = "{adapter_version}"
adapter_name = "test"
"""
    (sys_dir / "adapter.toml").write_text(adapter_content, encoding="utf-8")

    return project


# ---------------------------------------------------------------------------
# Test 1: Version match → no write (zero side effects)
# ---------------------------------------------------------------------------

class TestVersionMatchNoWrite:
    """VAL-M1-001: When versions already match, zero side effects."""

    def test_no_write_when_version_matches(self, tmp_path: Path) -> None:
        """Syncing a project already at CURRENT_MEMORY_VERSION should not write any file."""
        from memory_core.tools.version_sync import sync_single_project

        project = _make_fake_consumer(tmp_path, CURRENT_MEMORY_VERSION)

        # Record sha256 of all three files before sync
        sys_dir = project / "memory" / "system"
        before = {}
        for fname in ("memory.lock", "ownership.toml", "adapter.toml"):
            fpath = sys_dir / fname
            before[fname] = fpath.read_bytes()

        result = sync_single_project(project, CURRENT_MEMORY_VERSION)

        # Verify no files changed
        for fname in ("memory.lock", "ownership.toml", "adapter.toml"):
            fpath = sys_dir / fname
            assert fpath.read_bytes() == before[fname], f"{fname} should be unchanged"

        assert not result.get("patched"), "patched should be False when versions match"


# ---------------------------------------------------------------------------
# Test 2: Minor bump → allowed, three files updated
# ---------------------------------------------------------------------------

class TestMinorBumpSyncsThreeFiles:
    """VAL-M1-002: Minor version bump is allowed and updates all three files."""

    def test_minor_bump_syncs_three_files(self, tmp_path: Path) -> None:
        """Syncing from 0.9.1 to CURRENT (0.40.0) should update all three files."""
        from memory_core.tools.version_sync import sync_single_project

        project = _make_fake_consumer(tmp_path, "0.9.1")

        result = sync_single_project(project, CURRENT_MEMORY_VERSION)

        sys_dir = project / "memory" / "system"
        assert result.get("patched"), "Should patch when version is behind"
        assert result.get("gate_blocked") is not True, "Minor bump should not be gate-blocked"

        # Verify all three files updated to CURRENT_MEMORY_VERSION
        lock_content = (sys_dir / "memory.lock").read_text(encoding="utf-8")
        assert f'memory_version = "{CURRENT_MEMORY_VERSION}"' in lock_content

        ownership_content = (sys_dir / "ownership.toml").read_text(encoding="utf-8")
        assert f'memory_version = "{CURRENT_MEMORY_VERSION}"' in ownership_content

        adapter_content = (sys_dir / "adapter.toml").read_text(encoding="utf-8")
        assert f'version = "{CURRENT_MEMORY_VERSION}"' in adapter_content


# ---------------------------------------------------------------------------
# Test 3: Major bump → blocked, no write
# ---------------------------------------------------------------------------

class TestMajorBumpBlocked:
    """VAL-M1-004: Major version bump is blocked by gate."""

    def test_major_bump_blocked(self, tmp_path: Path) -> None:
        """Syncing from 1.5.0 (major=1 > 0) to CURRENT should be blocked."""
        from memory_core.tools.version_sync import sync_single_project

        project = _make_fake_consumer(tmp_path, "1.5.0")

        sync_single_project(project, CURRENT_MEMORY_VERSION)

        sys_dir = project / "memory" / "system"
        # Gate should block major version change
        lock_content = (sys_dir / "memory.lock").read_text(encoding="utf-8")
        assert 'memory_version = "1.5.0"' in lock_content, "Lock should not be written on major bump"


# ---------------------------------------------------------------------------
# Test 4: Downgrade → blocked, no write
# ---------------------------------------------------------------------------

class TestDowngradeBlocked:
    """VAL-M1-003: Downgrade (target < current) is blocked by gate."""

    def test_downgrade_blocked(self, tmp_path: Path) -> None:
        """Trying to sync from 9.9.9 to CURRENT (0.40.0) should be blocked as downgrade."""
        from memory_core.tools.version_sync import _gate_version_bump, sync_single_project

        # Unit test the gate directly
        gate = _gate_version_bump("9.9.9", CURRENT_MEMORY_VERSION, False)
        assert gate.startswith("blocked"), f"Downgrade should be blocked, got {gate}"
        assert "downgrade" in gate, f"Block reason should mention downgrade, got {gate}"

        # Integration test: full sync_single_project
        project = _make_fake_consumer(tmp_path, "9.9.9")

        # Record initial state
        sys_dir = project / "memory" / "system"
        lock_before = (sys_dir / "memory.lock").read_text(encoding="utf-8")
        ownership_before = (sys_dir / "ownership.toml").read_text(encoding="utf-8")
        adapter_before = (sys_dir / "adapter.toml").read_text(encoding="utf-8")

        result = sync_single_project(project, CURRENT_MEMORY_VERSION)

        # All three files should remain unchanged
        assert (sys_dir / "memory.lock").read_text(encoding="utf-8") == lock_before
        assert (sys_dir / "ownership.toml").read_text(encoding="utf-8") == ownership_before
        assert (sys_dir / "adapter.toml").read_text(encoding="utf-8") == adapter_before

        # Result should indicate gate blocked
        assert result.get("gate_blocked") is True
        assert result.get("gate_reason") == "blocked:downgrade"
        assert not result.get("patched")


# ---------------------------------------------------------------------------
# Test 5: Corrupt lock → no crash (fail-safe)
# ---------------------------------------------------------------------------

class TestCorruptLockNoCrash:
    """VAL-M1-005: Corrupt memory.lock should not crash the sync."""

    def test_corrupt_lock_no_crash(self, tmp_path: Path) -> None:
        """A garbage memory.lock should not raise an exception."""
        from memory_core.tools.version_sync import sync_single_project

        project = _make_fake_consumer(tmp_path, "0.9.1", corrupt_lock=True)

        # Should not raise
        result = sync_single_project(project, CURRENT_MEMORY_VERSION)

        # Result should be a dict (may have errors but no crash)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 6: Write failure → no raise, main chain continues
# ---------------------------------------------------------------------------

class TestWriteFailureDoesNotRaise:
    """VAL-M1-006: Write failures should not raise, main chain continues."""

    def test_write_failure_does_not_raise(self, tmp_path: Path) -> None:
        """When file write fails (e.g., read-only), sync should not raise."""
        from memory_core.tools.version_sync import sync_single_project

        project = _make_fake_consumer(tmp_path, "0.9.1")

        # Make the memory/system directory read-only to force write failure
        sys_dir = project / "memory" / "system"
        for fname in ("memory.lock", "ownership.toml", "adapter.toml"):
            fpath = sys_dir / fname
            fpath.chmod(stat.S_IRUSR | stat.S_IRGRP)  # read-only
        sys_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+execute only

        try:
            # Should not raise even though writes will fail
            result = sync_single_project(project, CURRENT_MEMORY_VERSION)
            assert isinstance(result, dict)
        finally:
            # Restore permissions for cleanup
            sys_dir.chmod(stat.S_IRWXU)
            for fname in ("memory.lock", "ownership.toml", "adapter.toml"):
                fpath = sys_dir / fname
                if fpath.exists():
                    fpath.chmod(stat.S_IRUSR | stat.S_IWUSR)


# ---------------------------------------------------------------------------
# Test: Gate version bump downgrade logic
# ---------------------------------------------------------------------------

class TestGateVersionBumpDowngrade:
    """Unit tests for _gate_version_bump downgrade detection."""

    def test_downgrade_minor_detected(self) -> None:
        """0.40.0 → 0.39.0 is a downgrade."""
        from memory_core.tools.version_sync import _gate_version_bump
        result = _gate_version_bump("0.40.0", "0.39.0", False)
        assert result == "blocked:downgrade"

    def test_downgrade_patch_detected(self) -> None:
        """0.40.1 → 0.40.0 is a downgrade."""
        from memory_core.tools.version_sync import _gate_version_bump
        result = _gate_version_bump("0.40.1", "0.40.0", False)
        assert result == "blocked:downgrade"

    def test_upgrade_minor_allowed(self) -> None:
        """0.9.1 → 0.40.0 is a minor upgrade (allowed)."""
        from memory_core.tools.version_sync import _gate_version_bump
        result = _gate_version_bump("0.9.1", "0.40.0", False)
        assert result == "allowed"

    def test_upgrade_patch_allowed(self) -> None:
        """0.40.0 → 0.40.1 is a patch upgrade (allowed)."""
        from memory_core.tools.version_sync import _gate_version_bump
        result = _gate_version_bump("0.40.0", "0.40.1", False)
        assert result == "allowed"

    def test_same_version_allowed(self) -> None:
        """Same version should be allowed (idempotent check handles skip)."""
        from memory_core.tools.version_sync import _gate_version_bump
        result = _gate_version_bump("0.40.0", "0.40.0", False)
        assert result == "allowed"

    def test_major_upgrade_blocked(self) -> None:
        """Major version upgrade should be blocked."""
        from memory_core.tools.version_sync import _gate_version_bump
        result = _gate_version_bump("0.40.0", "1.0.0", False)
        assert result == "blocked:major"

    def test_schema_changed_blocked(self) -> None:
        """Schema change should always be blocked."""
        from memory_core.tools.version_sync import _gate_version_bump
        result = _gate_version_bump("0.40.0", "0.41.0", True)
        assert result == "blocked:schema_changed"

    def test_invalid_version_fallback_conservative(self) -> None:
        """Invalid version strings should conservatively block."""
        from memory_core.tools.version_sync import _gate_version_bump
        # With packaging available, invalid versions should still block conservatively
        result = _gate_version_bump("not_a_version", "0.40.0", False)
        assert result.startswith("blocked")


# ---------------------------------------------------------------------------
# Test: Gateway version detection (session-start probe)
# ---------------------------------------------------------------------------

class TestGatewayVersionDetection:
    """Test the gateway session-start version detection integration."""

    def test_detect_version_probe_function_exists(self) -> None:
        """The _probe_version_and_sync function should exist in version_sync."""
        from memory_core.tools.version_sync import probe_version_and_sync
        assert callable(probe_version_and_sync)

    def test_probe_skips_when_no_memory_system(self, tmp_path: Path) -> None:
        """When memory/system doesn't exist, probe should skip silently."""
        from memory_core.tools.version_sync import probe_version_and_sync

        # tmp_path has no memory/system directory
        result = probe_version_and_sync(tmp_path)
        assert result is None or result.get("skipped") is True

    def test_probe_handles_corrupt_lock(self, tmp_path: Path) -> None:
        """When memory.lock is corrupt, probe should not crash."""
        from memory_core.tools.version_sync import probe_version_and_sync

        project = _make_fake_consumer(tmp_path, "0.9.1", corrupt_lock=True)
        # Should not raise, should return None (skip) when lock is corrupt
        result = probe_version_and_sync(project)
        # Corrupt lock means we can't parse version, so probe skips (returns None)
        assert result is None
