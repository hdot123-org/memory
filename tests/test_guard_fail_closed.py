"""Tests for guard fail-closed behavior.

Covers VAL-GUARD-001 through VAL-GUARD-006 assertions.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_core.tools._guard_patterns import (
    PROTECTED_PATH_MARKERS,
    is_protected_path_target,
)
from tests.guard_helpers import run_guard as _run_guard


class TestProtectedPathDetection:
    """VAL-GUARD-006: Test is_protected_path_target() helper correctness."""

    @pytest.mark.parametrize("marker", PROTECTED_PATH_MARKERS)
    @pytest.mark.parametrize("field", ["file_path", "path", "command"])
    def test_detects_protected_markers_in_all_fields(self, marker: str, field: str) -> None:
        """Test that all 4 markers are detected in all 3 path fields."""
        payload = {"tool_input": {field: f"/some/path/{marker}file.txt"}}
        assert is_protected_path_target(payload) is True

    @pytest.mark.parametrize("field", ["file_path", "path", "command"])
    def test_non_protected_path_returns_false(self, field: str) -> None:
        """Test that non-protected paths return False."""
        payload = {"tool_input": {field: "/some/path/src/file.txt"}}
        assert is_protected_path_target(payload) is False

    def test_empty_tool_input_returns_false(self) -> None:
        """Test that empty tool_input returns False."""
        payload = {"tool_input": {}}
        assert is_protected_path_target(payload) is False

    def test_missing_tool_input_returns_false(self) -> None:
        """Test that missing tool_input returns False."""
        payload = {}
        assert is_protected_path_target(payload) is False

    def test_non_string_field_returns_false(self) -> None:
        """Test that non-string field values don't crash and return False."""
        payload = {"tool_input": {"file_path": 12345}}
        assert is_protected_path_target(payload) is False

    def test_none_field_returns_false(self) -> None:
        """Test that None field values don't crash and return False."""
        payload = {"tool_input": {"file_path": None}}
        assert is_protected_path_target(payload) is False

    def test_performance_under_1ms(self) -> None:
        """VAL-GUARD-012: Test that path check completes under 1ms."""
        payload = {"tool_input": {"file_path": "/some/path/memory/kb/file.txt"}}

        # Warm up
        for _ in range(100):
            is_protected_path_target(payload)

        # Measure 1000 iterations
        times = []
        for _ in range(1000):
            start = time.perf_counter()
            is_protected_path_target(payload)
            end = time.perf_counter()
            times.append((end - start) * 1000)  # Convert to ms

        # Calculate statistics
        times.sort()
        median_ms = times[len(times) // 2]
        p99_ms = times[int(len(times) * 0.99)]

        # Assert under 1ms median
        assert median_ms < 1.0, f"Median time {median_ms:.3f}ms exceeds 1ms"
        assert p99_ms < 2.0, f"P99 time {p99_ms:.3f}ms exceeds 2ms"


class TestInternalGuardFailClosed:
    """VAL-GUARD-001, 003, 005, 007: Test internal guard fail-closed behavior."""

    def test_json_parse_error_protected_path_blocks(self, tmp_path: Path) -> None:
        """VAL-GUARD-001: JSON parse error on protected path should block."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # Send invalid JSON with protected path marker
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input='{"tool_input": {"file_path": "memory/kb/file.txt"} INVALID',
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "FACTORY_PROJECT_DIR": str(tmp_path)},
        )

        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
        assert "guard failure" in output["reason"].lower()

    def test_json_parse_error_non_protected_path_allows(self, tmp_path: Path) -> None:
        """VAL-GUARD-003: JSON parse error on non-protected path should allow."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # Send invalid JSON with non-protected path
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input='{"tool_input": {"file_path": "src/file.txt"} INVALID',
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "FACTORY_PROJECT_DIR": str(tmp_path)},
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"
        assert "guard failure" in output["reason"].lower()

    def test_json_parse_error_no_path_allows(self, tmp_path: Path) -> None:
        """VAL-GUARD-005: JSON parse error with no path info should allow."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # Send invalid JSON with no path info
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input='{"tool_name": "Write"} INVALID',
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "FACTORY_PROJECT_DIR": str(tmp_path)},
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"

    def test_project_root_failure_protected_path_blocks(self, tmp_path: Path) -> None:
        """VAL-GUARD-001: Project root failure on protected path should block."""
        # _load_project_root() returns None only when cwd() fails.
        # Use monkeypatch on the guard module to force this condition.
        env = {**os.environ}
        # Remove all env vars that _load_project_root checks
        env.pop("FACTORY_PROJECT_DIR", None)
        env.pop("MEMORY_HOOK_ORIGINAL_CWD", None)

        # Run guard in a way that _load_project_root returns None
        # We simulate this by patching Path.cwd to raise
        # Since the guard runs as a subprocess, we use a Python script inline
        script = """
