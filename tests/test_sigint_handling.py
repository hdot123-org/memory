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
GUARD_PATH = REPO_ROOT / "memory_core" / "tools" / "hook_runtime_guard.py"


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


class TestOsExitRegression:
    """Regression tests for telemetry atexit Traceback fix (PR #563).

    Bug: Signal handlers used sys.exit(0). The telemetry import creates a
    PostHog client that registers an atexit handler (Client.join). When
    sys.exit(0) fires during interpreter shutdown, the atexit handler runs
    in a partially-destroyed interpreter and emits a Traceback to stderr.
    Fix: os._exit(0) skips all atexit callbacks, avoiding the Traceback.

    These code inspections guard against regression back to sys.exit(0).
    """

    def test_sigint_handler_uses_os_exit(self):
        """Regression guard: _sigint_handler uses os._exit(0) not sys.exit(0).

        Verifies os._exit is used to skip atexit callbacks (telemetry
        PostHog Client.join) that would otherwise raise a Traceback on
        stderr during interpreter shutdown.
        """
        content = LOGGER_PATH.read_text()
        assert "os._exit(0)" in content, (
            "_sigint_handler must use os._exit(0) to skip atexit callbacks"
        )
        # The handler function definition must reference os._exit
        sigint_handler_idx = content.index("def _sigint_handler")
        handler_body = content[sigint_handler_idx:sigint_handler_idx + 200]
        assert "os._exit(0)" in handler_body, (
            "_sigint_handler body must call os._exit(0), not sys.exit(0) — "
            "sys.exit would trigger telemetry atexit Traceback during shutdown"
        )
        assert "sys.exit(0)" not in handler_body, (
            "_sigint_handler must NOT use sys.exit(0) — it triggers the "
            "PostHog atexit handler in a partially-destroyed interpreter"
        )

    def test_boot_timeout_handler_uses_os_exit(self):
        """Regression guard: _boot_timeout_handler uses os._exit(0) not sys.exit(0).

        Same rationale as _sigint_handler: os._exit skips atexit callbacks
        registered by the telemetry PostHog client (Client.join), avoiding
        Traceback pollution on stderr during SIGALRM-driven boot timeout.
        """
        content = LOGGER_PATH.read_text()
        assert "os._exit(0)" in content, (
            "_boot_timeout_handler must use os._exit(0) to skip atexit callbacks"
        )
        handler_idx = content.index("def _boot_timeout_handler")
        handler_body = content[handler_idx:handler_idx + 200]
        assert "os._exit(0)" in handler_body, (
            "_boot_timeout_handler body must call os._exit(0), not sys.exit(0) — "
            "sys.exit would trigger telemetry atexit Traceback during shutdown"
        )
        assert "sys.exit(0)" not in handler_body, (
            "_boot_timeout_handler must NOT use sys.exit(0) — it triggers the "
            "PostHog atexit handler in a partially-destroyed interpreter"
        )


class TestOsExitGatewayGuard:
    """Regression tests for telemetry atexit Traceback fix (INFRA-237).

    Bug: memory_hook_gateway.py and hook_runtime_guard.py signal handlers
    used sys.exit(0). These modules import telemetry, which creates a
    PostHog client that registers an atexit handler (Client.join). When
    sys.exit(0) fires during interpreter shutdown, the atexit handler runs
    in a partially-destroyed interpreter and emits a Traceback to stderr.
    Fix: os._exit(0) skips all atexit callbacks, avoiding the Traceback.

    These code inspections guard against regression back to sys.exit(0).
    """

    def test_gateway_sigint_handler_uses_os_exit(self):
        """Regression guard: gateway _sigint_handler uses os._exit(0) not sys.exit(0).

        Verifies os._exit is used to skip atexit callbacks (telemetry
        PostHog Client.join) that would otherwise raise a Traceback on
        stderr during interpreter shutdown.
        """
        content = GATEWAY_PATH.read_text()
        assert "os._exit(0)" in content, (
            "_sigint_handler must use os._exit(0) to skip atexit callbacks"
        )
        # The handler function definition must reference os._exit
        sigint_handler_idx = content.index("def _sigint_handler")
        handler_body = content[sigint_handler_idx:sigint_handler_idx + 200]
        assert "os._exit(0)" in handler_body, (
            "_sigint_handler body must call os._exit(0), not sys.exit(0) — "
            "sys.exit would trigger telemetry atexit Traceback during shutdown"
        )
        assert "sys.exit(0)" not in handler_body, (
            "_sigint_handler must NOT use sys.exit(0) — it triggers the "
            "PostHog atexit handler in a partially-destroyed interpreter"
        )

    def test_gateway_boot_timeout_handler_uses_os_exit(self):
        """Regression guard: gateway _boot_timeout_handler uses os._exit(0) not sys.exit(0).

        Same rationale as _sigint_handler: os._exit skips atexit callbacks
        registered by the telemetry PostHog client (Client.join), avoiding
        Traceback pollution on stderr during SIGALRM-driven boot timeout.
        """
        content = GATEWAY_PATH.read_text()
        assert "os._exit(0)" in content, (
            "_boot_timeout_handler must use os._exit(0) to skip atexit callbacks"
        )
        handler_idx = content.index("def _boot_timeout_handler")
        handler_body = content[handler_idx:handler_idx + 200]
        assert "os._exit(0)" in handler_body, (
            "_boot_timeout_handler body must call os._exit(0), not sys.exit(0) — "
            "sys.exit would trigger telemetry atexit Traceback during shutdown"
        )
        assert "sys.exit(0)" not in handler_body, (
            "_boot_timeout_handler must NOT use sys.exit(0) — it triggers the "
            "PostHog atexit handler in a partially-destroyed interpreter"
        )

    def test_guard_exit0_handler_uses_os_exit(self):
        """Regression guard: hook_runtime_guard _exit0_handler uses os._exit(0) not sys.exit(0).

        os._exit skips atexit callbacks registered by the telemetry PostHog
        client (Client.join), avoiding Traceback pollution on stderr during
        SIGINT/SIGALRM-driven shutdown of the bootstrap guard.
        """
        content = GUARD_PATH.read_text()
        assert "os._exit(0)" in content, (
            "_exit0_handler must use os._exit(0) to skip atexit callbacks"
        )
        handler_idx = content.index("def _exit0_handler")
        handler_body = content[handler_idx:handler_idx + 300]
        assert "os._exit(0)" in handler_body, (
            "_exit0_handler body must call os._exit(0), not sys.exit(0) — "
            "sys.exit would trigger telemetry atexit Traceback during shutdown"
        )
        assert "sys.exit(0)" not in handler_body, (
            "_exit0_handler must NOT use sys.exit(0) — it triggers the "
            "PostHog atexit handler in a partially-destroyed interpreter"
        )
