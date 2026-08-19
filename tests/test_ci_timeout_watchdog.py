"""Integration tests for ci-timeout-watchdog.sh reconciliation logic.

Tests the two-phase reconciliation mechanism:
- Phase A: Detect pending-ci files with created_at > 30min but no injected_at
- Phase B: Detect pending-ci files with injected_at > 45min and check PR status
"""
import json
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_locks_dir():
    """Create a temporary directory for pending-ci files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def watchdog_script():
    """Path to ci-timeout-watchdog.sh."""
    return Path(__file__).parent.parent / "webhook-scripts" / "ci-timeout-watchdog.sh"


def create_pending_ci_file(
    locks_dir: Path,
    pr_number: int,
    created_at: datetime,
    injected_at: datetime | None = None,
    session_id: str = "test-session-id",
    cwd: str = "/test/repo",
) -> Path:
    """Helper to create a pending-ci JSON file."""
    # Format timestamp as ISO 8601 with Z suffix (no timezone offset)
    def format_timestamp(dt: datetime) -> str:
        # Remove microseconds and timezone info, append Z
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    data = {
        "session_id": session_id,
        "pr_number": str(pr_number),
        "created_at": format_timestamp(created_at),
        "cwd": cwd,
    }
    if injected_at is not None:
        data["injected_at"] = format_timestamp(injected_at)
    
    file_path = locks_dir / f"pending-ci-{pr_number}.json"
    file_path.write_text(json.dumps(data))
    return file_path


class TestPhaseAReconciliation:
    """Test Phase A: Detect files with created_at > 30min but no injected_at."""
    
    def test_phase_a_detects_stale_uninjected_file(self, temp_locks_dir, watchdog_script):
        """Phase A should detect pending-ci files older than 30 minutes without injected_at."""
        # Create a file created 35 minutes ago (no injected_at)
        created_at = datetime.now(timezone.utc) - timedelta(minutes=35)
        file_path = create_pending_ci_file(temp_locks_dir, 123, created_at)
        
        # Run watchdog with LOCKS_DIR override
        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)
        
        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # File should be deleted
        assert not file_path.exists(), "Phase A should delete stale uninjected file"
        
        # Check stdout for Phase A message
        assert "Phase A" in result.stdout or "PR #123" in result.stdout
    
    def test_phase_a_ignores_recent_file(self, temp_locks_dir, watchdog_script):
        """Phase A should not delete files created less than 30 minutes ago."""
        # Create a file created 20 minutes ago (no injected_at)
        created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        file_path = create_pending_ci_file(temp_locks_dir, 124, created_at)
        
        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)
        
        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # File should still exist
        assert file_path.exists(), "Phase A should not delete recent file"
    
    def test_phase_a_ignores_file_with_injected_at(self, temp_locks_dir, watchdog_script):
        """Phase A should skip files that have injected_at (Phase B handles them)."""
        # Create a file created 35 minutes ago WITH injected_at
        created_at = datetime.now(timezone.utc) - timedelta(minutes=35)
        injected_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        file_path = create_pending_ci_file(
            temp_locks_dir, 125, created_at, injected_at=injected_at
        )
        
        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)
        
        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # File should still exist (Phase B will handle it)
        assert file_path.exists(), "Phase A should skip files with injected_at"


class TestPhaseBReconciliation:
    """Test Phase B: Detect files with injected_at > 45min and check PR status."""
    
    def test_phase_b_detects_stale_injected_file(self, temp_locks_dir, watchdog_script):
        """Phase B should detect pending-ci files with injected_at > 45min."""
        # Create a file with injected_at 50 minutes ago
        created_at = datetime.now(timezone.utc) - timedelta(minutes=55)
        injected_at = datetime.now(timezone.utc) - timedelta(minutes=50)
        file_path = create_pending_ci_file(
            temp_locks_dir, 126, created_at, injected_at=injected_at
        )
        
        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)
        
        # Run without mocking - PR #126 doesn't exist, gh pr view will fail,
        # script will output "UNKNOWN" and enter fallback branch
        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Check stdout for Phase B message or PR reference
        # (script outputs to stdout, not stderr)
        assert "Phase B" in result.stdout or "PR #126" in result.stdout or \
               "not merged" in result.stdout or "spawning fallback" in result.stdout
    
    def test_phase_b_ignores_recent_injected_file(self, temp_locks_dir, watchdog_script):
        """Phase B should not process files with injected_at < 45min."""
        # Create a file with injected_at 30 minutes ago
        created_at = datetime.now(timezone.utc) - timedelta(minutes=40)
        injected_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        file_path = create_pending_ci_file(
            temp_locks_dir, 127, created_at, injected_at=injected_at
        )
        
        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)
        
        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # File should still exist (not yet 45 minutes)
        assert file_path.exists(), "Phase B should not process recent injected files"


class TestWatchdogIdempotency:
    """Test that watchdog is idempotent and safe to run multiple times."""
    
    def test_watchdog_handles_empty_directory(self, temp_locks_dir, watchdog_script):
        """Watchdog should handle empty locks directory gracefully."""
        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)
        
        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # Should exit successfully
        assert result.returncode == 0
    
    def test_watchdog_handles_malformed_json(self, temp_locks_dir, watchdog_script):
        """Watchdog should handle malformed JSON files gracefully."""
        # Create a malformed JSON file
        malformed_file = temp_locks_dir / "pending-ci-999.json"
        malformed_file.write_text("not valid json")
        
        env = os.environ.copy()
        env["LOCKS_DIR"] = str(temp_locks_dir)
        
        result = subprocess.run(
            ["bash", str(watchdog_script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        # Should exit successfully (skip malformed file)
        assert result.returncode == 0