import sys, os, json
os.environ.pop('FACTORY_PROJECT_DIR', None)
os.environ.pop('MEMORY_HOOK_ORIGINAL_CWD', None)

# Monkeypatch Path.cwd to raise
from pathlib import Path
_original_cwd = Path.cwd
Path.cwd = classmethod(lambda cls: (_ for _ in ()).throw(OSError('mocked')))

# Now run the guard's main
from memory_core.tools.pretooluse_guard import main
sys.exit(main())
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps({"tool_input": {"file_path": "memory/docs/file.txt"}}),
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
        )

        # Should block because path is protected
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"

    def test_project_root_failure_non_protected_path_allows(self, tmp_path: Path) -> None:
        """VAL-GUARD-003: Project root failure on non-protected path should allow."""
        env = {**os.environ}
        env.pop("FACTORY_PROJECT_DIR", None)
        env.pop("MEMORY_HOOK_ORIGINAL_CWD", None)

        script = """
import sys, os, json
os.environ.pop('FACTORY_PROJECT_DIR', None)
os.environ.pop('MEMORY_HOOK_ORIGINAL_CWD', None)

from pathlib import Path
Path.cwd = classmethod(lambda cls: (_ for _ in ()).throw(OSError('mocked')))

from memory_core.tools.pretooluse_guard import main
sys.exit(main())
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps({"tool_input": {"file_path": "src/file.txt"}}),
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
        )

        # Should allow because path is not protected
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"


class TestGatewayFailClosed:
    """VAL-GUARD-002, 004: Test gateway fail-closed behavior when subprocess fails."""

    def test_gateway_timeout_protected_path_blocks(self, tmp_path: Path) -> None:
        """VAL-GUARD-002: Gateway timeout on protected path should block."""
        import argparse

        from memory_core.tools import memory_hook_gateway

        (tmp_path / "memory" / "system").mkdir(parents=True)

        args = argparse.Namespace(host="factory", event="pre-tool-use")
        raw_payload = json.dumps({"tool_input": {"file_path": "memory/log/file.txt"}})

        # Mock subprocess.run to raise TimeoutExpired
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="guard", timeout=5)):
            exit_code = memory_hook_gateway._handle_pretooluse_guard(args, raw_payload, tmp_path, time.time())

        assert exit_code == 2
        # Check stdout for block decision
        # Note: In real scenario, gateway prints to stdout. We'd need to capture it.
        # For now, we verify the return code.

    def test_gateway_crash_protected_path_blocks(self, tmp_path: Path) -> None:
        """VAL-GUARD-002: Gateway crash on protected path should block."""
        import argparse

        from memory_core.tools import memory_hook_gateway

        (tmp_path / "memory" / "system").mkdir(parents=True)

        args = argparse.Namespace(host="factory", event="pre-tool-use")
        raw_payload = json.dumps({"tool_input": {"file_path": "memory/kb/file.txt"}})

        # Mock subprocess.run to raise Exception
        with patch("subprocess.run", side_effect=Exception("Guard crashed")):
            exit_code = memory_hook_gateway._handle_pretooluse_guard(args, raw_payload, tmp_path, time.time())

        assert exit_code == 2

    def test_gateway_timeout_non_protected_path_allows(self, tmp_path: Path) -> None:
        """VAL-GUARD-004: Gateway timeout on non-protected path should allow."""
        import argparse

        from memory_core.tools import memory_hook_gateway

        (tmp_path / "memory" / "system").mkdir(parents=True)

        args = argparse.Namespace(host="factory", event="pre-tool-use")
        raw_payload = json.dumps({"tool_input": {"file_path": "src/file.txt"}})

        # Mock subprocess.run to raise TimeoutExpired
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="guard", timeout=5)):
            exit_code = memory_hook_gateway._handle_pretooluse_guard(args, raw_payload, tmp_path, time.time())

        assert exit_code == 0

    def test_gateway_crash_non_protected_path_allows(self, tmp_path: Path) -> None:
        """VAL-GUARD-004: Gateway crash on non-protected path should allow."""
        import argparse

        from memory_core.tools import memory_hook_gateway

        (tmp_path / "memory" / "system").mkdir(parents=True)

        args = argparse.Namespace(host="factory", event="pre-tool-use")
        raw_payload = json.dumps({"tool_input": {"file_path": "docs/file.txt"}})

        # Mock subprocess.run to raise Exception
        with patch("subprocess.run", side_effect=Exception("Guard crashed")):
            exit_code = memory_hook_gateway._handle_pretooluse_guard(args, raw_payload, tmp_path, time.time())

        assert exit_code == 0


class TestNormalPathsUnaffected:
    """VAL-GUARD-008, 009, 010: Test that normal paths are unaffected by fail-closed logic."""

    def test_normal_allow_path_unaffected(self, tmp_path: Path) -> None:
        """VAL-GUARD-008: Normal allow path should still work."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "src/file.txt",
            "content": "test content",
        }

        exit_code, result = _run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        # Reason should NOT indicate guard failure
        assert "guard failure" not in result.get("reason", "").lower()

    def test_normal_block_path_unaffected(self, tmp_path: Path) -> None:
        """VAL-GUARD-009: Normal block path should still work."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "memory/kb/file.txt",
            "content": "test content",
        }

        exit_code, result = _run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        # Reason should indicate ownership classification, not guard failure
        assert "guard failure" not in result.get("reason", "").lower()

    def test_non_memory_project_still_allowed(self, tmp_path: Path) -> None:
        """VAL-GUARD-010: Non-memory project should still be allowed."""
        # Don't create memory/system

        payload = {
            "tool_name": "Write",
            "file_path": "memory/kb/file.txt",
            "content": "test content",
        }

        exit_code, result = _run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "not a memory-managed project" in result.get("reason", "").lower()


class TestExitCodes:
    """VAL-GUARD-011: Test exit code semantics."""

    def test_allow_returns_exit_0(self, tmp_path: Path) -> None:
        """VAL-GUARD-011: Allow decision returns exit 0."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {"tool_name": "Write", "file_path": "src/file.txt"}
        exit_code, result = _run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_block_returns_exit_2(self, tmp_path: Path) -> None:
        """VAL-GUARD-011: Block decision returns exit 2."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {"tool_name": "Write", "file_path": "memory/kb/file.txt"}
        exit_code, result = _run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_fail_closed_block_returns_exit_2(self, tmp_path: Path) -> None:
        """VAL-GUARD-011: Fail-closed block returns exit 2."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # Send invalid JSON with protected path
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input='{"tool_input": {"file_path": "memory/kb/file.txt"} INVALID',
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "FACTORY_PROJECT_DIR": str(tmp_path)},
        )

        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert output["decision"] == "block"

    def test_fail_open_allow_returns_exit_0(self, tmp_path: Path) -> None:
        """VAL-GUARD-011: Fail-open allow returns exit 0."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # Send invalid JSON with non-protected path
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input='{"tool_input": {"file_path": "src/file.txt"} INVALID',
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env={**os.environ, "FACTORY_PROJECT_DIR": str(tmp_path)},
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "allow"
