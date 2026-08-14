"""Shared bash-script test helpers (INFRA-299 dedup).

INFRA-299: Function 'run_script' had 99% AST similarity across 2 test files
(test_ci_health_check, test_audit_telemetry_coverage). Both variants invoked
``bash <script>`` with capture_output/text and a timeout, returning
(exit_code, stdout, stderr); only the target SCRIPT_PATH differed.

Consolidated into a single helper; each test module keeps its own ``run_script``
wrapper bound to its SCRIPT_PATH. Public helper names, tests and assertions
are preserved.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_bash_script(
    script_path: Path,
    cwd: Path | None = None,
    timeout: int = 30,
) -> tuple[int, str, str]:
    """Run *script_path* with bash and return (exit_code, stdout, stderr).

    INFRA-299: extracted from 2 near-identical run_script bodies
    (99% AST similarity, 10 lines / 84 tokens each).
    """
    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=cwd or Path(__file__).parent.parent,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr
