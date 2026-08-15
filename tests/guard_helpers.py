"""Shared guard subprocess test helpers (INFRA-305 dedup).

INFRA-305: method '_run_guard' had 100% AST similarity across the
TestNormalPathsUnaffected and TestExitCodes classes in
tests/test_guard_fail_closed.py (18 lines / 158 tokens each). A third copy in
TestInternalGuardFailClosed (with an extra falsy-payload branch) was never
called by any test and got removed as dead code.

Consolidated into a single module-level helper; the test module imports it
under its historical local name via aliased import, so existing call sites
stay unchanged (minus the ``self.`` prefix). Public test names and
assertions are preserved.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_guard(payload: dict[str, Any], cwd: Path | None = None) -> tuple[int, dict[str, Any]]:
    """Run the guard with given payload and return (exit_code, result).

    INFRA-305: extracted from 2 identical ``_run_guard`` method bodies
    (100% AST similarity). Serializes *payload* as JSON on stdin, points
    FACTORY_PROJECT_DIR / MEMORY_HOOK_ORIGINAL_CWD at *cwd* when given, and
    tolerates non-JSON stdout by returning raw output in a dict.
    """
    env = os.environ.copy()
    if cwd:
        env["FACTORY_PROJECT_DIR"] = str(cwd)
        env["MEMORY_HOOK_ORIGINAL_CWD"] = str(cwd)

    result = subprocess.run(
        [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
    )

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        output = {"raw_stdout": result.stdout, "stderr": result.stderr}

    return result.returncode, output
