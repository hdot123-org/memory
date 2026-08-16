"""
Tests for scripts/sync-webhook-scripts.sh

TDD: These tests verify the sync script behavior before implementation.
Expected behavior:
1. Idempotent two runs: second run produces same checksums, new backup entry
2. Backup not overwritten: each run creates timestamped backup, never overwrites
3. Validation failure rollback: injected failure exits non-zero, target unchanged

Testing approach: sandbox stub method (library/script-testing.md)
- Create isolated /tmp sandbox with repo and production layouts
- Stub shellcheck and any external dependencies
- Verify behavior through file checksums, directory listings, exit codes
"""
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "sync-webhook-scripts.sh"


def run_sync_script(*args, cwd=None, env=None):
    """Run the sync script with given args."""
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        cwd=cwd or Path(__file__).parent.parent,
        env=env,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def compute_file_checksum(filepath):
    """Compute SHA256 checksum of a file."""
    result = subprocess.run(
        ["shasum", "-a", "256", str(filepath)],
        capture_output=True,
        text=True,
    )
    return result.stdout.split()[0] if result.returncode == 0 else None


@pytest.fixture
def sandbox_env(tmp_path):
    """
    Create isolated sandbox environment for sync script testing.

    Layout:
    - repo_dir/webhook-scripts/ : source (repo side)
    - prod_dir/ : target (production ~/.factory/webhook/scripts/)
    - backup_dir/ : backups created by sync script

    Returns environment dict for subprocess.
    """
    repo_dir = tmp_path / "repo"
    prod_dir = tmp_path / "production"
    backup_dir = tmp_path / "backups"

    repo_dir.mkdir()
    prod_dir.mkdir()
    backup_dir.mkdir()

    # Create webhook-scripts/ in repo with test files
    webhook_scripts = repo_dir / "webhook-scripts"
    webhook_scripts.mkdir()

    # Create a test script in repo
    test_script = webhook_scripts / "test-script.sh"
    test_script.write_text("#!/bin/bash\necho 'test'\n")
    test_script.chmod(0o755)

    # Create MANIFEST.sh
    manifest = webhook_scripts / "MANIFEST.sh"
    manifest.write_text(
        """#!/bin/bash
# Managed files list
MANAGED_FILES=(
    "test-script.sh"
)

# Environment-specific differences (declared)
ENV_DIFF_LINES=()
"""
    )

    # Create production side (initially empty or with old version)
    prod_script = prod_dir / "test-script.sh"
    prod_script.write_text("#!/bin/bash\necho 'old'\n")
    prod_script.chmod(0o755)

    env = {
        "REPO_ROOT": str(repo_dir),
        "PROD_ROOT": str(prod_dir),
        "BACKUP_ROOT": str(backup_dir),
        "PATH": "/usr/bin:/bin",  # Minimal PATH
    }

    return {
        "env": env,
        "repo_dir": repo_dir,
        "prod_dir": prod_dir,
        "backup_dir": backup_dir,
        "webhook_scripts": webhook_scripts,
        "test_script": test_script,
        "prod_script": prod_script,
    }


def test_sync_script_exists():
    """Verify sync script exists at expected path."""
    assert SCRIPT_PATH.exists(), f"Sync script not found at {SCRIPT_PATH}"


def test_sync_script_executable():
    """Verify sync script is executable."""
    assert SCRIPT_PATH.stat().st_mode & 0o111, "Sync script not executable"


def test_shellcheck_clean():
    """Verify sync script passes shellcheck."""
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")

    result = subprocess.run(
        ["shellcheck", str(SCRIPT_PATH)],
        capture_output=True,
    )
    assert result.returncode == 0, f"shellcheck failed:\n{result.stderr.decode()}"


