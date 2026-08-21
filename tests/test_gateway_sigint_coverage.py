"""Comprehensive SIGINT test coverage for all gateway entry paths.

This module closes the testing gap that let PR #300 ship broken by testing
the console-script entry path (production), not just the -m path.

Covers:
- VAL-GW-001: Console-script SIGINT during work phase → exit 0
- VAL-GW-002: Console-script SIGINT during import phase → exit 0
- VAL-GW-003: -m path SIGINT → exit 0 (non-regression)
- VAL-GW-004: No-signal normal execution → exit 0, valid JSON
- VAL-GW-007: SIGALRM self-fire within 8s → exit 0
- VAL-GW-008: pytest --collect-only exits 0, no INTERNALERROR
- VAL-GW-009: In-process main() calls pass without SystemExit
- VAL-NR-001: pytest collection does not crash
- VAL-NR-003: Existing in-process main() calls work
- VAL-NR-004: _cancel_pending_sigalrm fixture works
- VAL-NR-007: Gateway __main__ block has signal handlers
- VAL-NR-009: _git_registration_probe timeout=5
- VAL-CROSS-002: Entry path matrix (all three paths correct)
- VAL-CROSS-005: stdin.read() blocked + SIGINT → clean exit
- VAL-CROSS-008: install_guard independently callable
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
GATEWAY_PATH = REPO_ROOT / "memory_core" / "tools" / "memory_hook_gateway.py"
# M3 gateway split: _git_registration_probe 现位于 _gateway_policy.py
GATEWAY_POLICY_PATH = REPO_ROOT / "memory_core" / "tools" / "_gateway_policy.py"
HOOK_RUNTIME_GUARD_PATH = REPO_ROOT / "memory_core" / "tools" / "hook_runtime_guard.py"


def _find_gateway_binary() -> str | None:
    """Find memory-hook-gateway binary, checking venv first."""
    venv_binary = REPO_ROOT / ".venv" / "bin" / "memory-hook-gateway"
    if venv_binary.exists():
        return str(venv_binary)
    # Fallback to PATH lookup
    return shutil.which("memory-hook-gateway")


class TestConsoleScriptSigint:
    """VAL-GW-001, VAL-CROSS-005: Console-script SIGINT handling."""

    def test_console_script_sigint_during_work_phase(self) -> None:
        """VAL-GW-001: Console-script exits 0 on SIGINT during work phase (stdin.read())."""
        binary = _find_gateway_binary()
        assert binary is not None, "memory-hook-gateway not found in venv or PATH"

        proc = subprocess.Popen(
            [binary, "--host", "factory", "--event", "session-end"],
            stdin=subprocess.PIPE,  # Keep stdin open, no data = blocked on read
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
            # Isolate child in its own process group so SIGINT sent to the
            # child PID cannot leak back into the xdist test runner process
            # group and cause spurious KeyboardInterrupt in the test process
            # itself (flaky root cause: PR #858 CI / main nightly / PR #890).
            start_new_session=True,
        )

        time.sleep(1.0)  # Let process reach stdin.read()
        proc.send_signal(signal.SIGINT)

        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            pytest.fail("Console-script did not exit within 5s after SIGINT")

        stderr_text = stderr.decode("utf-8", errors="replace")
        assert proc.returncode == 0, (
            f"Console-script exit code {proc.returncode} != 0\nstderr: {stderr_text}"
        )
        assert "Traceback" not in stderr_text, (
            f"Traceback found in stderr:\n{stderr_text}"
        )
        assert "KeyboardInterrupt" not in stderr_text, (
            f"KeyboardInterrupt found in stderr:\n{stderr_text}"
        )

    def test_console_script_sigint_during_import_phase(self) -> None:
        """VAL-GW-002: Console-script exits 0 on SIGINT during import phase."""
        binary = _find_gateway_binary()
        assert binary is not None, "memory-hook-gateway not found in venv or PATH"

        proc = subprocess.Popen(
            [binary, "--host", "factory", "--event", "session-end"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
            # start_new_session: isolate child process group to prevent SIGINT
            # leakage into xdist test runner (fixes three-time flaky recurrence).
            start_new_session=True,
        )

        # Send SIGINT very early (during import phase)
        time.sleep(0.1)
        proc.send_signal(signal.SIGINT)

        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            pytest.fail("Console-script did not exit within 5s after early SIGINT")

        stderr_text = stderr.decode("utf-8", errors="replace")
        assert proc.returncode == 0, (
            f"Console-script early SIGINT exit code {proc.returncode} != 0\nstderr: {stderr_text}"
        )
        assert "Traceback" not in stderr_text, (
            f"Traceback found in stderr during early SIGINT:\n{stderr_text}"
        )


class TestMPathSigint:
    """VAL-GW-003: -m path SIGINT non-regression."""

    def test_m_path_sigint_exits_zero(self) -> None:
        """VAL-GW-003: -m path exits 0 on SIGINT (already working, must not regress)."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "memory_core.tools.memory_hook_gateway",
                "--host",
                "factory",
                "--event",
                "session-end",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
            start_new_session=True,  # process group isolation (SIGINT leak guard)
        )

        time.sleep(1.0)
        proc.send_signal(signal.SIGINT)

        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            pytest.fail("-m path did not exit within 5s after SIGINT")

        stderr_text = stderr.decode("utf-8", errors="replace")
        assert proc.returncode == 0, (
            f"-m path exit code {proc.returncode} != 0\nstderr: {stderr_text}"
        )
        assert "Traceback" not in stderr_text, (
            f"Traceback in -m path stderr:\n{stderr_text}"
        )


