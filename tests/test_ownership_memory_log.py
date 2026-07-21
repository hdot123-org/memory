"""Tests for F1: ownership scope extension — memory_log domain and error_log resource.

Covers:
- VAL-F1-001: memory_log Domain Registered as STANDARD
- VAL-F1-002: error_log Resource Covers errors.jsonl Files
- VAL-F1-003: _discover_canonical_files Finds memory/log/ Files
- VAL-F1-004: VOLATILE_PATTERNS No Longer Excludes errors.jsonl
- VAL-F1-005: classify_owned_path Correctly Classifies memory/log/ Paths
- VAL-F1-006: Existing Ownership Domains Unchanged
"""

import pytest

from memory_core.ownership import (
    DEFAULT_OWNERSHIP_DOMAINS,
    DEFAULT_OWNERSHIP_RESOURCES,
    Owned,
    ProtectionLevel,
    classify_owned_path,
)
from memory_core.tools.memory_hook_integrity_manifest import (
    _discover_canonical_files,
    _is_volatile,
)

# --- VAL-F1-001: memory_log Domain Registered as STANDARD ---

class TestMemoryLogDomain:
    """Test memory_log domain registration."""

    def test_memory_log_domain_exists(self):
        """memory_log domain should exist in DEFAULT_OWNERSHIP_DOMAINS."""
        domain_names = {d.name for d in DEFAULT_OWNERSHIP_DOMAINS}
        assert "memory_log" in domain_names

    def test_memory_log_domain_path(self):
        """memory_log domain should have path='memory/log'."""
        memory_log = next(
            d for d in DEFAULT_OWNERSHIP_DOMAINS if d.name == "memory_log"
        )
        assert memory_log.path == "memory/log"

    def test_memory_log_domain_level_is_standard(self):
        """memory_log domain should have STANDARD protection level."""
        memory_log = next(
            d for d in DEFAULT_OWNERSHIP_DOMAINS if d.name == "memory_log"
        )
        assert memory_log.level == ProtectionLevel.STANDARD

    def test_memory_log_domain_is_recursive(self):
        """memory_log domain should be recursive."""
        memory_log = next(
            d for d in DEFAULT_OWNERSHIP_DOMAINS if d.name == "memory_log"
        )
        assert memory_log.recursive is True


# --- VAL-F1-002: error_log Resource Covers errors.jsonl Files ---

class TestErrorLogResource:
    """Test error_log resource registration."""

    def test_error_log_resource_exists(self):
        """error_log resource should exist in DEFAULT_OWNERSHIP_RESOURCES."""
        resource_names = {r.name for r in DEFAULT_OWNERSHIP_RESOURCES}
        assert "error_log" in resource_names

    def test_error_log_resource_path_pattern(self):
        """error_log resource should match memory/log/*-errors.jsonl pattern."""
        error_log = next(
            r for r in DEFAULT_OWNERSHIP_RESOURCES if r.name == "error_log"
        )
        assert "errors.jsonl" in error_log.path

    def test_error_log_resource_level_is_standard(self):
        """error_log resource should have STANDARD protection level."""
        error_log = next(
            r for r in DEFAULT_OWNERSHIP_RESOURCES if r.name == "error_log"
        )
        assert error_log.level == ProtectionLevel.STANDARD

    def test_classify_error_log_path(self):
        """classify_owned_path should classify errors.jsonl as owned."""
        result = classify_owned_path("memory/log/2025-01-01-errors.jsonl")
        assert isinstance(result, Owned)


# --- VAL-F1-003: _discover_canonical_files Finds memory/log/ Files ---

