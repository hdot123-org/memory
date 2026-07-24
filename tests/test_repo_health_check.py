"""Tests for repo_health_check.sh script."""

import subprocess
from pathlib import Path


def run_health_check(mode: str = "--ci", cwd: Path | None = None) -> tuple[int, str, str]:
    """Run health check script and return (exit_code, stdout, stderr)."""
    script_path = Path(__file__).parent.parent / "scripts" / "repo_health_check.sh"
    cmd = ["bash", str(script_path), mode]
    result = subprocess.run(
        cmd,
        cwd=cwd or Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_ci_mode_version_consistency_passes():
    """Test that --ci mode passes when version is consistent across all files."""
    exit_code, stdout, stderr = run_health_check("--ci")

    # Should pass on clean repo
    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stdout: {stdout}\nstderr: {stderr}"
    assert "version-consistency" in stdout
    assert "PASS" in stdout


def test_ci_mode_detects_version_mismatch_in_constants():
    """Test that --ci mode detects when constants.py version doesn't match pyproject.toml."""
    constants_path = Path(__file__).parent.parent / "memory_core" / "constants.py"
    original_content = constants_path.read_text()

    try:
        # Break version consistency
        broken_content = original_content.replace(
            'CURRENT_MEMORY_VERSION = "0.9.1"',
            'CURRENT_MEMORY_VERSION = "0.8.0"'
        )
        constants_path.write_text(broken_content)

        exit_code, stdout, stderr = run_health_check("--ci")

        # Should fail
        assert exit_code == 1, f"Expected exit 1, got {exit_code}. stdout: {stdout}\nstderr: {stderr}"
        assert "version-consistency" in stdout
        assert "FAIL" in stdout
    finally:
        # Restore original content
        constants_path.write_text(original_content)


def test_ci_mode_detects_version_mismatch_in_readme():
    """Test that --ci mode detects when README version doesn't match pyproject.toml."""
    readme_path = Path(__file__).parent.parent / "README.md"
    original_content = readme_path.read_text()

    try:
        # Break version consistency
        broken_content = original_content.replace(
            "- Current documented release: v0.9.1",
            "- Current documented release: v0.8.0"
        )
        readme_path.write_text(broken_content)

        exit_code, stdout, stderr = run_health_check("--ci")

        # Should fail
        assert exit_code == 1, f"Expected exit 1, got {exit_code}. stdout: {stdout}\nstderr: {stderr}"
        assert "version-consistency" in stdout
        assert "FAIL" in stdout
    finally:
        # Restore original content
        readme_path.write_text(original_content)


def test_ci_mode_detects_gitlab_residue():
    """Test that --ci mode detects GitLab residue in tracked files."""
    # Create a temporary file with GitLab residue
    test_file = Path(__file__).parent.parent / "test_gitlab_residue.txt"

    try:
        test_file.write_text("This file contains GitLab-first reference\n")
        subprocess.run(["git", "add", str(test_file)], cwd=Path(__file__).parent.parent, check=True)

        exit_code, stdout, stderr = run_health_check("--ci")

        # Should fail
        assert exit_code == 1, f"Expected exit 1, got {exit_code}. stdout: {stdout}\nstderr: {stderr}"
        assert "gitlab-residue" in stdout
        assert "FAIL" in stdout
    finally:
        # Clean up
        subprocess.run(["git", "rm", "-f", str(test_file)], cwd=Path(__file__).parent.parent, check=False)
        if test_file.exists():
            test_file.unlink()


def test_ci_mode_excludes_changelog_from_residue_check():
    """Test that CHANGELOG.md is excluded from GitLab residue check."""
    changelog_path = Path(__file__).parent.parent / "CHANGELOG.md"
    original_content = changelog_path.read_text()

    try:
        # Add GitLab residue to CHANGELOG (should be ignored)
        test_content = original_content + "\n- Fixed sync-to-github job\n"
        changelog_path.write_text(test_content)

        exit_code, stdout, stderr = run_health_check("--ci")

        # Should still pass (CHANGELOG is excluded)
        assert "gitlab-residue" in stdout
        assert "PASS" in stdout
    finally:
        # Restore original content
        changelog_path.write_text(original_content)


def test_ci_mode_excludes_python_files_from_residue_check():
    """Test that Python files are excluded from GitLab residue check."""
    # Create a temporary Python file with GitLab residue
    test_file = Path(__file__).parent.parent / "test_gitlab_residue.py"

    try:
        test_file.write_text('# This file checks for .gitlab-ci.yml\nCI_CONFIG = ".gitlab-ci.yml"\n')
        subprocess.run(["git", "add", str(test_file)], cwd=Path(__file__).parent.parent, check=True)

        exit_code, stdout, stderr = run_health_check("--ci")

        # Should still pass (Python files are excluded)
        assert "gitlab-residue" in stdout
        assert "PASS" in stdout
    finally:
        # Clean up
        subprocess.run(["git", "rm", "-f", str(test_file)], cwd=Path(__file__).parent.parent, check=False)
        if test_file.exists():
            test_file.unlink()


def test_full_mode_includes_remote_checks():
    """Test that --full mode includes remote checks (tags/releases, workflow health)."""
    exit_code, stdout, stderr = run_health_check("--full")

    # Should include remote checks
    assert "tags-releases" in stdout
    assert "release-workflow" in stdout


def test_script_requires_bash():
    """Test that script runs with bash interpreter."""
    script_path = Path(__file__).parent.parent / "scripts" / "repo_health_check.sh"
    first_line = script_path.read_text().split('\n')[0]

    assert first_line.startswith("#!/usr/bin/env bash") or first_line.startswith("#!/bin/bash")


def test_script_has_execute_permission():
    """Test that script has execute permission in git index."""
    # Check git index for executable permission (100755 mode)
    result = subprocess.run(
        ["git", "ls-files", "--stage", "scripts/repo_health_check.sh"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    # Should find the file with executable bit set (100755)
    assert result.returncode == 0
    assert "100755" in result.stdout, "Script should have execute permission (100755) in git index"


def test_ci_mode_output_format():
    """Test that --ci mode output has expected format."""
    exit_code, stdout, stderr = run_health_check("--ci")

    # Check output format
    assert "Repo Health Check" in stdout
    assert "version-consistency" in stdout
    assert "readme-install-versions" in stdout
    assert "gitlab-residue" in stdout
    assert "Summary:" in stdout


def test_full_mode_output_format():
    """Test that --full mode output has expected format."""
    exit_code, stdout, stderr = run_health_check("--full")

    # Check output format includes CI checks
    assert "version-consistency" in stdout
    assert "readme-install-versions" in stdout
    assert "gitlab-residue" in stdout

    # Check output format includes remote checks
    assert "tags-releases" in stdout
    assert "release-workflow" in stdout

    assert "Summary:" in stdout


def test_invalid_mode():
    """Test that invalid mode returns error."""
    script_path = Path(__file__).parent.parent / "scripts" / "repo_health_check.sh"
    cmd = ["bash", str(script_path), "--invalid"]
    result = subprocess.run(
        cmd,
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )

    # Should fail with error
    assert result.returncode != 0
    assert "Usage:" in result.stdout or "Usage:" in result.stderr