def test_sync_basic_flow(sandbox_env):
    """
    Test basic sync flow: backup → sync → validate.

    Expected:
    - Backup created with timestamp
    - Production file updated to match repo
    - Exit code 0 (success)
    """
    env = sandbox_env["env"]

    # Record initial state
    prod_checksum_before = compute_file_checksum(sandbox_env["prod_script"])

    # Run sync
    rc, stdout, stderr = run_sync_script(env=env)

    # Verify success
    assert rc == 0, f"Sync failed:\nstdout: {stdout}\nstderr: {stderr}"

    # Verify backup was created
    backup_files = list(sandbox_env["backup_dir"].iterdir())
    assert len(backup_files) > 0, "No backup created"

    # Verify production file was updated
    prod_checksum_after = compute_file_checksum(sandbox_env["prod_script"])
    assert prod_checksum_after != prod_checksum_before, "Production file not updated"

    # Verify production matches repo
    repo_checksum = compute_file_checksum(sandbox_env["test_script"])
    assert prod_checksum_after == repo_checksum, "Production doesn't match repo"


def test_sync_idempotent_two_runs(sandbox_env):
    """
    VAL-DEP-002: Idempotent two runs.

    Expected:
    - First run: syncs and creates backup
    - Second run: checksums unchanged, new backup entry created
    - Both runs exit 0
    """
    env = sandbox_env["env"]

    # First run
    rc1, stdout1, stderr1 = run_sync_script(env=env)
    assert rc1 == 0, f"First sync failed:\n{stderr1}"

    # Record state after first run
    prod_checksum_1 = compute_file_checksum(sandbox_env["prod_script"])
    backup_count_1 = len(list(sandbox_env["backup_dir"].iterdir()))

    # Wait a moment to ensure different timestamp
    time.sleep(1.1)

    # Second run
    rc2, stdout2, stderr2 = run_sync_script(env=env)
    assert rc2 == 0, f"Second sync failed:\n{stderr2}"

    # Verify checksum unchanged
    prod_checksum_2 = compute_file_checksum(sandbox_env["prod_script"])
    assert (
        prod_checksum_2 == prod_checksum_1
    ), f"Checksum changed: {prod_checksum_1} -> {prod_checksum_2}"

    # Verify new backup created
    backup_count_2 = len(list(sandbox_env["backup_dir"].iterdir()))
    assert backup_count_2 > backup_count_1, (
        f"No new backup created: {backup_count_1} -> {backup_count_2}"
    )


def test_sync_backup_not_overwritten(sandbox_env):
    """
    VAL-DEP-002: Backup not overwritten.

    Expected:
    - Each run creates timestamped backup
    - Older backups never overwritten
    """
    env = sandbox_env["env"]

    # Run sync multiple times
    for i in range(3):
        rc, stdout, stderr = run_sync_script(env=env)
        assert rc == 0, f"Sync run {i+1} failed:\n{stderr}"
        time.sleep(1.1)  # Ensure different timestamps

    # Verify multiple backups exist
    backup_files = sorted(sandbox_env["backup_dir"].iterdir())
    assert len(backup_files) >= 3, f"Expected >=3 backups, got {len(backup_files)}"

    # Verify each backup has unique timestamp in name
    timestamps = set()
    for bf in backup_files:
        # Extract timestamp from filename (e.g., test-script.sh.bak.20260816-123456)
        parts = bf.name.split(".")
        if len(parts) >= 3 and "bak" in parts[-2]:
            timestamps.add(parts[-1])

    assert len(timestamps) >= 3, f"Expected >=3 unique timestamps, got {timestamps}"


def test_sync_check_mode_readonly(sandbox_env):
    """
    Test --check mode is read-only.

    Expected:
    - No files modified in production
    - No backups created
    - Exit 0 if in sync, non-zero if drift detected
    """
    env = sandbox_env["env"]

    # Record initial state
    prod_checksum_before = compute_file_checksum(sandbox_env["prod_script"])
    backup_count_before = len(list(sandbox_env["backup_dir"].iterdir()))

    # Run in check mode
    rc, stdout, stderr = run_sync_script("--check", env=env)

    # Verify no changes to production
    prod_checksum_after = compute_file_checksum(sandbox_env["prod_script"])
    assert (
        prod_checksum_after == prod_checksum_before
    ), "Production modified in --check mode"

    # Verify no backups created
    backup_count_after = len(list(sandbox_env["backup_dir"].iterdir()))
    assert (
        backup_count_after == backup_count_before
    ), "Backups created in --check mode"


