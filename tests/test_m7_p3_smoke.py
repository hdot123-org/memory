"""M7-P3 runtime convergence smoke test.

Freezes the baseline contract of build_context_package and verifies
that core workspace INDEX files exist and contain no absolute-path leaks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import hook – make memory_core/tools importable
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory_core" / "tools"))

from memory_hook_gateway import build_context_package  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestM7P3Smoke:
    """Baseline smoke tests for the M7-P3 runtime convergence milestone."""

    # -- build_context_package contract ---------------------------------------

    def test_build_context_package_status_ok(self) -> None:
        result = build_context_package("codex", "test", {})
        assert result["status"] == "ok", (
            f"Expected status='ok' but got status={result.get('status')!r}"
        )

    def test_no_missing_paths(self) -> None:
        result = build_context_package("codex", "test", {})
        assert result["missing_paths"] == [], (
            f"Unexpected missing paths: {result['missing_paths']}"
        )

    def test_no_validation_errors(self) -> None:
        result = build_context_package("codex", "test", {})
        assert result["validation_errors"] == [], (
            f"Unexpected validation errors: {result['validation_errors']}"
        )

    # -- INDEX file existence -------------------------------------------------

    def test_workspace_index_exists(self) -> None:
        assert (REPO_ROOT / "memory_core" / "INDEX.md").is_file(), (
            "memory_core/INDEX.md is missing"
        )

    def test_docs_index_exists(self) -> None:
        assert (REPO_ROOT / "memory_core" / "memory" / "docs" / "INDEX.md").is_file(), (
            "memory_core/memory/docs/INDEX.md is missing"
        )

    def test_global_index_exists(self) -> None:
        assert (REPO_ROOT / "memory_core" / "memory" / "kb" / "global" / "INDEX.md").is_file(), (
            "memory_core/memory/kb/global/INDEX.md is missing"
        )

    # -- absolute-path leak check ---------------------------------------------

    def test_no_absolute_paths_in_workspace(self) -> None:
        """Ensure no file under memory_core/ contains a hardcoded /Users/busiji path."""
        rg = subprocess.run(
            ["rg", "-c", "/Users/busiji", str(REPO_ROOT / "memory_core")],
            capture_output=True,
            text=True,
        )
        # rg -c prints "path:count" per file; total matches must be 0
        total = 0
        for line in rg.stdout.strip().splitlines():
            if line and line[-1].isdigit():
                # Format is "path:count" – take the last colon-separated token
                total += int(line.rsplit(":", 1)[-1])
        assert total == 0, (
            f"Found {total} occurrence(s) of '/Users/busiji' under memory_core/"
        )

    # -- context enrichment fields --------------------------------------------

    def test_policy_pack_loads(self) -> None:
        result = build_context_package("codex", "test", {})
        policy_pack = result.get("system_context", {}).get("policy_pack")
        assert isinstance(policy_pack, dict) and len(policy_pack) > 0, (
            f"policy_pack should be a non-empty dict, got {policy_pack!r}"
        )

    def test_project_scope_resolved(self) -> None:
        result = build_context_package("codex", "test", {})
        scope = result.get("project_scope")
        assert isinstance(scope, str) and len(scope) > 0, (
            f"project_scope should be a non-empty string, got {scope!r}"
        )

    def test_evidence_refs_present(self) -> None:
        result = build_context_package("codex", "test", {})
        refs = result.get("evidence_refs")
        assert isinstance(refs, list) and len(refs) > 0, (
            f"evidence_refs should be a non-empty list, got {refs!r}"
        )
