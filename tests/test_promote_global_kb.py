"""Tests for memory-promote CLI tool.

Tests cover VAL-PROMOTE-001 through VAL-PROMOTE-006:
- Command registration and --help/--version
- Command mode: promote file to specified domain
- Invalid --to value error
- INDEX.md update after promote
- Empty pending shows no candidates
- File not exist error
"""
import subprocess
import sys

import pytest

from memory_core.tools.global_kb_init import create_global_kb_structure


@pytest.fixture
def global_kb(tmp_path):
    """Create a temporary global KB structure."""
    kb_root = tmp_path / "global-kb"
    result = create_global_kb_structure(kb_root)
    assert result["success"], f"Failed to create global KB: {result['errors']}"
    return kb_root


@pytest.fixture
def sample_pending_file(global_kb):
    """Create a sample file in pending/ directory."""
    pending_dir = global_kb / "pending"
    test_file = pending_dir / "test-knowledge.md"
    test_file.write_text(
        """---
source_project: /path/to/project
source_file: memory/kb/lessons/test.md
captured_at: 2026-06-20T10:00:00Z
---

# Test Knowledge

This is a test knowledge item.
""",
        encoding="utf-8",
    )
    return test_file


class TestPromoteCLIRegistration:
    """VAL-PROMOTE-001: Command registration and help/version flags."""

    def test_help_flag(self):
        """memory-promote --help shows usage information."""
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.promote_global_kb", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "usage:" in result.stdout.lower() or "promote" in result.stdout.lower()

    def test_version_flag(self):
        """memory-promote --version shows version number."""
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.promote_global_kb", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "0.9.0" in result.stdout


class TestPromoteCommandMode:
    """VAL-PROMOTE-002: Command mode promotes file to specified domain."""

    def test_promote_to_operations(self, global_kb, sample_pending_file):
        """Promote file from pending/ to operations/."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.promote_global_kb",
                str(sample_pending_file),
                "--to",
                "operations",
                "--global-kb-root",
                str(global_kb),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # File moved from pending to operations
        assert not sample_pending_file.exists()
        target_file = global_kb / "operations" / sample_pending_file.name
        assert target_file.exists()

    def test_promote_to_engineering(self, global_kb, sample_pending_file):
        """Promote file from pending/ to engineering/."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.promote_global_kb",
                str(sample_pending_file),
                "--to",
                "engineering",
                "--global-kb-root",
                str(global_kb),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert not sample_pending_file.exists()
        target_file = global_kb / "engineering" / sample_pending_file.name
        assert target_file.exists()

    def test_promote_to_collaboration(self, global_kb, sample_pending_file):
        """Promote file from pending/ to collaboration/."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.promote_global_kb",
                str(sample_pending_file),
                "--to",
                "collaboration",
                "--global-kb-root",
                str(global_kb),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert not sample_pending_file.exists()
        target_file = global_kb / "collaboration" / sample_pending_file.name
        assert target_file.exists()


class TestPromoteInvalidDomain:
    """VAL-PROMOTE-003: Invalid --to value errors."""

    def test_invalid_domain(self, global_kb, sample_pending_file):
        """Invalid --to value returns non-zero exit code."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.promote_global_kb",
                str(sample_pending_file),
                "--to",
                "invalid_domain",
                "--global-kb-root",
                str(global_kb),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        # Error message mentions invalid domain
        assert "invalid" in result.stderr.lower() or "error" in result.stderr.lower()
        # File not moved
        assert sample_pending_file.exists()


class TestPromoteIndexUpdate:
    """VAL-PROMOTE-004: INDEX.md updated after promote."""

    def test_index_updated_after_promote(self, global_kb, sample_pending_file):
        """After promote, INDEX.md contains new entry."""
        # Get initial INDEX.md content
        index_path = global_kb / "INDEX.md"
        initial_content = index_path.read_text(encoding="utf-8")

        # Promote file
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.promote_global_kb",
                str(sample_pending_file),
                "--to",
                "operations",
                "--global-kb-root",
                str(global_kb),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Check INDEX.md updated
        updated_content = index_path.read_text(encoding="utf-8")
        assert updated_content != initial_content
        # INDEX should mention the file or domain
        assert sample_pending_file.name in updated_content or "operations" in updated_content


class TestPromoteEmptyPending:
    """VAL-PROMOTE-005: Empty pending shows no candidates."""

    def test_empty_pending_no_args(self, global_kb):
        """When pending/ is empty, running without args shows no candidates."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.promote_global_kb",
                "--global-kb-root",
                str(global_kb),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Output mentions no candidates or empty
        assert "无候选" in result.stdout or "empty" in result.stdout.lower() or "no candidates" in result.stdout.lower()


class TestPromoteFileNotExist:
    """VAL-PROMOTE-006: File not exist errors."""

    def test_nonexistent_file(self, global_kb):
        """Non-existent file returns non-zero exit code."""
        fake_file = global_kb / "pending" / "nonexistent.md"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.promote_global_kb",
                str(fake_file),
                "--to",
                "operations",
                "--global-kb-root",
                str(global_kb),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        # Error message mentions file not found or not exist
        assert "not found" in result.stderr.lower() or "not exist" in result.stderr.lower() or "no such file" in result.stderr.lower()


class TestPromoteInteractiveMode:
    """Interactive mode: list pending candidates when no args."""

    def test_list_pending_candidates(self, global_kb, sample_pending_file):
        """With pending files, interactive mode lists them."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.promote_global_kb",
                "--global-kb-root",
                str(global_kb),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Output mentions the pending file
        assert sample_pending_file.name in result.stdout