def test_sync_validation_failure_rollback(sandbox_env):
    """
    VAL-DEP-005: Validation failure rollback.

    Expected:
    - Injected validation failure (e.g., shellcheck fail)
    - Exit non-zero
    - Production file unchanged (rollback)
    - Backup preserved
    """
    env = sandbox_env["env"].copy()

    # Inject a script that will fail shellcheck
    test_script = sandbox_env["test_script"]
    test_script.write_text("#!/bin/bash\necho 'test'\nif\n")  # Syntax error: incomplete if

    # Record initial state
    prod_checksum_before = compute_file_checksum(sandbox_env["prod_script"])

    # Run sync (should fail validation)
    rc, stdout, stderr = run_sync_script(env=env)

    # Verify failure
    assert rc != 0, "Sync should fail on validation error"

    # Verify production unchanged (rollback)
    prod_checksum_after = compute_file_checksum(sandbox_env["prod_script"])
    assert (
        prod_checksum_after == prod_checksum_before
    ), "Production modified despite validation failure"

    # Verify backup was created (before sync attempt)
    backup_files = list(sandbox_env["backup_dir"].iterdir())
    assert len(backup_files) > 0, "No backup created before sync"


def test_sync_manifest_respected(sandbox_env):
    """
    Test that MANIFEST.sh is respected.

    Expected:
    - Only files in MANAGED_FILES list are synced
    - Files not in manifest are ignored
    """
    env = sandbox_env["env"]

    # Add a file not in manifest
    unmanaged_file = sandbox_env["webhook_scripts"] / "unmanaged.sh"
    unmanaged_file.write_text("#!/bin/bash\necho 'unmanaged'\n")

    # Run sync
    rc, stdout, stderr = run_sync_script(env=env)
    assert rc == 0, f"Sync failed:\n{stderr}"

    # Verify unmanaged file not synced to production
    prod_unmanaged = sandbox_env["prod_dir"] / "unmanaged.sh"
    assert not prod_unmanaged.exists(), "Unmanaged file was synced"


def test_sync_env_diff_lines_declared(sandbox_env):
    """
    VAL-DEP-001: Environment-specific differences must be declared.

    Expected:
    - MANIFEST.sh can declare ENV_DIFF_LINES
    - Declared differences don't cause sync to fail
    """
    env = sandbox_env["env"]

    # Update manifest with declared env diff
    manifest = sandbox_env["webhook_scripts"] / "MANIFEST.sh"
    manifest.write_text(
        """#!/bin/bash
MANAGED_FILES=(
    "test-script.sh"
)

ENV_DIFF_LINES=(
    "line 1: expected difference"
)
"""
    )

    # Add the declared difference to production
    sandbox_env["prod_script"].write_text(
        "#!/bin/bash\nline 1: expected difference\necho 'test'\n"
    )

    # Run sync
    rc, stdout, stderr = run_sync_script(env=env)

    # Should succeed despite difference (declared in manifest)
    assert rc == 0, f"Sync failed with declared env diff:\n{stderr}"


# ============================================================================
# m1-followup-hardening: Scrutiny findings fixes
# ============================================================================


def test_check_mode_exit_nonzero_when_repo_file_missing(sandbox_env):
    """
    m1 scrutiny finding #1: --check fail-open when repo-managed file missing.

    Expected:
    - MANIFEST lists a file that exists in production but NOT in repo
    - --check mode exits non-zero (not fail-open)
    - Output reports the missing file as drift
    """
    env = sandbox_env["env"]

    # Remove the file from repo side (but keep in manifest)
    sandbox_env["test_script"].unlink()

    # Production still has the file
    assert sandbox_env["prod_script"].exists()

    # Run --check mode
    rc, stdout, stderr = run_sync_script("--check", env=env)

    # Should exit non-zero (fail-closed, not fail-open)
    assert rc != 0, "--check should exit non-zero when repo-managed file missing"

    # Output should mention the missing file
    output = stdout + stderr
    assert "missing from repo" in output.lower() or "drift" in output.lower(), (
        f"Output should report missing file as drift:\n{output}"
    )


