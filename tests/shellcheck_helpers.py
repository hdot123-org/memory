"""Shared shellcheck test helpers (INFRA-297 dedup).

INFRA-297: Function 'test_shellcheck_clean' had 99% AST similarity across 6 test
files (test_branch_cleanup, test_release_rollback, test_ci_health_check,
test_audit_telemetry_coverage, test_write_pending_ci, test_deploy_security_baseline).
All variants ran shellcheck on a script path and asserted returncode == 0.

Consolidated into a single helper; each test module calls it with its own script path.
Public test names and assertions are preserved.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def assert_shellcheck_clean(script_path: Path) -> None:
    """Assert that *script_path* passes shellcheck with zero warnings.

    INFRA-297: extracted from 6 near-identical test_shellcheck_clean bodies
    (99% AST similarity, 10 lines / 67 tokens each).
    """
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")

    result = subprocess.run(
        ["shellcheck", str(script_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"shellcheck failed:\n{result.stdout}\n{result.stderr}"
    )
