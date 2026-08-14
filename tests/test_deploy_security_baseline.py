"""Tests for deploy-security-baseline.sh script."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "deploy-security-baseline.sh"
REPO_ROOT = Path(__file__).parent.parent


def run_script(*args: str, env: dict | None = None) -> tuple[int, str, str]:
    """Run deploy-security-baseline.sh and return (exit_code, stdout, stderr)."""
    cmd = ["bash", str(SCRIPT_PATH), *args]
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=full_env,
        cwd=REPO_ROOT,
    )
    return result.returncode, result.stdout, result.stderr


# ============================================================================
# VAL-SCRIPTS-010: deploy-security-baseline.sh exits 1 without target
# ============================================================================
def test_no_target_exits_1():
    """Running with no arguments exits 1 with usage message."""
    exit_code, stdout, stderr = run_script()
    assert exit_code == 1, f"Expected exit 1, got {exit_code}. stderr: {stderr}"
    combined = (stdout + stderr).lower()
    assert "usage" in combined, f"Expected usage message, got stdout={stdout!r}, stderr={stderr!r}"


# ============================================================================
# VAL-SCRIPTS-011: deploy-security-baseline.sh deploys to empty directory
# ============================================================================
def test_deploy_to_empty_dir(tmp_path: Path):
    """Deploying to an empty target directory copies the expected baseline files."""
    target = tmp_path / "target"
    target.mkdir()

    # Set SKIP_BRANCH_PROTECTION=1 to avoid gh calls in tests
    exit_code, stdout, stderr = run_script(
        str(target),
        env={"SKIP_BRANCH_PROTECTION": "1"},
    )
    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stdout={stdout}\nstderr={stderr}"

    # Check that the expected files were copied
    assert (target / ".github" / "workflows" / "droid-review.yml").is_file(), \
        "droid-review.yml should be copied to target"
    assert (target / ".github" / "workflows" / "auto-merge.yml").is_file(), \
        "auto-merge.yml should be copied to target"
    assert (target / "scripts" / "check_droid_review.sh").is_file(), \
        "check_droid_review.sh should be copied to target"

    # Verify check_droid_review.sh is executable
    check_script = target / "scripts" / "check_droid_review.sh"
    assert os.access(check_script, os.X_OK), \
        "check_droid_review.sh should have execute permission"


# ============================================================================
# VAL-SCRIPTS-012: deploy-security-baseline.sh skips existing without FORCE=1
# ============================================================================
def test_skip_existing_without_force(tmp_path: Path):
    """When target already has a file and FORCE is not set, the file is skipped."""
    target = tmp_path / "target"
    target.mkdir()

    # Pre-create the droid-review.yml with custom content
    workflows_dir = target / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    original_content = "# ORIGINAL CONTENT - should not be overwritten\n"
    (workflows_dir / "droid-review.yml").write_text(original_content)

    exit_code, stdout, stderr = run_script(
        str(target),
        env={"SKIP_BRANCH_PROTECTION": "1"},
    )
    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stdout={stdout}\nstderr={stderr}"

    # Verify the original content is preserved
    actual_content = (workflows_dir / "droid-review.yml").read_text()
    assert actual_content == original_content, \
        f"Original file content should be preserved when FORCE is not set. Got: {actual_content!r}"

    # Verify output mentions skipping
    assert "skipping" in stdout.lower() or "already exists" in stdout.lower(), \
        f"Expected 'skipping' message in output. stdout: {stdout}"


# ============================================================================
# Additional: FORCE=1 overwrites existing files
# ============================================================================
def test_force_overwrites(tmp_path: Path):
    """When FORCE=1 is set, existing files are overwritten."""
    target = tmp_path / "target"
    target.mkdir()

    # Pre-create the droid-review.yml with custom content
    workflows_dir = target / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    original_content = "# ORIGINAL CONTENT - should be overwritten\n"
    (workflows_dir / "droid-review.yml").write_text(original_content)

    exit_code, stdout, stderr = run_script(
        str(target),
        env={"SKIP_BRANCH_PROTECTION": "1", "FORCE": "1"},
    )
    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stdout={stdout}\nstderr={stderr}"

    # Verify the file was overwritten (content should differ from original)
    actual_content = (workflows_dir / "droid-review.yml").read_text()
    assert actual_content != original_content, \
        "File should be overwritten when FORCE=1 is set"

    # Verify output mentions deployment (not skipping)
    assert "deployed" in stdout.lower() or "[+]" in stdout, \
        f"Expected deployment message in output. stdout: {stdout}"


# ============================================================================
# VAL-SCRIPTS-013: deploy-security-baseline.sh passes shellcheck
# ============================================================================
def test_shellcheck_clean():
    """shellcheck scripts/deploy-security-baseline.sh exits 0."""
    result = subprocess.run(
        ["shellcheck", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
    )

    # Skip if shellcheck not installed
    if result.returncode != 0 and "not found" in result.stderr.lower():
        import pytest
        pytest.skip("shellcheck not installed")

    assert result.returncode == 0, \
        f"shellcheck failed:\n{result.stdout}\n{result.stderr}"
