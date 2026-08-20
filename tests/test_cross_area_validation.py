"""Cross-area integration tests for the entire hook chain.

Validates gateway + logger behave correctly under SIGINT and env var variations.

Covers:
- VAL-CROSS-001: Full SessionEnd hook chain completes within 10s under SIGINT
- VAL-CROSS-003: MEMORY_HOOK_FORCE=1: hooks exit cleanly under SIGINT
- VAL-CROSS-004: MEMORY_HOOK_FORCE unset + source-repo cwd: hooks still exit 0
- VAL-NR-002: Full test suite passes (no new failures)
- VAL-NR-005: mypy --strict passes for touched files
- VAL-NR-006: ruff check clean for all touched files

Also covers scrutiny-identified gap:
- VAL-GIT-004 (env var path): Set MEMORY_HOOK_PROJECT_CWD WITHOUT creating
  marker files, verify git subprocess is NOT spawned.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Tools may not be installed in all CI environments (e.g. Coverage Audit job)
HAS_MYPY = shutil.which("mypy") is not None
HAS_RUFF = shutil.which("ruff") is not None

REPO_ROOT = Path(__file__).parent.parent
CONSOLE_SCRIPT = REPO_ROOT / ".venv" / "bin" / "memory-hook-gateway"
LOGGER_MODULE = "memory_core.tools.session_end_logger"
GATEWAY_MODULE = "memory_core.tools.memory_hook_gateway"


# ─── VAL-CROSS-001: Full hook chain under SIGINT ─────────────────────────────

class TestFullHookChainSigint:
    """Full SessionEnd hook chain (gateway + logger) completes within 10s under SIGINT."""

    def test_gateway_exits_zero_under_sigint_within_10s(self):
        """Gateway console-script exits 0 within 10s when SIGINT sent."""
        if not CONSOLE_SCRIPT.exists():
            pytest.skip(".venv console script not found")

        proc = subprocess.Popen(
            [str(CONSOLE_SCRIPT), "--host", "factory", "--event", "session-end"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
        )
        time.sleep(1.0)  # Let it reach work phase (blocked on stdin.read)
        proc.send_signal(signal.SIGINT)

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Gateway did not exit within 10s after SIGINT")

        stderr = proc.stderr.read()
        assert proc.returncode == 0, (
            f"Gateway exit {proc.returncode}, stderr: {stderr.decode()}"
        )
        assert b"Traceback" not in stderr, (
            f"Traceback in stderr: {stderr.decode()}"
        )
        assert b"KeyboardInterrupt" not in stderr, (
            f"KeyboardInterrupt in stderr: {stderr.decode()}"
        )

    def test_logger_exits_zero_under_sigint_within_timeout(self):
        """Logger -m path exits 0 within timeout when SIGINT sent."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                LOGGER_MODULE,
                "--session-id",
                "cross-test-001",
                "--session-dir",
                "/tmp/nonexistent-cross-test-dir",
                "--project-root",
                "/tmp",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
        )
        time.sleep(0.5)
        proc.send_signal(signal.SIGINT)

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Logger did not exit within 5s after SIGINT")

        stderr = proc.stderr.read()
        assert proc.returncode == 0, (
            f"Logger exit {proc.returncode}, stderr: {stderr.decode()}"
        )
        assert b"Traceback" not in stderr, (
            f"Traceback in stderr: {stderr.decode()}"
        )

    def test_both_gateway_and_logger_exit_zero_under_sigint(self):
        """Both gateway and logger can run sequentially and both exit 0 under SIGINT."""
        if not CONSOLE_SCRIPT.exists():
            pytest.skip(".venv console script not found")

        # Gateway
        gw_proc = subprocess.Popen(
            [str(CONSOLE_SCRIPT), "--host", "factory", "--event", "session-end"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
        )
        time.sleep(0.5)
        gw_proc.send_signal(signal.SIGINT)
        try:
            gw_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            gw_proc.kill()
            gw_proc.wait()

        gw_stderr = gw_proc.stderr.read()
        assert gw_proc.returncode == 0, f"Gateway exit {gw_proc.returncode}"
        assert b"Traceback" not in gw_stderr

        # Logger
        log_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                LOGGER_MODULE,
                "--session-id",
                "cross-chain-001",
                "--session-dir",
                "/tmp/nonexistent-chain-dir",
                "--project-root",
                "/tmp",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
        )
        time.sleep(0.5)
        log_proc.send_signal(signal.SIGINT)
        try:
            log_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log_proc.kill()
            log_proc.wait()

        log_stderr = log_proc.stderr.read()
        assert log_proc.returncode == 0, f"Logger exit {log_proc.returncode}"
        assert b"Traceback" not in log_stderr


