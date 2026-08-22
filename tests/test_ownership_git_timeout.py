"""Tests for ownership.py git subprocess timeout and graceful degradation.

Covers:
- VAL-GIT-001: Git subprocess has timeout parameter
- VAL-GIT-002: Git timeout causes graceful degradation, not crash
- VAL-GIT-003: Git binary not found → graceful degradation
- VAL-GIT-004: MEMORY_HOOK_PROJECT_CWD env var reuse avoids spawning git
- VAL-GIT-005: git_detector injection still works (testability)
- VAL-GIT-006: Marker-based detection works without git (fast path)
- VAL-CROSS-010: Ownership git timeout does not slow normal (fast) path
"""

import inspect
import os
import re
import subprocess
import time
from unittest.mock import MagicMock, patch

from memory_core import ownership
from memory_core.ownership import is_memory_core_source_repo


class TestGitTimeout:
    """Tests for git subprocess timeout parameter."""

    def test_subprocess_run_has_timeout_parameter(self, tmp_path):
        """VAL-GIT-001: subprocess.run call must include timeout parameter."""
        # Create a non-marker directory to force git subprocess path
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            # Mock git to return a non-source-repo path
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""

            is_memory_core_source_repo(test_dir)

            # Verify subprocess.run was called with timeout parameter
            assert mock_run.called, "subprocess.run should have been called"
            call_kwargs = mock_run.call_args[1]
            assert "timeout" in call_kwargs, "timeout parameter must be present"
            assert call_kwargs["timeout"] > 0, "timeout must be positive"
            assert call_kwargs["timeout"] == 2, "timeout should be 2 seconds"


class TestGitTimeoutExpired:
    """Tests for git subprocess TimeoutExpired handling."""

    def test_timeout_expired_returns_false_gracefully(self, tmp_path):
        """VAL-GIT-002: TimeoutExpired must be caught and return False."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            # Mock git to raise TimeoutExpired
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=2)

            result = is_memory_core_source_repo(test_dir)

            # Should return False gracefully, not crash
            assert result is False, "Should return False on timeout"

    def test_timeout_expired_with_markers_returns_true(self, tmp_path):
        """VAL-GIT-002: If markers exist even on timeout, return True."""
        # Create marker structure
        tools_dir = tmp_path / "memory_core" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "memory_hook_gateway.py").write_text("# marker")

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            # Even if git times out, markers should still be detected
            # (though markers are checked BEFORE git, so git shouldn't even be called)
            result = is_memory_core_source_repo(tmp_path)
            assert result is True, "Should return True when markers exist"
            # Git shouldn't even be called when markers exist
            assert not mock_run.called, "Git subprocess should not be called when markers exist"


class TestGitFileNotFoundError:
    """Tests for git binary not found handling."""

    def test_file_not_found_returns_false_gracefully(self, tmp_path):
        """VAL-GIT-003: FileNotFoundError must be caught and return False."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            # Mock git to raise FileNotFoundError (git not on PATH)
            mock_run.side_effect = FileNotFoundError("git not found")

            result = is_memory_core_source_repo(test_dir)

            # Should return False gracefully, not crash
            assert result is False, "Should return False when git not found"


