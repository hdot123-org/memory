"""Tests for ci_health_check.sh script."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "ci_health_check.sh"


def run_script(cwd: Path | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run ci_health_check.sh and return (exit_code, stdout, stderr)."""
    cmd = ["bash", str(SCRIPT_PATH)]
    result = subprocess.run(
        cmd,
        cwd=cwd or Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def test_script_exists_and_executable():
    """Test that ci_health_check.sh exists and has execute permission."""
    assert SCRIPT_PATH.exists(), f"Script not found: {SCRIPT_PATH}"
    assert SCRIPT_PATH.stat().st_mode & 0o111, "Script lacks execute permission"


def test_has_set_euo_pipefail():
    """Test that script contains 'set -euo pipefail' for strict error handling."""
    content = SCRIPT_PATH.read_text()
    assert "set -euo pipefail" in content, "Script missing 'set -euo pipefail'"


def test_shellcheck_clean():
    """Test that script passes shellcheck with no warnings."""
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")

    result = subprocess.run(
        ["shellcheck", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"shellcheck failed:\n{result.stdout}\n{result.stderr}"


def test_runs_without_crash():
    """Test that script runs and produces output without crash or hang.

    Exit code may be 0 or 1 depending on environment (tools available, repo state),
    but must not crash (subprocess.TimeoutExpired) or hang.
    """
    exit_code, stdout, stderr = run_script(timeout=30)

    # Should complete (not timeout) and exit with 0 or 1
    assert exit_code in (0, 1), f"Unexpected exit code {exit_code}. stderr: {stderr}"

    # Should produce some stdout output
    assert stdout, "Script produced no stdout output"

    # Should contain expected section markers
    assert "validate_memory_system" in stdout or "CI" in stdout or "health" in stdout.lower(), \
        f"Unexpected output format. stdout: {stdout[:500]}"