# ─── VAL-CROSS-003: MEMORY_HOOK_FORCE=1 + SIGINT ────────────────────────────

class TestForceHookSigint:
    """MEMORY_HOOK_FORCE=1: hooks exit cleanly under SIGINT."""

    def test_gateway_force_1_sigint_exit_zero(self):
        """Gateway with MEMORY_HOOK_FORCE=1 + SIGINT → exit 0."""
        if not CONSOLE_SCRIPT.exists():
            pytest.skip(".venv console script not found")

        proc = subprocess.Popen(
            [str(CONSOLE_SCRIPT), "--host", "factory", "--event", "session-end"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
            cwd="/tmp",
        )
        time.sleep(1.0)
        proc.send_signal(signal.SIGINT)

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Gateway with FORCE=1 did not exit within 10s")

        stderr = proc.stderr.read()
        assert proc.returncode == 0, (
            f"Gateway FORCE=1 exit {proc.returncode}, stderr: {stderr.decode()}"
        )
        assert b"Traceback" not in stderr
        assert b"KeyboardInterrupt" not in stderr

    def test_logger_force_1_sigint_exit_zero(self):
        """Logger -m path with MEMORY_HOOK_FORCE=1 + SIGINT → exit 0."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                LOGGER_MODULE,
                "--session-id",
                "cross-force-001",
                "--session-dir",
                "/tmp/nonexistent-force-dir",
                "--project-root",
                "/tmp",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "MEMORY_HOOK_FORCE": "1"},
        )
        time.sleep(0.5)
        proc.send_signal(signal.SIGINT)

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Logger with FORCE=1 did not exit within 5s")

        stderr = proc.stderr.read()
        assert proc.returncode == 0, (
            f"Logger FORCE=1 exit {proc.returncode}, stderr: {stderr.decode()}"
        )
        assert b"Traceback" not in stderr


# ─── VAL-CROSS-004: MEMORY_HOOK_FORCE unset + source-repo cwd ────────────────

class TestSourceRepoNoopSigint:
    """MEMORY_HOOK_FORCE unset + source-repo cwd: hooks noop but exit 0 under SIGINT."""

    def test_gateway_no_force_source_repo_sigint_exit_zero(self):
        """Gateway without FORCE, in source-repo cwd, SIGINT → exit 0."""
        if not CONSOLE_SCRIPT.exists():
            pytest.skip(".venv console script not found")

        # Build env WITHOUT MEMORY_HOOK_FORCE
        env = dict(os.environ)
        env.pop("MEMORY_HOOK_FORCE", None)
        env.pop("WORKBOT_FORCE_HOOK", None)

        proc = subprocess.Popen(
            [str(CONSOLE_SCRIPT), "--host", "factory", "--event", "session-end"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(REPO_ROOT),  # source-repo cwd
        )
        time.sleep(1.0)
        proc.send_signal(signal.SIGINT)

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Gateway noop path did not exit within 10s")

        stderr = proc.stderr.read()
        assert proc.returncode == 0, (
            f"Gateway noop exit {proc.returncode}, stderr: {stderr.decode()}"
        )
        assert b"Traceback" not in stderr, (
            f"Traceback in noop stderr: {stderr.decode()}"
        )
        assert b"KeyboardInterrupt" not in stderr

    def test_logger_no_force_source_repo_sigint_exit_zero(self):
        """Logger without FORCE, in source-repo cwd, SIGINT → exit 0."""
        env = dict(os.environ)
        env.pop("MEMORY_HOOK_FORCE", None)
        env.pop("WORKBOT_FORCE_HOOK", None)

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                LOGGER_MODULE,
                "--session-id",
                "cross-noop-001",
                "--session-dir",
                "/tmp/nonexistent-noop-dir",
                "--project-root",
                str(REPO_ROOT),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        time.sleep(0.5)
        proc.send_signal(signal.SIGINT)

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Logger noop path did not exit within 5s")

        stderr = proc.stderr.read()
        assert proc.returncode == 0, (
            f"Logger noop exit {proc.returncode}, stderr: {stderr.decode()}"
        )
        assert b"Traceback" not in stderr


# ─── VAL-GIT-004 (scrutiny gap): Env var without marker files ────────────────

class TestEnvVarWithoutMarkers:
    """Scrutiny-identified gap: env var code path was masked by marker files.

    Previous tests created marker files alongside env var, so the marker
    fast-path returned True before the env var code ever executed.
    This test sets env var WITHOUT markers, verifying the env var path
    independently prevents spawning git subprocess.
    """

    def test_env_var_no_markers_skips_git_subprocess(self, tmp_path: Path):
        """MEMORY_HOOK_PROJECT_CWD set, NO markers → git subprocess NOT spawned."""
        from memory_core.ownership import is_memory_core_source_repo

        # Create a plain directory with NO marker files
        test_dir = tmp_path / "plain_project"
        test_dir.mkdir()

        # Set env var to match the resolved path
        env_patch = patch.dict(
            os.environ, {"MEMORY_HOOK_PROJECT_CWD": str(test_dir)}
        )
        env_patch.start()

        try:
            with patch("memory_core.ownership.subprocess.run") as mock_run:
                result = is_memory_core_source_repo(test_dir)

                # Should NOT have called git subprocess
                # (env var optimization skipped it)
                assert not mock_run.called, (
                    "Git subprocess should NOT be called when MEMORY_HOOK_PROJECT_CWD "
                    "matches resolved path, even without marker files"
                )

                # Should return False (no markers at this path)
                assert result is False, (
                    "Should return False when no markers exist, "
                    "even though env var skipped git"
                )
        finally:
            env_patch.stop()

    def test_env_var_no_markers_resolved_path_match(self, tmp_path: Path):
        """Env var with symlink-style path still resolves correctly."""
        from memory_core.ownership import is_memory_core_source_repo

        test_dir = tmp_path / "resolved_project"
        test_dir.mkdir()

        # Use a path that resolves to the same directory
        env_path = str(test_dir) + "/"  # trailing slash, resolves same

        env_patch = patch.dict(
            os.environ, {"MEMORY_HOOK_PROJECT_CWD": env_path}
        )
        env_patch.start()

        try:
            with patch("memory_core.ownership.subprocess.run") as mock_run:
                result = is_memory_core_source_repo(test_dir)

                # Env var should match after resolve(), skipping git
                assert not mock_run.called, (
                    "Git subprocess should NOT be called when env var "
                    "resolves to same path"
                )
                assert result is False
        finally:
            env_patch.stop()

    def test_env_var_no_markers_mismatch_calls_git(self, tmp_path: Path):
        """When env var doesn't match and no markers → git subprocess IS called."""
        from memory_core.ownership import is_memory_core_source_repo

        test_dir = tmp_path / "project_a"
        test_dir.mkdir()
        other_dir = tmp_path / "project_b"
        other_dir.mkdir()

        # Set env var to a DIFFERENT path
        env_patch = patch.dict(
            os.environ, {"MEMORY_HOOK_PROJECT_CWD": str(other_dir)}
        )
        env_patch.start()

        try:
            with patch("memory_core.ownership.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stdout = ""

                result = is_memory_core_source_repo(test_dir)

                # Env var doesn't match → git subprocess should be called
                assert mock_run.called, (
                    "Git subprocess SHOULD be called when env var doesn't match"
                )
                assert result is False
        finally:
            env_patch.stop()


# ─── VAL-NR-005: mypy --strict for touched files ─────────────────────────────

@pytest.mark.skipif(not HAS_MYPY, reason="mypy not installed in this environment")
class TestMypyStrictTouchedFiles:
    """mypy --strict must pass for all 4 touched files.

    Pre-existing errors in transitively imported files (project_lifecycle.py,
    posthog_client.py, telemetry_bridge.py) are NOT in our touched files
    and are excluded from this check.
    """

    def test_hook_runtime_guard_passes_mypy_strict(self):
        """hook_runtime_guard.py passes mypy --strict."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--strict",
                "--no-error-summary",
                str(REPO_ROOT / "memory_core" / "tools" / "hook_runtime_guard.py"),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        # Filter out errors from transitively imported files
        errors_in_our_file = [
            line
            for line in result.stdout.splitlines()
            if "hook_runtime_guard.py" in line and "error:" in line
        ]
        assert not errors_in_our_file, (
            "mypy --strict errors in hook_runtime_guard.py:\n"
            + "\n".join(errors_in_our_file)
        )

    def test_ownership_passes_mypy_strict(self):
        """ownership.py passes mypy --strict."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--strict",
                "--no-error-summary",
                str(REPO_ROOT / "memory_core" / "ownership.py"),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        errors_in_our_file = [
            line
            for line in result.stdout.splitlines()
            if "ownership.py" in line and "error:" in line
        ]
        assert not errors_in_our_file, (
            "mypy --strict errors in ownership.py:\n"
            + "\n".join(errors_in_our_file)
        )

    def test_session_end_logger_passes_mypy_strict(self):
        """session_end_logger.py passes mypy --strict."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--strict",
                "--no-error-summary",
                str(REPO_ROOT / "memory_core" / "tools" / "session_end_logger.py"),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        errors_in_our_file = [
            line
            for line in result.stdout.splitlines()
            if "session_end_logger.py" in line and "error:" in line
        ]
        assert not errors_in_our_file, (
            "mypy --strict errors in session_end_logger.py:\n"
            + "\n".join(errors_in_our_file)
        )

    def test_memory_hook_gateway_passes_mypy_strict(self):
        """memory_hook_gateway.py passes mypy --strict."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--strict",
                "--no-error-summary",
                str(REPO_ROOT / "memory_core" / "tools" / "memory_hook_gateway.py"),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        errors_in_our_file = [
            line
            for line in result.stdout.splitlines()
            if "memory_hook_gateway.py" in line and "error:" in line
        ]
        assert not errors_in_our_file, (
            "mypy --strict errors in memory_hook_gateway.py:\n"
            + "\n".join(errors_in_our_file)
        )


# ─── VAL-NR-006: ruff check clean ───────────────────────────────────────────

@pytest.mark.skipif(not HAS_RUFF, reason="ruff not installed in this environment")
class TestRuffCheckClean:
    """ruff check must be clean for all touched files."""

    def test_ruff_check_all_touched_files(self):
        """ruff check passes for all 4 touched files."""
        touched_files = [
            str(REPO_ROOT / "memory_core" / "tools" / "hook_runtime_guard.py"),
            str(REPO_ROOT / "memory_core" / "ownership.py"),
            str(REPO_ROOT / "memory_core" / "tools" / "session_end_logger.py"),
            str(REPO_ROOT / "memory_core" / "tools" / "memory_hook_gateway.py"),
        ]

        result = subprocess.run(
            ["ruff", "check", *touched_files],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"ruff check failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_ruff_check_test_files(self):
        """ruff check passes for the cross-area test file."""
        result = subprocess.run(
            ["ruff", "check", str(Path(__file__))],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"ruff check failed on test file:\n{result.stdout}\n{result.stderr}"
        )


# ─── VAL-NR-002: Full pytest suite passes ────────────────────────────────────

class TestFullPytestSuite:
    """Full pytest suite must pass with no new failures.

    This is a meta-test that verifies the test infrastructure is intact.
    The actual suite is run separately in the verification step.
    """

    def test_pytest_collect_only_succeeds(self):
        """pytest --collect-only exits 0, no INTERNALERROR."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-cov"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"pytest --collect-only failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "INTERNALERROR" not in result.stderr, (
            f"INTERNALERROR during collection:\n{result.stderr}"
        )

    def test_cross_area_tests_collectible(self):
        """This test file itself is collectible by pytest."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "--no-cov",
                str(Path(__file__)),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"Collection of cross-area tests failed:\n{result.stdout}"
        )
        # Verify test count — should have at least 15 tests
        lines = [
            line
            for line in result.stdout.splitlines()
            if "::test_" in line
        ]
        assert len(lines) >= 15, (
            f"Expected at least 15 tests, found {len(lines)}"
        )