class TestDiscoverCanonicalFilesMemoryLog:
    """Test that _discover_canonical_files discovers memory/log/ files."""

    def test_discover_md_files_in_memory_log(self, tmp_path):
        """Should discover .md files in memory/log/."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "2025-01-01-sessions.md").write_text("# Sessions\n")

        files = _discover_canonical_files(tmp_path)
        rel_paths = {str(f.relative_to(tmp_path)) for f in files}
        assert "memory/log/2025-01-01-sessions.md" in rel_paths

    def test_discover_jsonl_files_in_memory_log(self, tmp_path):
        """Should discover .jsonl files in memory/log/."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "2025-01-01-errors.jsonl").write_text("{}\n")

        files = _discover_canonical_files(tmp_path)
        rel_paths = {str(f.relative_to(tmp_path)) for f in files}
        assert "memory/log/2025-01-01-errors.jsonl" in rel_paths

    def test_discover_multiple_files(self, tmp_path):
        """Should discover multiple files in memory/log/."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "2025-01-01-sessions.md").write_text("# Sessions\n")
        (log_dir / "2025-01-01-errors.jsonl").write_text("{}\n")
        (log_dir / "2025-01-02-sessions.md").write_text("# More\n")

        files = _discover_canonical_files(tmp_path)
        rel_paths = {str(f.relative_to(tmp_path)) for f in files}
        assert "memory/log/2025-01-01-sessions.md" in rel_paths
        assert "memory/log/2025-01-01-errors.jsonl" in rel_paths
        assert "memory/log/2025-01-02-sessions.md" in rel_paths


# --- VAL-F1-004: VOLATILE_PATTERNS No Longer Excludes errors.jsonl ---

class TestVolatilePatternsNotExcludeErrorsJsonl:
    """Test that errors.jsonl is NOT matched by volatile patterns."""

    def test_errors_jsonl_not_volatile(self):
        """memory/log/2025-01-01-errors.jsonl should NOT be volatile."""
        assert _is_volatile("memory/log/2025-01-01-errors.jsonl") is False

    def test_other_errors_jsonl_not_volatile(self):
        """Other errors.jsonl paths should NOT be volatile."""
        assert _is_volatile("memory/log/2025-12-31-errors.jsonl") is False
        assert _is_volatile("memory/log/today-errors.jsonl") is False


# --- VAL-F1-005: classify_owned_path Correctly Classifies memory/log/ Paths ---

class TestClassifyOwnedPathMemoryLog:
    """Test classify_owned_path for memory/log/ paths."""

    def test_classify_sessions_md(self):
        """memory/log/*.md should be classified under memory_log domain."""
        result = classify_owned_path("memory/log/2025-01-01-sessions.md")
        assert isinstance(result, Owned)
        assert result.domain is not None
        assert result.domain.name == "memory_log"

    def test_classify_errors_jsonl(self):
        """memory/log/*-errors.jsonl should be owned."""
        result = classify_owned_path("memory/log/2025-01-01-errors.jsonl")
        assert isinstance(result, Owned)

    def test_classify_nested_memory_log_file(self):
        """Nested files under memory/log/ should be classified."""
        result = classify_owned_path("memory/log/2025-01/01/sessions.md")
        assert isinstance(result, Owned)
        assert result.domain is not None
        assert result.domain.name == "memory_log"


# --- VAL-F1-006: Existing Ownership Domains Unchanged ---

class TestExistingDomainsUnchanged:
    """Test that existing domains and resources are not affected."""

    def test_existing_domain_count(self):
        """Should have 7 domains total (6 existing + memory_log)."""
        assert len(DEFAULT_OWNERSHIP_DOMAINS) == 7

    def test_existing_resource_count(self):
        """Should have 11 resources total (10 existing + error_log)."""
        assert len(DEFAULT_OWNERSHIP_RESOURCES) == 11

    @pytest.mark.parametrize("name", [
        "memory_docs",
        "memory_kb",
        "memory_system",
        "project_map",
        "audit",
        "review",
    ])
    def test_existing_domains_still_present(self, name):
        """All 6 original domains should still exist."""
        domain_names = {d.name for d in DEFAULT_OWNERSHIP_DOMAINS}
        assert name in domain_names

    def test_existing_domains_are_critical(self):
        """Original 6 domains should still be CRITICAL level."""
        for domain in DEFAULT_OWNERSHIP_DOMAINS:
            if domain.name != "memory_log":
                assert domain.level == ProtectionLevel.CRITICAL
            else:
                # memory_log is STANDARD
                assert domain.level == ProtectionLevel.STANDARD

    @pytest.mark.parametrize("name", [
        "agents_md",
        "audit_summary",
        "readme_md",
        "changelog_md",
        "contributing_md",
        "memory_lock",
        "adapter_toml",
        "ownership_toml",
        "migrations_log",
        "manifest_json",
    ])
    def test_existing_resources_still_present(self, name):
        """All 10 original resources should still exist."""
        resource_names = {r.name for r in DEFAULT_OWNERSHIP_RESOURCES}
        assert name in resource_names

    def test_memory_log_is_only_standard_domain(self):
        """memory_log should be the only STANDARD domain among defaults."""
        standard_domains = [
            d for d in DEFAULT_OWNERSHIP_DOMAINS
            if d.level == ProtectionLevel.STANDARD
        ]
        assert len(standard_domains) == 1
        assert standard_domains[0].name == "memory_log"