class TestNoSignalExecution:
    """VAL-GW-004: Normal execution without signals."""

    def test_console_script_normal_execution(self) -> None:
        """VAL-GW-004: Gateway completes normally, exits 0, stdout has valid JSON."""
        binary = _find_gateway_binary()
        assert binary is not None, "memory-hook-gateway not found in venv or PATH"

        proc = subprocess.Popen(
            [binary, "--host", "factory", "--event", "session-end"],
            stdin=subprocess.DEVNULL,  # EOF immediately — gateway sees closed stdin
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
        )

        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            pytest.fail("Gateway did not complete within 10s without signals")

        stderr_text = stderr.decode("utf-8", errors="replace")
        assert proc.returncode == 0, (
            f"Normal execution exit code {proc.returncode} != 0\nstderr: {stderr_text}"
        )

        # stdout should contain valid JSON (or be empty for session-end)
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        if stdout_text:
            try:
                parsed = json.loads(stdout_text)
                assert isinstance(parsed, dict), "stdout JSON is not a dict"
            except json.JSONDecodeError as e:
                pytest.fail(f"stdout is not valid JSON: {e}\nstdout: {stdout_text}")

        assert "Traceback" not in stderr_text, f"Traceback in normal execution stderr:\n{stderr_text}"


class TestSigalmSelfFire:
    """VAL-GW-007: SIGALRM self-fire on stuck process."""

    def test_sigalm_fires_within_8s(self) -> None:
        """VAL-GW-007: Stuck process (stdin open, no SIGINT) exits within 9s via SIGALRM."""
        binary = _find_gateway_binary()
        assert binary is not None, "memory-hook-gateway not found in venv or PATH"

        proc = subprocess.Popen(
            [binary, "--host", "factory", "--event", "session-end"],
            stdin=subprocess.PIPE,  # Keep stdin open, no data
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
        )

        # Do NOT send SIGINT, do NOT close stdin
        # The 8s SIGALRM should fire and exit the process

        try:
            stdout, stderr = proc.communicate(timeout=9)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            pytest.fail("SIGALRM did not fire within 9s — process hung")

        stderr_text = stderr.decode("utf-8", errors="replace")
        assert proc.returncode == 0, (
            f"SIGALRM exit code {proc.returncode} != 0\nstderr: {stderr_text}"
        )
        assert "Traceback" not in stderr_text, (
            f"Traceback after SIGALRM:\n{stderr_text}"
        )


