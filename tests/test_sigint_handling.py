"""Tests for SIGINT signal handling in SessionEnd hooks.

VAL-SIGINT-001 through VAL-SIGINT-006: Verify that session_end_logger.py and
memory_hook_gateway.py handle SIGINT gracefully (exit 0, no traceback).

CRITICAL: These tests must run with MEMORY_HOOK_FORCE UNSET.
The subprocess env overrides MEMORY_HOOK_FORCE=1 for the child processes only.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LOGGER_PATH = REPO_ROOT / "memory_core" / "tools" / "session_end_logger.py"
GATEWAY_PATH = REPO_ROOT / "memory_core" / "tools" / "memory_hook_gateway.py"


class TestSessionEndLoggerSigint:
    """VAL-SIGINT-001: session_end_logger catches SIGINT during work phase."""

    def test_sigint_exits_zero(self):
        """Send SIGINT to running session_end_logger, assert exit code 0."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "memory_core.tools.session_end_logger",
                "--session-id",
                "test-sigint-001",
                "--session-dir",
                "/tmp/nonexistent-session-dir-sigint",
                "--project-root",
                "/tmp",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
        )
        time.sleep(1)  # Wait for process to start and enter main()
        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=5)
        assert proc.returncode == 0, (
            f"Expected exit 0, got {proc.returncode}\nstderr: {stderr.decode()}"
        )

    def test_no_traceback_on_sigint(self):
        """VAL-SIGINT-004: No traceback in stderr on SIGINT."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "memory_core.tools.session_end_logger",
                "--session-id",
                "test-sigint-004",
                "--session-dir",
                "/tmp/nonexistent-session-dir-sigint",
                "--project-root",
                "/tmp",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
        )
        time.sleep(1)
        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=5)
        stderr_text = stderr.decode()
        assert "Traceback" not in stderr_text, (
            f"Traceback found in stderr:\n{stderr_text}"
        )


class TestGatewaySigint:
    """VAL-SIGINT-002: memory_hook_gateway catches SIGINT during work phase."""

    def test_sigint_exits_zero(self):
        """Send SIGINT to running gateway, assert exit code 0."""
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
        )
        # Don't close stdin yet — let the process start
        time.sleep(1)
        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=5)
        assert proc.returncode == 0, (
            f"Expected exit 0, got {proc.returncode}\nstderr: {stderr.decode()}"
        )

    def test_no_traceback_on_sigint(self):
        """VAL-SIGINT-004: No traceback in stderr on SIGINT for gateway."""
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
        )
        time.sleep(1)
        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=5)
        stderr_text = stderr.decode()
        assert "Traceback" not in stderr_text, (
            f"Traceback found in stderr:\n{stderr_text}"
        )


class TestSignalHandlerPlacement:
    """VAL-SIGINT-003 + VAL-SIGINT-005: Handler placement code inspection."""

    def test_logger_sigint_before_imports(self):
        """VAL-SIGINT-005: SIGINT handler appears before import argparse in session_end_logger.py."""
        content = LOGGER_PATH.read_text()
        sigint_line = content.index("signal.signal(signal.SIGINT")
        argparse_line = content.index("import argparse")
        assert sigint_line < argparse_line, (
            "SIGINT handler must appear before import argparse"
        )

    def test_logger_has_sigalrm_boot_timeout(self):
        """session_end_logger already has SIGALRM from PR #207 — verify it still exists."""
        content = LOGGER_PATH.read_text()
        assert "signal.signal(signal.SIGALRM" in content
        assert "signal.alarm" in content

    def test_gateway_sigint_before_imports(self):
        """VAL-SIGINT-005: SIGINT handler appears before import argparse in gateway.py."""
        content = GATEWAY_PATH.read_text()
        sigint_line = content.index("signal.signal(signal.SIGINT")
        argparse_line = content.index("import argparse")
        assert sigint_line < argparse_line, (
            "SIGINT handler must appear before import argparse"
        )

    def test_gateway_has_sigalrm_boot_timeout(self):
        """VAL-SIGINT-003: Gateway has SIGALRM boot timeout for imports."""
        content = GATEWAY_PATH.read_text()
        has_sigalrm = "signal.signal(signal.SIGALRM" in content
        assert has_sigalrm, "Gateway must have SIGALRM handler"
        assert "signal.alarm" in content, "Gateway must have signal.alarm"
        assert "_BOOT_TIMEOUT" in content, "Gateway must have _BOOT_TIMEOUT constant"
