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


class _SigintRunnerMixin:
    """Shared subprocess-SIGINT runner and tests (#697, #699 dedup).

    Subclasses set SIGINT_ARGS and SIGINT_CWD. The mixin provides
    test_sigint_exits_zero and test_no_traceback_on_sigint, eliminating
    the duplicate test methods that had 86-87% AST similarity.
    Test names and assertion semantics are preserved.
    """

    SIGINT_ARGS: list = []
    SIGINT_CWD: str | None = None

    def _spawn_and_sigint(self) -> tuple:
        """Spawn SIGINT_ARGS with MEMORY_HOOK_FORCE=1, SIGINT after boot, return (returncode, stdout, stderr)."""
        proc = subprocess.Popen(
            self.SIGINT_ARGS,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd=self.SIGINT_CWD,
            start_new_session=True,
        )
        time.sleep(1)  # Wait for process to start and enter main()
        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=5)
        return proc.returncode, stdout, stderr

    def test_sigint_exits_zero(self):
        """Send SIGINT to running process, assert exit code 0."""
        returncode, _stdout, stderr = self._spawn_and_sigint()
        assert returncode == 0, (
            f"Expected exit 0, got {returncode}\nstderr: {stderr.decode()}"
        )

    def test_no_traceback_on_sigint(self):
        """No traceback in stderr on SIGINT."""
        _returncode, _stdout, stderr = self._spawn_and_sigint()
        stderr_text = stderr.decode()
        assert "Traceback" not in stderr_text, (
            f"Traceback found in stderr:\n{stderr_text}"
        )


class TestSessionEndLoggerSigint(_SigintRunnerMixin):
    """VAL-SIGINT-001: session_end_logger catches SIGINT during work phase."""

    SIGINT_ARGS = [
        sys.executable,
        "-m",
        "memory_core.tools.session_end_logger",
        "--session-id",
        "test-sigint-001",
        "--session-dir",
        "/tmp/nonexistent-session-dir-sigint",
        "--project-root",
        "/tmp",
    ]
    SIGINT_CWD = None


class TestGatewaySigint(_SigintRunnerMixin):
    """VAL-SIGINT-002: memory_hook_gateway catches SIGINT during work phase."""

    SIGINT_ARGS = [
        sys.executable,
        "-m",
        "memory_core.tools.memory_hook_gateway",
        "--host",
        "factory",
        "--event",
        "session-end",
    ]
    SIGINT_CWD = "/tmp"


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
        """VAL-SIGINT-005: SIGINT handler registered before heavyweight imports in gateway.py.

        M3 gateway split: the facade keeps the boot-time signal handlers at
        the top (before the submodule re-export imports); the heavy arg-parsing
        code now lives in _gateway_dispatch, so we compare against the first
        re-export import as the "heavyweight import" marker.
        """
        content = GATEWAY_PATH.read_text()
        sigint_line = content.index("signal.signal(signal.SIGINT")
        heavy_import_line = content.index("from ._gateway_artifacts import")
        assert sigint_line < heavy_import_line, (
            "SIGINT handler must be registered before heavyweight gateway imports"
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


class TestRemainingOsExitRegression:
    """Regression tests for the two remaining sys.exit(0) sites (PR #565).

    Bug: session_end_logger.py still had two sys.exit(0) calls outside the
    signal handlers covered by PR #563. These reach interpreter shutdown
    through the same atexit path: the telemetry import registers a PostHog
    client whose Client.join atexit handler runs in a partially-destroyed
    interpreter and emits a Traceback to stderr.
    Fix: os._exit(0) skips all atexit callbacks, avoiding the Traceback.

    Locations migrated by PR #565:
      1. _set_timeout's inner _handler (SIGALRM timeout handler)
      2. _safe_run_session_end's except SystemExit timeout-exit path

    These code inspections guard against regression back to sys.exit(0).
    """

    def test_set_timeout_handler_uses_os_exit(self):
        """Regression guard: _set_timeout's _handler uses os._exit(0) not sys.exit(0).

        The inner _handler registered for SIGALRM fires when the overall
        session-end timeout elapses. os._exit skips atexit callbacks
        (telemetry PostHog Client.join), avoiding Traceback pollution on
        stderr during the timeout-driven shutdown.
        """
        content = LOGGER_PATH.read_text()
        assert "os._exit(0)" in content, (
            "_set_timeout must use os._exit(0) to skip atexit callbacks"
        )
        func_idx = content.index("def _set_timeout")
        func_body = content[func_idx:func_idx + 300]
        assert "os._exit(0)" in func_body, (
            "_set_timeout's _handler must call os._exit(0), not sys.exit(0) — "
            "sys.exit would trigger telemetry atexit Traceback during shutdown"
        )
        assert "sys.exit(0)" not in func_body, (
            "_set_timeout's _handler must NOT use sys.exit(0) — it triggers the "
            "PostHog atexit handler in a partially-destroyed interpreter"
        )

    def test_safe_run_session_end_timeout_exit_uses_os_exit(self):
        """Regression guard: _safe_run_session_end timeout exit uses os._exit(0).

        The except SystemExit branch is reached when the SIGALRM timeout
        fires (SystemExit is raised by the timeout path). os._exit skips
        atexit callbacks registered by the telemetry PostHog client
        (Client.join), avoiding Traceback pollution on stderr during the
        timeout-driven shutdown.
        """
        content = LOGGER_PATH.read_text()
        assert "os._exit(0)" in content, (
            "_safe_run_session_end must use os._exit(0) to skip atexit callbacks"
        )
        func_idx = content.index("def _safe_run_session_end")
        # Narrow the window to the timeout-exit path (the except SystemExit branch)
        timeout_idx = content.index("except SystemExit", func_idx)
        exit_window = content[timeout_idx:timeout_idx + 450]
        assert "os._exit(0)" in exit_window, (
            "_safe_run_session_end timeout-exit must call os._exit(0), not "
            "sys.exit(0) — sys.exit would trigger telemetry atexit Traceback "
            "during shutdown"
        )
        assert "sys.exit(0)" not in exit_window, (
            "_safe_run_session_end timeout-exit must NOT use sys.exit(0) — it "
            "triggers the PostHog atexit handler in a partially-destroyed "
            "interpreter"
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
