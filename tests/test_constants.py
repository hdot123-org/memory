"""Unit tests for memory_core.constants invariants.

Validates that the single-source-of-truth constants remain structurally
sound — schemas, required paths, host definitions, and version format.
"""

import re

from memory_core import __version__, constants

# ---------------------------------------------------------------------------
# Supported hosts
# ---------------------------------------------------------------------------


def test_supported_hosts_contains_factory():
    """``factory`` must always be in SUPPORTED_HOSTS."""
    assert "factory" in constants.SUPPORTED_HOSTS


def test_supported_hosts_is_tuple():
    """SUPPORTED_HOSTS must be a tuple (immutable)."""
    assert isinstance(constants.SUPPORTED_HOSTS, tuple)


# ---------------------------------------------------------------------------
# Required memory files / dirs
# ---------------------------------------------------------------------------


def test_required_memory_files_has_lock():
    """memory.lock is a mandatory memory file."""
    assert "memory.lock" in constants.REQUIRED_MEMORY_FILES


def test_required_memory_dirs_contains_kb_subdirs():
    """All four kb sub-directories are required."""
    expected = {"kb/projects", "kb/decisions", "kb/lessons", "kb/global"}
    assert expected.issubset(set(constants.REQUIRED_MEMORY_DIRS))


# ---------------------------------------------------------------------------
# Canonical schema identifiers
# ---------------------------------------------------------------------------


def test_canonical_memory_lock_schema():
    """Canonical schema identifier should match the expected prefix."""
    assert constants.CANONICAL_MEMORY_LOCK_SCHEMA.startswith("context-package-")


def test_ownership_schema_version():
    """Ownership schema version should follow the memory-ownership pattern."""
    assert constants.OWNERSHIP_SCHEMA_VERSION.startswith("memory-ownership-")


# ---------------------------------------------------------------------------
# Source repo modes
# ---------------------------------------------------------------------------


def test_valid_source_repo_modes():
    """readonly and develop are the two valid source-repo modes."""
    assert "readonly" in constants.VALID_SOURCE_REPO_MODES
    assert "develop" in constants.VALID_SOURCE_REPO_MODES
    assert len(constants.VALID_SOURCE_REPO_MODES) == 2


# ---------------------------------------------------------------------------
# Version format (PEP 440 / semver-ish)
# ---------------------------------------------------------------------------


def test_version_is_valid_format():
    """Package version should be a valid PEP 440-ish string."""
    assert re.match(r"^\d+\.\d+\.\d+", __version__), f"Version '{__version__}' does not look like a release version"


# ---------------------------------------------------------------------------
# Migration log pattern
# ---------------------------------------------------------------------------


def test_migration_log_pattern_matches_valid_line():
    """The migration log regex should accept a well-formed line."""
    line = "2026-01-15T10:30:00Z | 0.1.0 | 0.2.0 | success | Migrated schema"
    assert constants.MIGRATION_LOG_LINE_PATTERN.match(line) is not None


def test_migration_log_pattern_rejects_garbage():
    """The migration log regex should reject malformed input."""
    assert constants.MIGRATION_LOG_LINE_PATTERN.match("not a log line") is None
