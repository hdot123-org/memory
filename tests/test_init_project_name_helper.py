#!/usr/bin/env python3
"""Tests for the _project_name helper in init_project_memory.

Covers the silent-except fix: narrowed exception types + debug logging,
while preserving the fallback-to-directory-name behaviour.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_core.tools.init_project_memory import _project_name, _slug


class TestProjectNameFallbackWhenGitUnavailable:
    """Verify that _project_name falls back to directory name when git subprocess fails."""

    def test_project_name_fallback_when_git_unavailable(self, tmp_path: Path) -> None:
        """Monkeypatch subprocess.run to raise FileNotFoundError; assert directory name fallback."""
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = _project_name(tmp_path)

        # Should fall back to directory name, slugged
        expected = _slug(tmp_path.name)
        assert result == expected

    def test_project_name_fallback_on_timeout(self, tmp_path: Path) -> None:
        """subprocess.TimeoutExpired should also trigger fallback."""
        fake_exc = subprocess.TimeoutExpired(cmd=["git"], timeout=5)
        with patch("subprocess.run", side_effect=fake_exc):
            result = _project_name(tmp_path)

        assert result == _slug(tmp_path.name)

    def test_project_name_fallback_on_os_error(self, tmp_path: Path) -> None:
        """Generic OSError should also trigger fallback."""
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            result = _project_name(tmp_path)

        assert result == _slug(tmp_path.name)

    def test_project_name_returns_scope_when_provided(self, tmp_path: Path) -> None:
        """When scope is provided, it should be returned regardless of git status."""
        result = _project_name(tmp_path, scope="my_scope")
        assert result == "my_scope"


class TestProjectNameFallbackLoggedAtDebug:
    """Verify that git query failures are logged at DEBUG level."""

    def test_project_name_fallback_logged_at_debug(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """When git fails, a DEBUG-level log entry is emitted."""
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            with caplog.at_level("DEBUG", logger="memory_core.tools.init_project_memory"):
                _project_name(tmp_path)

        # Check that a debug message mentioning git remote failure exists
        assert any(
            "git remote query failed" in record.message
            for record in caplog.records
            if record.levelname == "DEBUG"
        )

    def test_project_name_no_log_on_success(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """When git succeeds, no debug log about failure should be emitted."""
        fake_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="https://github.com/org/my-repo.git\n", stderr=""
        )
        with patch("subprocess.run", return_value=fake_result):
            with caplog.at_level("DEBUG", logger="memory_core.tools.init_project_memory"):
                result = _project_name(tmp_path)

        assert result == "my_repo"
        assert not any(
            "git remote query failed" in record.message
            for record in caplog.records
        )