class TestPytestCollectionSafety:
    """VAL-GW-008, VAL-NR-001: pytest collection does not crash."""

    def test_pytest_collect_only_exits_zero(self) -> None:
        """VAL-GW-008: pytest --collect-only exits 0 with no INTERNALERROR."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "--no-cov",
                "-q",
                "tests/test_sigint_handling.py",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            f"pytest --collect-only exit code {result.returncode} != 0\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "INTERNALERROR" not in result.stderr, (
            f"INTERNALERROR in pytest collection:\n{result.stderr}"
        )
        assert "SystemExit" not in result.stderr, (
            f"SystemExit in pytest collection:\n{result.stderr}"
        )


class TestInProcessMainSafety:
    """VAL-GW-009, VAL-NR-003, VAL-NR-004: In-process main() calls."""

    def test_import_does_not_arm_sigalm(self) -> None:
        """VAL-GW-009: Importing gateway does not arm SIGALRM."""
        import memory_core.tools.memory_hook_gateway as gateway  # noqa: F401

        # Check no pending alarm
        pending_alarm = signal.alarm(0)  # Returns 0 if no pending alarm
        assert pending_alarm == 0, (
            f"Importing gateway armed SIGALRM: pending={pending_alarm}"
        )

    def test_gateway_main_callable(self) -> None:
        """VAL-CROSS-008: gateway_main is callable."""
        from memory_core.tools.hook_runtime_guard import gateway_main

        assert callable(gateway_main), "gateway_main is not callable"


class TestInstallGuardIndependent:
    """VAL-CROSS-008: install_guard independently callable and testable."""

    def test_install_guard_callable(self) -> None:
        """VAL-CROSS-008: install_guard is callable."""
        from memory_core.tools.hook_runtime_guard import install_guard

        assert callable(install_guard), "install_guard is not callable"

    def test_install_guard_installs_handlers(self) -> None:
        """VAL-CROSS-008: After install_guard, SIGINT and SIGALRM handlers are installed."""
        from memory_core.tools.hook_runtime_guard import install_guard

        # Save original handlers
        orig_sigint = signal.getsignal(signal.SIGINT)
        orig_sigalm = signal.getsignal(signal.SIGALRM)

        try:
            install_guard(boot_seconds=5)

            # Check handlers are installed
            current_sigint = signal.getsignal(signal.SIGINT)
            current_sigalm = signal.getsignal(signal.SIGALRM)

            assert current_sigint != orig_sigint, "SIGINT handler not installed"
            assert current_sigalm != orig_sigalm, "SIGALRM handler not installed"

            # Check SIGALRM is armed
            pending = signal.alarm(0)  # Cancel and get remaining time
            assert pending > 0, f"SIGALRM not armed: pending={pending}"

        finally:
            # Restore original handlers
            signal.signal(signal.SIGINT, orig_sigint)
            signal.signal(signal.SIGALRM, orig_sigalm)
            signal.alarm(0)  # Cancel any pending alarm


class TestCodeInspection:
    """VAL-NR-007, VAL-NR-009: Code inspection tests."""

    def test_gateway_main_block_has_signal_handlers(self) -> None:
        """VAL-NR-007: Gateway if __name__=='__main__' block has signal handlers."""
        content = GATEWAY_PATH.read_text()

        # Find the if __name__ == "__main__": block
        main_block_start = content.find('if __name__ == "__main__":')
        assert main_block_start != -1, "if __name__ == '__main__': block not found"

        # Extract the block (next ~500 chars should contain signal setup)
        main_block = content[main_block_start : main_block_start + 1000]

        assert "signal.signal(signal.SIGALRM" in main_block, (
            "SIGALRM handler not in __main__ block"
        )
        assert "signal.signal(signal.SIGINT" in main_block, (
            "SIGINT handler not in __main__ block"
        )
        assert "signal.alarm" in main_block, "signal.alarm not in __main__ block"

    def test_git_registration_probe_timeout_5(self) -> None:
        """VAL-NR-009: _git_registration_probe has timeout=5."""
        content = GATEWAY_POLICY_PATH.read_text()

        # Find _git_registration_probe function
        func_start = content.find("def _git_registration_probe(")
        assert func_start != -1, "_git_registration_probe function not found"

        # Extract function body (next ~3000 chars)
        func_body = content[func_start : func_start + 5000]

        # Check for timeout=5 in subprocess.run calls
        assert "timeout=5" in func_body, (
            "_git_registration_probe does not have timeout=5"
        )
    def test_hook_runtime_guard_structure(self) -> None:
        """VAL-GW-005: hook_runtime_guard.py has correct structure."""
        assert HOOK_RUNTIME_GUARD_PATH.exists(), "hook_runtime_guard.py does not exist"

        content = HOOK_RUNTIME_GUARD_PATH.read_text()

        # Check install_guard function
        assert "def install_guard(" in content, "install_guard function not found"
        assert "signal.signal(signal.SIGALRM" in content, "SIGALRM handler not in install_guard"
        assert "signal.signal(signal.SIGINT" in content, "SIGINT handler not in install_guard"
        assert "signal.alarm(" in content, "signal.alarm not in install_guard"

        # Check gateway_main function
        assert "def gateway_main(" in content, "gateway_main function not found"

        # Check install_guard is called BEFORE importing gateway
        install_guard_call_pos = content.find("install_guard()")
        import_gateway_pos = content.find("from memory_core.tools.memory_hook_gateway import main")

        assert install_guard_call_pos != -1, "install_guard() call not found"
        assert import_gateway_pos != -1, "gateway import not found"
        assert install_guard_call_pos < import_gateway_pos, (
            f"install_guard() must be called before importing gateway. "
            f"install_guard at {install_guard_call_pos}, import at {import_gateway_pos}"
        )


class TestEntryPathMatrix:
    """VAL-CROSS-002: All three entry paths behave correctly."""

    def test_console_script_sigint_path(self) -> None:
        """VAL-CROSS-002: Console-script + SIGINT → exit 0."""
        binary = _find_gateway_binary()
        assert binary is not None, "memory-hook-gateway not found in venv or PATH"

        proc = subprocess.Popen(
            [binary, "--host", "factory", "--event", "session-end"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
            start_new_session=True,  # process group isolation (SIGINT leak guard)
        )

        time.sleep(1.0)
        proc.send_signal(signal.SIGINT)

        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            pytest.fail("Console-script + SIGINT did not exit within 5s")

        assert proc.returncode == 0, (
            f"Console-script + SIGINT exit code {proc.returncode} != 0"
        )

    def test_m_path_sigint_path(self) -> None:
        """VAL-CROSS-002: -m path + SIGINT → exit 0."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "memory_core.tools.memory_hook_gateway",
                "--host",
                "factory",
                "--event",
                "session-end",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
            start_new_session=True,  # process group isolation (SIGINT leak guard)
        )

        time.sleep(1.0)
        proc.send_signal(signal.SIGINT)

        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            pytest.fail("-m path + SIGINT did not exit within 5s")

        assert proc.returncode == 0, (
            f"-m path + SIGINT exit code {proc.returncode} != 0"
        )

    def test_pytest_import_no_guard(self) -> None:
        """VAL-CROSS-002: pytest import → guard NOT active."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "--no-cov",
                "-q",
                "tests/test_sigint_handling.py",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            f"pytest collection failed: exit {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