class TestMemoryHookProjectCwdEnvVar:
    """Tests for MEMORY_HOOK_PROJECT_CWD environment variable reuse."""

    def test_env_var_set_and_matches_skips_git(self, tmp_path):
        """VAL-GIT-004: When env var matches resolved path, skip git subprocess."""
        # Create marker structure
        tools_dir = tmp_path / "memory_core" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "memory_hook_gateway.py").write_text("# marker")

        # Set env var to match the path
        env_patch = patch.dict(os.environ, {"MEMORY_HOOK_PROJECT_CWD": str(tmp_path)})
        env_patch.start()

        try:
            with patch("memory_core.ownership.subprocess.run") as mock_run:
                result = is_memory_core_source_repo(tmp_path)

                # Should return True (markers exist)
                assert result is True

                # Should NOT have called git subprocess
                assert not mock_run.called, "Git subprocess should not be called when env var matches"
        finally:
            env_patch.stop()

    def test_env_var_set_but_does_not_match_calls_git(self, tmp_path):
        """VAL-GIT-004: When env var doesn't match, git subprocess is called."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        # Set env var to a DIFFERENT path
        other_path = tmp_path / "other_path"
        other_path.mkdir()

        env_patch = patch.dict(os.environ, {"MEMORY_HOOK_PROJECT_CWD": str(other_path)})
        env_patch.start()

        try:
            with patch("memory_core.ownership.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stdout = ""

                is_memory_core_source_repo(test_dir)

                # Should have called git subprocess
                assert mock_run.called, "Git subprocess should be called when env var doesn't match"
        finally:
            env_patch.stop()

    def test_env_var_not_set_calls_git(self, tmp_path):
        """VAL-GIT-004: When env var not set, git subprocess is called."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        # Ensure env var is not set
        env_patch = patch.dict(os.environ, {}, clear=False)
        env_patch.start()
        os.environ.pop("MEMORY_HOOK_PROJECT_CWD", None)

        try:
            with patch("memory_core.ownership.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stdout = ""

                is_memory_core_source_repo(test_dir)

                # Should have called git subprocess
                assert mock_run.called, "Git subprocess should be called when env var not set"
        finally:
            env_patch.stop()


class TestGitDetectorInjection:
    """Tests for git_detector parameter injection."""

    def test_git_detector_used_when_provided(self, tmp_path):
        """VAL-GIT-005: git_detector parameter must be used for test injection."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        # Create a custom git_detector
        custom_detector = MagicMock(return_value=None)

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            result = is_memory_core_source_repo(test_dir, git_detector=custom_detector)

            # Should have called the custom detector
            assert custom_detector.called, "Custom git_detector should be called"
            assert custom_detector.call_args[0][0] == test_dir.resolve()

            # Should NOT have called subprocess.run
            assert not mock_run.called, "subprocess.run should not be called when git_detector provided"

            # Should return False (detector returned None)
            assert result is False

    def test_git_detector_returns_path_checks_markers(self, tmp_path):
        """VAL-GIT-005: When git_detector returns path, check markers there."""
        # Create marker structure in a different directory
        marker_dir = tmp_path / "marker_dir"
        marker_dir.mkdir()
        tools_dir = marker_dir / "memory_core" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "memory_hook_gateway.py").write_text("# marker")

        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        # Create a custom git_detector that returns marker_dir
        custom_detector = MagicMock(return_value=marker_dir)

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            result = is_memory_core_source_repo(test_dir, git_detector=custom_detector)

            # Should return True (markers found at detector-returned path)
            assert result is True

            # Should NOT have called subprocess.run
            assert not mock_run.called


class TestMarkerBasedDetection:
    """Tests for marker-based fast path detection."""

    def test_marker_files_detected_without_git(self, tmp_path):
        """VAL-GIT-006: Marker files should be detected without spawning git."""
        # Create marker structure
        tools_dir = tmp_path / "memory_core" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "memory_hook_gateway.py").write_text("# marker")

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            result = is_memory_core_source_repo(tmp_path)

            # Should return True
            assert result is True

            # Should NOT have called git subprocess
            assert not mock_run.called, "Git subprocess should not be called when markers exist"

    def test_multiple_markers_any_one_sufficient(self, tmp_path):
        """VAL-GIT-006: Any single marker file is sufficient."""
        # Test each marker individually
        markers = [
            ("memory_core/tools/memory_hook_gateway.py", "# gateway"),
            ("memory_core/tools/factory_global_hooks.py", "# hooks"),
            ("memory_core/ownership.py", "# ownership"),
        ]

        for marker_path, content in markers:
            # Create a fresh temp directory for each test
            test_dir = tmp_path / f"test_{marker_path.replace('/', '_')}"
            test_dir.mkdir()

            full_marker = test_dir / marker_path
            full_marker.parent.mkdir(parents=True, exist_ok=True)
            full_marker.write_text(content)

            with patch("memory_core.ownership.subprocess.run") as mock_run:
                result = is_memory_core_source_repo(test_dir)

                assert result is True, f"Should detect marker: {marker_path}"
                assert not mock_run.called, f"Git should not be called for marker: {marker_path}"


class TestNormalFastPathPerformance:
    """Tests for normal (fast) path performance."""

    def test_normal_git_response_fast(self, tmp_path):
        """VAL-CROSS-010: Normal git response should be fast (< 500ms)."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        # Mock git to respond quickly (simulating normal case)
        def fast_git_response(*args, **kwargs):
            time.sleep(0.01)  # 10ms, well under 500ms
            result = MagicMock()
            result.returncode = 1
            result.stdout = ""
            return result

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            mock_run.side_effect = fast_git_response

            start = time.monotonic()
            result = is_memory_core_source_repo(test_dir)
            elapsed = time.monotonic() - start

            # Should complete quickly
            assert elapsed < 0.5, f"Normal path should complete in < 500ms, took {elapsed:.3f}s"
            assert result is False

    def test_no_artificial_delay(self, tmp_path):
        """VAL-CROSS-010: No artificial delay should be added."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        # Mock git to respond instantly
        with patch("memory_core.ownership.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""

            start = time.monotonic()
            is_memory_core_source_repo(test_dir)
            elapsed = time.monotonic() - start

            # Should be nearly instant
            assert elapsed < 0.1, f"Should be nearly instant, took {elapsed:.3f}s"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_general_exception_caught_gracefully(self, tmp_path):
        """General exceptions should be caught and return False."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        with patch("memory_core.ownership.subprocess.run") as mock_run:
            # Mock git to raise an unexpected exception
            mock_run.side_effect = RuntimeError("Unexpected error")

            result = is_memory_core_source_repo(test_dir)

            # Should return False gracefully
            assert result is False

    def test_empty_env_var_treated_as_not_set(self, tmp_path):
        """Empty MEMORY_HOOK_PROJECT_CWD should be treated as not set."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        # Set env var to empty string
        env_patch = patch.dict(os.environ, {"MEMORY_HOOK_PROJECT_CWD": ""})
        env_patch.start()

        try:
            with patch("memory_core.ownership.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stdout = ""

                is_memory_core_source_repo(test_dir)

                # Should have called git subprocess
                assert mock_run.called, "Git subprocess should be called when env var is empty"
        finally:
            env_patch.stop()

    def test_timeout_value_is_positive_integer(self):
        """VAL-GIT-001: Timeout value must be a positive integer."""
        # This is a code inspection test

        source = inspect.getsource(ownership.is_memory_core_source_repo)

        # Check that timeout= is present in the source
        assert "timeout=" in source, "timeout parameter must be present in source"

        # Extract the timeout value
        # Look for pattern like timeout=2

        match = re.search(r"timeout=(\d+)", source)
        assert match, "timeout must be set to a numeric value"

        timeout_value = int(match.group(1))
        assert timeout_value > 0, "timeout must be positive"
        assert timeout_value == 2, "timeout should be 2 seconds"
