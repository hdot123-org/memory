#!/usr/bin/env python3
"""9-case parameterized tests for _discover_canonical_files.

Tests cover: canonical / runtime / domain-recursive / domain-flat /
resource-plain / resource-glob-with-base / resource-glob-no-base /
volatile-skip / manifest-skip.

These tests establish the behavior baseline BEFORE refactoring the
function from CC=45 to CC<=20 via Phase Extraction (5 helpers).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# noqa: E402
from memory_core.tools.memory_hook_integrity_manifest import (
    _discover_canonical_files,
)

# --- Helpers ---

def _write_ownership_toml(root: Path, domains_toml: str, resources_toml: str) -> None:
    """Write a minimal ownership.toml with custom domains and resources."""
    sys_dir = root / "memory" / "system"
    sys_dir.mkdir(parents=True, exist_ok=True)
    content = 'schema_version = "memory-ownership-v1"\n'
    if domains_toml:
        content += f"\n{domains_toml}"
    if resources_toml:
        content += f"\n{resources_toml}"
    (sys_dir / "ownership.toml").write_text(content, encoding="utf-8")


# --- 9-Case Parameterized Tests ---

class TestDiscoverCanonicalFiles:
    """Parameterized behavior tests for _discover_canonical_files."""

    def test_canonical_patterns(self, tmp_path: Path):
        """Case 1: CANONICAL_PATTERNS files are discovered."""
        sys_dir = tmp_path / "memory" / "system"
        sys_dir.mkdir(parents=True)
        (sys_dir / "adapter.toml").write_text("[adapter]\n")
        (sys_dir / "memory.lock").write_text("lock\n")
        # Non-existent canonical files should be silently skipped
        # ownership.toml is also canonical and exists by default in tests

        result = _discover_canonical_files(tmp_path)
        rel = {str(p.relative_to(tmp_path)) for p in result}

        assert "memory/system/adapter.toml" in rel
        assert "memory/system/memory.lock" in rel

    def test_artifact_runtime(self, tmp_path: Path):
        """Case 2: ARTIFACT_PATTERNS scanned only when include_runtime=True."""
        sys_dir = tmp_path / "memory" / "system"
        sys_dir.mkdir(parents=True)

        # Create artifact files
        ctx_dir = tmp_path / "memory" / "artifacts" / "memory-hook" / "contexts"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "2026-07-20.json").write_text("{}")
        (ctx_dir / "session.jsonl").write_text('{"event":"test"}')
        (ctx_dir / "notes.txt").write_text("ignored")  # wrong suffix

        # Without runtime: artifact files NOT included
        result_no_rt = _discover_canonical_files(tmp_path, include_runtime=False)
        rel_no_rt = {str(p.relative_to(tmp_path)) for p in result_no_rt}
        assert "memory/artifacts/memory-hook/contexts/2026-07-20.json" not in rel_no_rt

        # With runtime: .json and .jsonl artifact files included, .txt excluded
        result_rt = _discover_canonical_files(tmp_path, include_runtime=True)
        rel_rt = {str(p.relative_to(tmp_path)) for p in result_rt}
        assert "memory/artifacts/memory-hook/contexts/2026-07-20.json" in rel_rt
        assert "memory/artifacts/memory-hook/contexts/session.jsonl" in rel_rt
        assert "memory/artifacts/memory-hook/contexts/notes.txt" not in rel_rt

    def test_domain_recursive(self, tmp_path: Path):
        """Case 3: Recursive domain walks entire tree."""
        docs_dir = tmp_path / "memory" / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "INDEX.md").write_text("# Index")
        sub = docs_dir / "design"
        sub.mkdir()
        (sub / "arch.md").write_text("# Architecture")

        # Default ownership includes memory_docs domain with recursive=True
        result = _discover_canonical_files(tmp_path)
        rel = {str(p.relative_to(tmp_path)) for p in result}

        assert "memory/docs/INDEX.md" in rel
        assert "memory/docs/design/arch.md" in rel

    def test_domain_flat(self, tmp_path: Path):
        """Case 4: Non-recursive domain only includes direct children."""
        # Create custom ownership with a flat (non-recursive) domain
        _write_ownership_toml(
            tmp_path,
            domains_toml=(
                "[[domains]]\n"
                'name = "flat_logs"\n'
                'path = "memory/logs"\n'
                'level = "STANDARD"\n'
                "recursive = false\n"
            ),
            resources_toml="",
        )

        log_dir = tmp_path / "memory" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "top.log").write_text("top")
        sub = log_dir / "nested"
        sub.mkdir()
        (sub / "deep.log").write_text("deep")

        result = _discover_canonical_files(tmp_path)
        rel = {str(p.relative_to(tmp_path)) for p in result}

        assert "memory/logs/top.log" in rel
        assert "memory/logs/nested/deep.log" not in rel

    def test_resource_plain(self, tmp_path: Path):
        """Case 5: Plain (non-glob) resource file is discovered."""
        # AGENTS.md is a default resource
        (tmp_path / "AGENTS.md").write_text("# Agents\n")

        result = _discover_canonical_files(tmp_path)
        rel = {str(p.relative_to(tmp_path)) for p in result}

        assert "AGENTS.md" in rel

    def test_resource_glob_with_base(self, tmp_path: Path):
        """Case 6: Glob resource pattern with a base directory."""
        _write_ownership_toml(
            tmp_path,
            domains_toml="",
            resources_toml=(
                "[[resources]]\n"
                'name = "log_md"\n'
                'path = "memory/log/*.md"\n'
                'level = "STANDARD"\n'
            ),
        )

        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "report.md").write_text("# Report")
        (log_dir / "data.json").write_text("{}")  # wrong suffix

        result = _discover_canonical_files(tmp_path)
        rel = {str(p.relative_to(tmp_path)) for p in result}

        assert "memory/log/report.md" in rel
        assert "memory/log/data.json" not in rel

    def test_resource_glob_no_base(self, tmp_path: Path):
        """Case 7: Glob resource pattern at root level (no base directory)."""
        _write_ownership_toml(
            tmp_path,
            domains_toml="",
            resources_toml=(
                "[[resources]]\n"
                'name = "root_md"\n'
                'path = "*.md"\n'
                'level = "STANDARD"\n'
            ),
        )

        (tmp_path / "README.md").write_text("# README")
        (tmp_path / "notes.txt").write_text("notes")  # wrong suffix

        result = _discover_canonical_files(tmp_path)
        rel = {str(p.relative_to(tmp_path)) for p in result}

        assert "README.md" in rel
        assert "notes.txt" not in rel

    def test_volatile_skip(self, tmp_path: Path):
        """Case 8: Volatile files are excluded from results."""
        sys_dir = tmp_path / "memory" / "system"
        sys_dir.mkdir(parents=True)
        (sys_dir / "adapter.toml").write_text("[adapter]\n")
        (sys_dir / "errors.log").write_text("errors")
        (sys_dir / "health-report.json").write_text("{}")

        result = _discover_canonical_files(tmp_path)
        rel = {str(p.relative_to(tmp_path)) for p in result}

        assert "memory/system/adapter.toml" in rel
        assert "memory/system/errors.log" not in rel
        assert "memory/system/health-report.json" not in rel

    def test_manifest_skip(self, tmp_path: Path):
        """Case 9: manifest.json itself is excluded (chicken-egg problem)."""
        sys_dir = tmp_path / "memory" / "system"
        sys_dir.mkdir(parents=True)
        (sys_dir / "adapter.toml").write_text("[adapter]\n")
        (sys_dir / "manifest.json").write_text('{"entries":[]}')

        result = _discover_canonical_files(tmp_path)
        rel = {str(p.relative_to(tmp_path)) for p in result}

        assert "memory/system/adapter.toml" in rel
        assert "memory/system/manifest.json" not in rel
