"""Tests for audit_telemetry_coverage.sh script."""

from pathlib import Path

from tests.script_helpers import run_bash_script

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "audit_telemetry_coverage.sh"


def run_script(cwd: Path | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run audit_telemetry_coverage.sh and return (exit_code, stdout, stderr)."""
    return run_bash_script(SCRIPT_PATH, cwd=cwd, timeout=timeout)


def test_script_exists_and_executable():
    """Test that audit_telemetry_coverage.sh exists and has execute permission."""
    assert SCRIPT_PATH.exists(), f"Script not found: {SCRIPT_PATH}"
    assert SCRIPT_PATH.stat().st_mode & 0o111, "Script lacks execute permission"


def test_has_set_euo_pipefail():
    """Test that script contains 'set -euo pipefail' for strict error handling."""
    content = SCRIPT_PATH.read_text()
    assert "set -euo pipefail" in content, "Script missing 'set -euo pipefail'"


def test_shellcheck_clean():
    """Test that script passes shellcheck with no warnings."""
    from tests.shellcheck_helpers import assert_shellcheck_clean

    assert_shellcheck_clean(SCRIPT_PATH)


def test_always_exits_zero():
    """Test that script always exits 0 (advisory-only, non-blocking).

    The script is designed to be advisory-only: it reports telemetry coverage
    but never fails the build. Exit code must always be 0 regardless of
    coverage status.
    """
    exit_code, stdout, stderr = run_script(timeout=30)

    # Advisory-only: must always exit 0
    assert exit_code == 0, f"Expected exit 0 (advisory-only), got {exit_code}. stderr: {stderr}"

    # Should produce output (coverage report)
    assert stdout, "Script produced no stdout output"

    # Should contain expected report markers
    assert "Telemetry Coverage" in stdout or "覆盖率" in stdout, \
        f"Unexpected output format. stdout: {stdout[:500]}"
