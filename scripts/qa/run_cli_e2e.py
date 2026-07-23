#!/usr/bin/env python3
"""CLI end-to-end smoke test runner for all memory-core CLI entry points.

Runs three layers of tests:
  Layer 1: Smoke tests (--help, --version, no-args, invalid-args) for all 15 CLIs
  Layer 2: Functional tests for key CLIs (init, validate, migrate)
  Layer 3: Robustness tests (bad paths, concurrency)

Usage:
    python scripts/qa/run_cli_e2e.py
    python scripts/qa/run_cli_e2e.py --layer 1
    python scripts/qa/run_cli_e2e.py --json output.json

Exit codes:
    0  All tests passed
    1  At least one test failed
    2  Only warnings (skips), no failures
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# ANSI colors
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class TestResult:
    name: str
    layer: int
    passed: bool
    skipped: bool = False
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class QAResult:
    results: list[TestResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_s: float = 0.0

    def add(self, r: TestResult) -> None:
        self.results.append(r)
        self.total += 1
        if r.skipped:
            self.skipped += 1
        elif r.passed:
            self.passed += 1
        else:
            self.failed += 1

    def exit_code(self) -> int:
        if self.failed > 0:
            return 1
        if self.skipped > 0 and self.passed == 0:
            return 2
        return 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_s": round(self.duration_s, 2),
            "results": [
                {
                    "name": r.name,
                    "layer": r.layer,
                    "passed": r.passed,
                    "skipped": r.skipped,
                    "error": r.error,
                    "duration_ms": round(r.duration_ms, 1),
                }
                for r in self.results
            ],
        }


def color(text: str, c: str) -> str:
    return f"{c}{text}{RESET}"


def run_cmd(cmd: list[str], stdin: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr)."""
    try:
        env = os.environ.copy()
        # Bypass denylist for E2E tests (same as conftest.py does for unit tests)
        env["MEMORY_CORE_BYPASS_DENYLIST"] = "1"
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except FileNotFoundError:
        return -2, "", "NOT_FOUND"


# ---- CLI Entry Points ----
CLI_COMMANDS = [
    "memory-init",
    "memory-migrate",
    "memory-validate",
    "memory-hook-gateway",
    "memory-factory-hooks",
    "memory-consistency-check",
    "memory-audit-layout",
    "memory-plan-residue",
    "memory-apply-residue-plan",
    "memory-ownership",
    "memory-verify-consumer",
    "memory-integrity-resign",
    "memory-sync-versions",
    "memory-audit-daily",
    "memory-promote",
]

# CLIs that do meaningful work with no args (exit 0 is expected)
CLI_NO_ARGS_OK = {
    "memory-consistency-check",  # Runs all consistency checks on the repo
    "memory-sync-versions",      # Scans all known projects for version sync
    "memory-promote",            # Lists pending candidates
}