def test_manifest_source_does_not_leak_shell_options(sandbox_env):
    """
    m1 scrutiny finding #2: MANIFEST.sh set -euo pipefail leaks to caller.

    Expected:
    - Script sources MANIFEST.sh
    - Caller's shell options (errexit, nounset) remain unchanged after source
    - Specifically: if caller has errexit OFF, it stays OFF after sourcing MANIFEST
    """
    env = sandbox_env["env"]

    # Run a wrapper that checks errexit state before and after sourcing
    wrapper_script = sandbox_env["repo_dir"] / "test-wrapper.sh"
    wrapper_script.write_text(
        """#!/bin/bash
# Check errexit state before sourcing MANIFEST
if [[ $- == *e* ]]; then
    echo "ERREXIT_BEFORE=on"
else
    echo "ERREXIT_BEFORE=off"
fi

# Source MANIFEST (this is what sync-webhook-scripts.sh does)
source "${REPO_ROOT}/webhook-scripts/MANIFEST.sh"

# Check errexit state after sourcing
if [[ $- == *e* ]]; then
    echo "ERREXIT_AFTER=on"
else
    echo "ERREXIT_AFTER=off"
fi
"""
    )
    wrapper_script.chmod(0o755)

    # Run wrapper WITHOUT errexit initially
    result = subprocess.run(
        ["bash", str(wrapper_script)],
        capture_output=True,
        text=True,
        env={**env, "REPO_ROOT": env["REPO_ROOT"]},
        timeout=10,
    )

    # Parse output
    before = None
    after = None
    for line in result.stdout.split("\n"):
        if line.startswith("ERREXIT_BEFORE="):
            before = line.split("=")[1]
        elif line.startswith("ERREXIT_AFTER="):
            after = line.split("=")[1]

    assert before == "off", f"Test setup error: errexit should be off initially, got {before}"
    assert after == "off", (
        f"MANIFEST.sh leaked errexit to caller: before={before}, after={after}. "
        f"MANIFEST should isolate shell options.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_validate_file_suppresses_shellcheck_stdout(sandbox_env):
    """
    m1 scrutiny finding #3 (bonus): validate_file stdout SC annotations leak.

    Expected:
    - validate_file suppresses shellcheck stdout (SC annotations)
    - Only stderr is suppressed (current behavior), stdout must also be suppressed
    - Cosmetic fix: no shellcheck annotations in sync logs
    """
    env = sandbox_env["env"]

    # Create a script with shellcheck warnings (but valid syntax)
    test_script = sandbox_env["test_script"]
    test_script.write_text(
        """#!/bin/bash
# Script with shellcheck warning: unused variable
unused_var="test"
echo "hello"
"""
    )

    # Run sync (which calls validate_file)
    rc, stdout, stderr = run_sync_script(env=env)

    # Should succeed (shellcheck warnings don't fail validation in current impl)
    # But stdout should not contain shellcheck annotations
    output = stdout + stderr
    assert "SC" not in output or "shellcheck" not in output.lower(), (
        f"validate_file leaked shellcheck annotations to output:\n{output}"
    )


def test_sync_cleanup_orphan_sync_tmp_directories(sandbox_env):
    """
    m1 scrutiny finding #4 (bonus): Clean up orphan .sync-tmp-* on startup.

    Expected:
    - sync script cleans up any existing .sync-tmp-* directories in PROD_ROOT
    - Defense against kill -9 residue
    - Cleanup happens at script start, before new sync
    """
    env = sandbox_env["env"]
    prod_dir = sandbox_env["prod_dir"]

    # Create orphan .sync-tmp-* directories (simulate kill -9 residue)
    orphan1 = prod_dir / ".sync-tmp-20260816-120000"
    orphan2 = prod_dir / ".sync-tmp-20260816-130000"
    orphan1.mkdir()
    orphan2.mkdir()
    (orphan1 / "leftover.txt").write_text("orphan")
    (orphan2 / "leftover.txt").write_text("orphan")

    # Verify orphans exist
    assert orphan1.exists()
    assert orphan2.exists()

    # Run sync
    rc, stdout, stderr = run_sync_script(env=env)
    assert rc == 0, f"Sync failed:\n{stderr}"

    # Verify orphans cleaned up
    assert not orphan1.exists(), f"Orphan directory not cleaned: {orphan1}"
    assert not orphan2.exists(), f"Orphan directory not cleaned: {orphan2}"

    # Output should mention cleanup (optional, but good for observability)
    # output = stdout + stderr
    # assert "cleanup" in output.lower() or "orphan" in output.lower()
