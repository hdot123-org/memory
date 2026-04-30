"""Smoke tests for memory_core/tools/validate_memory_system.py.

Verifies that the validator returns the correct exit code in both
healthy and broken scenarios.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "memory_core" / "tools"
sys.path.insert(0, str(TOOLS_DIR))


def _run_validator(env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the validator as a subprocess and return the result."""
    base_env = dict(os.environ)
    base_env["PYTHONPATH"] = str(TOOLS_DIR)
    if env:
        base_env.update(env)
    return subprocess.run(
        [sys.executable, str(TOOLS_DIR / "validate_memory_system.py")],
        capture_output=True,
        text=True,
        env=base_env,
    )


class TestValidateReturnsZeroOnHealthySystem:
    """When the memory system is intact, the validator must exit 0."""

    def test_validate_returns_zero_on_healthy_system(self) -> None:
        result = _run_validator()
        assert result.returncode == 0, (
            f"Expected exit code 0 but got {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_validate_prints_summary(self) -> None:
        result = _run_validator()
        assert "Memory System Validation Report" in result.stdout, (
            f"Expected summary report in stdout.\nGot: {result.stdout}"
        )

    def test_validate_reports_all_checks_passed(self) -> None:
        result = _run_validator()
        lines = result.stdout.splitlines()
        passed_line = [l for l in lines if "checks passed" in l]
        assert len(passed_line) == 1, f"Expected exactly one summary line, got: {passed_line}"
        summary = passed_line[0]
        assert "/" in summary
        parts = summary.strip().split()
        ratio = [p for p in parts if "/" in p][0]
        numerator, denominator = ratio.split("/")
        assert numerator == denominator, (
            f"Not all checks passed: {ratio}\nFull output: {result.stdout}"
        )


class TestValidateCatchesBrokenCore:
    """When the core builder is sabotaged, the validator must exit non-zero.

    These tests exercise the validator functions in-process so that
    monkeypatching takes effect.
    """

    def test_validate_catches_missing_core(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Break _resolve_core_builder; validator must detect it."""
        from validate_memory_system import (  # type: ignore
            ValidateResult,
            check_core_builder_resolve,
            check_gateway_import,
        )

        def _broken_resolve(provider: str, *, allow_fallback: bool = True) -> tuple:
            raise RuntimeError("core builder intentionally broken for test")

        # We need to patch the gateway's _resolve_core_builder since
        # check_core_builder_resolve imports from memory_hook_gateway.
        import memory_hook_gateway  # type: ignore
        monkeypatch.setattr(memory_hook_gateway, "_resolve_core_builder", _broken_resolve)

        result = ValidateResult()
        ok = check_gateway_import(result)
        assert ok, "Gateway import should succeed"

        builder_ok, builder = check_core_builder_resolve(result)
        assert not builder_ok, "Core builder resolve should fail"
        assert builder is None

        # Validator returns non-zero when core builder fails
        assert not result.all_passed

    def test_validate_catches_bad_package(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return a structurally invalid package; validator must detect it."""
        import memory_hook_gateway  # type: ignore
        from validate_memory_system import (  # type: ignore
            ValidateResult,
            check_context_package,
            check_core_builder_resolve,
            check_gateway_import,
        )

        original_resolve = memory_hook_gateway._resolve_core_builder

        def _resolve_bad_builder(provider: str, *, allow_fallback: bool = True):
            if provider == "legacy":
                return "legacy", lambda **kwargs: {"garbage": True}, []
            return original_resolve(provider, allow_fallback=allow_fallback)

        monkeypatch.setattr(memory_hook_gateway, "_resolve_core_builder", _resolve_bad_builder)

        result = ValidateResult()
        ok = check_gateway_import(result)
        assert ok, "Gateway import should succeed"

        builder_ok, builder = check_core_builder_resolve(result)
        assert builder_ok, "Core builder should resolve"
        assert builder is not None

        pkg_ok = check_context_package(result, builder)
        assert not pkg_ok, "Context package check should fail for invalid package"