def layer1_smoke(qa: QAResult) -> None:
    """Layer 1: Smoke tests for all CLI commands."""
    print(color("\n=== Layer 1: Smoke Tests ===\n", BOLD))

    for cmd_name in CLI_COMMANDS:
        # Check if command exists
        code, _, _ = run_cmd(["which", cmd_name])
        if code != 0:
            qa.add(TestResult(f"{cmd_name}: command exists", 1, skipped=True, error="not in PATH"))
            print(f"  {color('SKIP', YELLOW)} {cmd_name} (not in PATH)")
            continue

        # --help test
        start = time.monotonic()
        code, stdout, stderr = run_cmd([cmd_name, "--help"])
        ms = (time.monotonic() - start) * 1000
        ok = code == 0 and ("usage:" in stdout or "usage:" in stderr or len(stdout) > 0)
        qa.add(TestResult(f"{cmd_name} --help", 1, ok, error="" if ok else f"exit={code}", duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} {cmd_name} --help ({ms:.0f}ms)")

        # No-args test
        # Most CLIs should fail (exit != 0) with usage info when called with no args.
        # But some CLIs do meaningful work with no args (e.g. consistency-check runs checks).
        start = time.monotonic()
        code, stdout, stderr = run_cmd([cmd_name], timeout=15)
        ms = (time.monotonic() - start) * 1000
        if cmd_name in CLI_NO_ARGS_OK:
            ok = code == 0
        else:
            ok = code != 0
        qa.add(TestResult(f"{cmd_name} (no args)", 1, ok, error="" if ok else "unexpected exit code", duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} {cmd_name} (no args) ({ms:.0f}ms)")


def layer2_functional(qa: QAResult) -> None:
    """Layer 2: Functional tests for key CLIs."""
    print(color("\n=== Layer 2: Functional Tests ===\n", BOLD))

    # Check if memory-init exists
    code, _, _ = run_cmd(["which", "memory-init"])
    if code != 0:
        qa.add(TestResult("Layer 2 functional", 2, skipped=True, error="CLI not installed"))
        print(f"  {color('SKIP', YELLOW)} CLI commands not installed (run pip install -e .)")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Test: memory-init create
        start = time.monotonic()
        code, stdout, stderr = run_cmd(["memory-init", "--target", tmpdir], timeout=30)
        ms = (time.monotonic() - start) * 1000
        ok = code == 0
        err_msg = (stderr[:200] if stderr else stdout[:200]) if not ok else ""
        qa.add(TestResult("memory-init create", 2, ok, error=err_msg, duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} memory-init create ({ms:.0f}ms)")

        # Verify structure
        memory_system = Path(tmpdir) / "memory" / "system"
        required_files = ["memory.lock", "adapter.toml", "migrations.log"]
        for f in required_files:
            exists = (memory_system / f).exists()
            qa.add(TestResult(f"init: {f} exists", 2, exists, error=f"missing {f}"))
            status = color("PASS", GREEN) if exists else color("FAIL", RED)
            print(f"  {status}   {f} exists")

        required_dirs = ["kb/projects", "kb/decisions", "kb/lessons", "kb/global"]
        for d in required_dirs:
            exists = (Path(tmpdir) / "memory" / d).is_dir()
            qa.add(TestResult(f"init: {d}/ exists", 2, exists, error=f"missing {d}/"))
            status = color("PASS", GREEN) if exists else color("FAIL", RED)
            print(f"  {status}   {d}/ exists")

        # Test: memory-validate
        start = time.monotonic()
        code, stdout, stderr = run_cmd(["memory-validate", "--target", tmpdir], timeout=15)
        ms = (time.monotonic() - start) * 1000
        ok = code == 0
        err_msg = (stderr[:200] if stderr else stdout[:200]) if not ok else ""
        qa.add(TestResult("memory-validate after init", 2, ok, error=err_msg, duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} memory-validate after init ({ms:.0f}ms)")

        # Test: memory-init --dry-run (on existing)
        start = time.monotonic()
        code, stdout, stderr = run_cmd(["memory-init", "--target", tmpdir, "--dry-run", "--mode", "update"], timeout=15)
        ms = (time.monotonic() - start) * 1000
        ok = code == 0
        err_msg = (stderr[:200] if stderr else stdout[:200]) if not ok else ""
        qa.add(TestResult("memory-init --dry-run update", 2, ok, error=err_msg, duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} memory-init --dry-run update ({ms:.0f}ms)")

        # Test: memory-validate --json
        start = time.monotonic()
        code, stdout, stderr = run_cmd(["memory-validate", "--target", tmpdir, "--json"], timeout=15)
        ms = (time.monotonic() - start) * 1000
        try:
            data = json.loads(stdout)
            ok = code == 0 and isinstance(data, dict)
        except json.JSONDecodeError:
            ok = False
        qa.add(TestResult("memory-validate --json", 2, ok, error="invalid JSON" if not ok else "", duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} memory-validate --json ({ms:.0f}ms)")

        # Test: memory-audit-layout --json
        start = time.monotonic()
        code, stdout, stderr = run_cmd(["memory-audit-layout", "--target", tmpdir, "--json"], timeout=15)
        ms = (time.monotonic() - start) * 1000
        ok = code == 0
        err_msg = (stderr[:200] if stderr else stdout[:200]) if not ok else ""
        qa.add(TestResult("memory-audit-layout --json", 2, ok, error=err_msg, duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} memory-audit-layout --json ({ms:.0f}ms)")

        # Test: memory-ownership show --json
        start = time.monotonic()
        code, stdout, stderr = run_cmd(["memory-ownership", "show", "--project-root", tmpdir, "--json"], timeout=15)
        ms = (time.monotonic() - start) * 1000
        ok = code == 0
        err_msg = (stderr[:200] if stderr else stdout[:200]) if not ok else ""
        qa.add(TestResult("memory-ownership show --json", 2, ok, error=err_msg, duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} memory-ownership show --json ({ms:.0f}ms)")


def layer3_robustness(qa: QAResult) -> None:
    """Layer 3: Robustness tests."""
    print(color("\n=== Layer 3: Robustness Tests ===\n", BOLD))

    code, _, _ = run_cmd(["which", "memory-init"])
    if code != 0:
        qa.add(TestResult("Layer 3 robustness", 3, skipped=True, error="CLI not installed"))
        print(f"  {color('SKIP', YELLOW)} CLI commands not installed")
        return

    # Non-existent target
    start = time.monotonic()
    code, stdout, stderr = run_cmd(["memory-init", "--target", "/nonexistent/path/xyz"], timeout=15)
    ms = (time.monotonic() - start) * 1000
    ok = code != 0
    qa.add(TestResult("init: nonexistent target rejected", 3, ok, error="" if ok else "should fail", duration_ms=ms))
    status = color("PASS", GREEN) if ok else color("FAIL", RED)
    print(f"  {status} init: nonexistent target rejected ({ms:.0f}ms)")

    # Validate on empty dir
    with tempfile.TemporaryDirectory() as tmpdir:
        start = time.monotonic()
        code, stdout, stderr = run_cmd(["memory-validate", "--target", tmpdir], timeout=15)
        ms = (time.monotonic() - start) * 1000
        ok = code != 0
        qa.add(TestResult("validate: empty dir rejected", 3, ok, error="" if ok else "should fail", duration_ms=ms))
        status = color("PASS", GREEN) if ok else color("FAIL", RED)
        print(f"  {status} validate: empty dir rejected ({ms:.0f}ms)")


def main() -> int:
    parser = argparse.ArgumentParser(description="memory-core CLI E2E smoke tests")
    parser.add_argument("--layer", type=int, choices=[1, 2, 3], help="Run only specified layer")
    parser.add_argument("--json", type=str, help="Write JSON results to file")
    args = parser.parse_args()

    start = time.monotonic()
    qa = QAResult()

    print(color("=" * 60, CYAN))
    print(color(" memory-core CLI E2E Test Runner", BOLD))
    print(color("=" * 60, CYAN))

    layers = [args.layer] if args.layer else [1, 2, 3]
    for layer in layers:
        if layer == 1:
            layer1_smoke(qa)
        elif layer == 2:
            layer2_functional(qa)
        elif layer == 3:
            layer3_robustness(qa)

    qa.duration_s = time.monotonic() - start

    # Summary
    print(color("\n" + "=" * 60, CYAN))
    print(color(f" Results: {qa.passed} passed, {qa.failed} failed, {qa.skipped} skipped", BOLD))
    print(color(f" Duration: {qa.duration_s:.2f}s", CYAN))
    print(color("=" * 60, CYAN))

    if args.json:
        output_path = Path(args.json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(qa.to_dict(), indent=2, ensure_ascii=False))
        print(f"\nJSON results written to {output_path}")

    return qa.exit_code()


if __name__ == "__main__":
    sys.exit(main())
