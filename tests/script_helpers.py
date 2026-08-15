"""Shared bash-script test helpers (INFRA-299, INFRA-344 dedup).

INFRA-299: Function ``run_script`` had 99% AST similarity across 2 test files
(test_ci_health_check, test_audit_telemetry_coverage). Both variants invoked
``bash <script>`` with capture_output/text and a timeout, returning
(exit_code, stdout, stderr); only the target SCRIPT_PATH differed.

INFRA-344: ``run_script`` in test_write_pending_ci and
test_deploy_security_baseline had 94% AST similarity (13 lines). Their
``*args`` passthrough + ``os.environ`` merge bodies are folded into
``run_bash_script`` as well. Each test module keeps its own ``run_script``
wrapper bound to its SCRIPT_PATH. Public helper names, tests and assertions
are preserved.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_bash_script(
    script_path: Path,
    *args: str,
    cwd: Path | None = None,
    env: dict | None = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """Run ``bash <script_path> [*args]`` and return (exit_code, stdout, stderr).

    INFRA-299: extracted from 2 near-identical run_script bodies
    (99% AST similarity, 10 lines / 84 tokens each).
    INFRA-344: extended with ``*args`` passthrough and env merging for the
    write-pending-ci / deploy-security-baseline wrappers (94% AST similarity,
    13 lines / 108 tokens vs 13 lines / 97 tokens).

    Args:
        script_path: Target script to execute with bash.
        *args: Extra arguments passed through to the script.
        cwd: Working directory; defaults to the repo root.
        env: Extra environment mappings merged over a copy of os.environ.
        timeout: Optional subprocess timeout in seconds (None = no timeout).
    """
    cmd = ["bash", str(script_path), *args]
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=full_env,
        cwd=cwd or Path(__file__).parent.parent,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr
