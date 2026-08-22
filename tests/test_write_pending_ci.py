"""Tests for write-pending-ci.sh script."""

from __future__ import annotations

import stat
from pathlib import Path

from tests.script_helpers import run_bash_script

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "write-pending-ci.sh"


def run_script(
    *args: str,
    env: dict | None = None,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    """Run write-pending-ci.sh and return (exit_code, stdout, stderr)."""
    return run_bash_script(SCRIPT_PATH, *args, env=env, cwd=cwd)


# ============================================================================
# VAL-SCRIPTS-016: write-pending-ci.sh passes shellcheck
# ============================================================================
def test_shellcheck_clean():
    """shellcheck scripts/write-pending-ci.sh exits 0."""
    from tests.shellcheck_helpers import assert_shellcheck_clean

    assert_shellcheck_clean(SCRIPT_PATH)


# ============================================================================
# VAL-SCRIPTS-014: write-pending-ci.sh delegates arguments
# ============================================================================
def test_delegates_arguments(tmp_path: Path):
    """The wrapper passes all arguments through to the global script.

    The script uses `exec ~/.factory/webhook/scripts/write-pending-ci.sh "$@"`.
    We mock the global script by overriding HOME to point to a tmp directory
    where we place a mock script at .factory/webhook/scripts/write-pending-ci.sh.
    The mock records the arguments it received.
    """
    # Create mock HOME directory structure
    mock_home = tmp_path / "mock_home"
    mock_script_dir = mock_home / ".factory" / "webhook" / "scripts"
    mock_script_dir.mkdir(parents=True)

    # Create a file to record arguments
    args_file = tmp_path / "received_args.txt"

    # Create mock global script that echoes args to a file
    mock_script = mock_script_dir / "write-pending-ci.sh"
    mock_script.write_text(f'#!/usr/bin/env bash\necho "$@" > "{args_file}"\nexit 0\n')
    mock_script.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

    # Run the wrapper with test arguments, overriding HOME
    exit_code, stdout, stderr = run_script(
        "42",
        "test-session-abc",
        env={"HOME": str(mock_home)},
    )

    assert exit_code == 0, f"Expected exit 0, got {exit_code}. stderr: {stderr}"

    # Verify the mock received the arguments
    assert args_file.is_file(), "Mock script should have been called and created args file"
    received = args_file.read_text().strip()
    assert received == "42 test-session-abc", f"Expected '42 test-session-abc', got {received!r}"


# ============================================================================
# VAL-SCRIPTS-015: write-pending-ci.sh handles missing global script gracefully
# ============================================================================
def test_missing_global_script_fails(tmp_path: Path):
    """When the global script doesn't exist, the wrapper exits non-zero.

    We override HOME to point to an empty tmp directory so that
    ~/.factory/webhook/scripts/write-pending-ci.sh does not exist.
    The `exec` call will fail, producing a non-zero exit code.
    """
    mock_home = tmp_path / "empty_home"
    mock_home.mkdir()

    exit_code, stdout, stderr = run_script(
        "99",
        env={"HOME": str(mock_home)},
    )

    assert exit_code != 0, f"Expected non-zero exit when global script is missing, got {exit_code}"
