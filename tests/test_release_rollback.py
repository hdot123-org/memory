"""Tests for release_rollback.sh script."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_script_path() -> Path:
    """Get path to release_rollback.sh script."""
    return Path(__file__).parent.parent / "scripts" / "release_rollback.sh"


def run_script(*args, cwd=None, env=None) -> tuple[int, str, str]:
    """
    Run release_rollback.sh script and return (exit_code, stdout, stderr).

    Args:
        *args: Arguments to pass to the script
        cwd: Working directory (defaults to repo root)
        env: Environment variables (defaults to current env)

    Returns:
        (exit_code, stdout, stderr) tuple
    """
    script_path = get_script_path()
    cmd = ["bash", str(script_path), *args]

    result = subprocess.run(
        cmd,
        cwd=cwd or Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def create_fixture_repo(tmp_path: Path) -> Path:
    """
    Create a git repo with a tag for testing.

    Args:
        tmp_path: Temporary directory for the fixture

    Returns:
        Path to the created repository
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Configure git user
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    (repo / "file.txt").write_text("v1 content\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create a second commit
    (repo / "file.txt").write_text("v2 content\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Update to v2"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Tag the second commit
    subprocess.run(
        ["git", "tag", "v1.0.0"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create a third commit
    (repo / "file.txt").write_text("v3 content\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Update to v3"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


# ============================================================================
# VAL-SCRIPTS-001: release_rollback.sh exits 2 with usage when no arguments
# ============================================================================
def test_no_args_exits_2():
    """When invoked with no arguments, script exits 2 with usage message in stderr."""
    exit_code, stdout, stderr = run_script()

    assert exit_code == 2, f"Expected exit 2, got {exit_code}. stderr: {stderr}"
    assert "Usage:" in stderr or "usage:" in stderr.lower(), (
        f"Expected usage message in stderr, got: {stderr}"
    )


# ============================================================================
# VAL-SCRIPTS-002: release_rollback.sh --dry-run prints plan without mutation
# ============================================================================
def test_dry_run_no_mutation(tmp_path: Path):
    """When --dry-run is used, script prints rollback plan but makes no git mutations."""
    repo = create_fixture_repo(tmp_path)

    # Capture state before dry-run
    log_before = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    tags_before = subprocess.run(
        ["git", "tag", "-l"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    # Run dry-run
    exit_code, stdout, stderr = run_script("--dry-run", "v1.0.0", cwd=repo)

    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stderr: {stderr}"
    assert "DRY RUN" in stdout, f"Expected 'DRY RUN' in output, got: {stdout}"
    assert "Would revert commit:" in stdout, (
        f"Expected 'Would revert commit:' in output, got: {stdout}"
    )
    assert "Would move tag" in stdout, f"Expected 'Would move tag' in output, got: {stdout}"
    assert "Would push" in stdout, f"Expected 'Would push' in output, got: {stdout}"

    # Verify no mutations occurred
    log_after = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    tags_after = subprocess.run(
        ["git", "tag", "-l"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert log_before == log_after, "git log changed after dry-run"
    assert tags_before == tags_after, "git tags changed after dry-run"


# ============================================================================
# VAL-SCRIPTS-003: release_rollback.sh refuses dirty working tree (with --dry-run)
# ============================================================================
def test_dry_run_dirty_tree_rejected(tmp_path: Path):
    """When --dry-run is used on a dirty working tree, script exits 1."""
    repo = create_fixture_repo(tmp_path)

    # Modify a tracked file to make the tree dirty
    (repo / "file.txt").write_text("modified content\n")

    exit_code, stdout, stderr = run_script("--dry-run", "v1.0.0", cwd=repo)

    assert exit_code == 1, f"Expected exit 1 for dirty tree, got {exit_code}. stderr: {stderr}"
    assert "uncommitted" in stderr.lower() or "changes" in stderr.lower(), (
        f"Expected error about uncommitted changes, got: {stderr}"
    )


# ============================================================================
# VAL-SCRIPTS-003: release_rollback.sh refuses dirty working tree (without --dry-run)
# ============================================================================
def test_dirty_tree_rejected(tmp_path: Path):
    """Script should reject dirty working tree without making changes."""
    repo = create_fixture_repo(tmp_path)

    # Modify a tracked file to make the tree dirty
    file_path = repo / "file.txt"
    file_path.write_text("dirty")

    exit_code, stdout, stderr = run_script("v1.0.0", cwd=repo)

    # Should exit with error (exit 1 for dirty tree)
    assert exit_code == 1, f"Expected exit 1 for dirty tree, got {exit_code}"
    assert "uncommitted" in stderr.lower() or "changes" in stderr.lower(), (
        f"Expected error about uncommitted changes, got: {stderr}"
    )


# ============================================================================
# VAL-SCRIPTS-004: release_rollback.sh rejects non-existent tag
# ============================================================================
def test_nonexistent_tag_rejected(tmp_path: Path):
    """When invoked with a non-existent tag, script exits 1 with error message."""
    repo = create_fixture_repo(tmp_path)

    exit_code, stdout, stderr = run_script("v99.99.99", cwd=repo)

    assert exit_code == 1, f"Expected exit 1 for non-existent tag, got {exit_code}. stderr: {stderr}"
    assert "not found" in stderr.lower() or "tag" in stderr.lower(), (
        f"Expected error about tag not found, got: {stderr}"
    )


# ============================================================================
# VAL-SCRIPTS-005: release_rollback.sh passes shellcheck
# ============================================================================
def test_shellcheck_clean():
    """shellcheck scripts/release_rollback.sh exits 0."""
    script_path = get_script_path()
    result = subprocess.run(
        ["shellcheck", str(script_path)],
        capture_output=True,
        text=True,
    )

    # Skip if shellcheck not installed
    if result.returncode != 0 and "not found" in result.stderr.lower():
        import pytest
        pytest.skip("shellcheck not installed")

    assert result.returncode == 0, f"shellcheck failed:\n{result.stdout}\n{result.stderr}"
