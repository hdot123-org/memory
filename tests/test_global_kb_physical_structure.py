"""Tests for global KB physical structure creation (VAL-STRUCT-001, VAL-STRUCT-003).

Tests verify:
- ~/.memory/global-kb/ contains operations/, engineering/, collaboration/, pending/ subdirs
- Each subdir has a non-empty README.md describing its domain responsibilities
- Root INDEX.md contains a classification list of all four domains
- pending/README.md explains the promote and manual confirmation flow
- The create function is idempotent (doesn't overwrite existing INDEX.md)
"""
from __future__ import annotations

from pathlib import Path

# Import the function under test (will fail until implemented)
try:
    from memory_core.tools.global_kb_init import create_global_kb_structure
except ImportError:
    # Define a stub so tests can be written before implementation
    def create_global_kb_structure(*args, **kwargs):
        raise NotImplementedError("create_global_kb_structure not yet implemented")


class TestGlobalKBPhysicalStructure:
    """Test suite for VAL-STRUCT-001: 全局知识库三大域目录结构"""

    def test_create_global_kb_creates_four_directories(self, tmp_path: Path) -> None:
        """VAL-STRUCT-001: ~/.memory/global-kb/ 必须包含 operations/、engineering/、collaboration/、pending/ 四个子目录"""
        global_kb_root = tmp_path / "global-kb"

        result = create_global_kb_structure(global_kb_root)

        assert result["success"], f"create_global_kb_structure failed: {result.get('errors', [])}"

        # Verify all four directories exist
        assert (global_kb_root / "operations").is_dir(), "operations/ directory missing"
        assert (global_kb_root / "engineering").is_dir(), "engineering/ directory missing"
        assert (global_kb_root / "collaboration").is_dir(), "collaboration/ directory missing"
        assert (global_kb_root / "pending").is_dir(), "pending/ directory missing"

    def test_each_domain_has_nonempty_readme(self, tmp_path: Path) -> None:
        """VAL-STRUCT-001: 每个子目录有非空 README.md 说明该域职责"""
        global_kb_root = tmp_path / "global-kb"

        create_global_kb_structure(global_kb_root)

        domains = ["operations", "engineering", "collaboration", "pending"]
        for domain in domains:
            readme_path = global_kb_root / domain / "README.md"
            assert readme_path.is_file(), f"{domain}/README.md missing"

            content = readme_path.read_text(encoding="utf-8")
            assert len(content.strip()) > 0, f"{domain}/README.md is empty"
            assert len(content) > 50, f"{domain}/README.md too short ({len(content)} chars)"

    def test_root_has_index_md_with_four_domains(self, tmp_path: Path) -> None:
        """VAL-STRUCT-001: 根目录有 INDEX.md 含四大域分类清单"""
        global_kb_root = tmp_path / "global-kb"

        create_global_kb_structure(global_kb_root)

        index_path = global_kb_root / "INDEX.md"
        assert index_path.is_file(), "INDEX.md missing in global-kb root"

        content = index_path.read_text(encoding="utf-8")

        # Verify all four domain names appear in INDEX.md
        assert "operations" in content.lower(), "INDEX.md missing 'operations' domain"
        assert "engineering" in content.lower(), "INDEX.md missing 'engineering' domain"
        assert "collaboration" in content.lower(), "INDEX.md missing 'collaboration' domain"
        assert "pending" in content.lower(), "INDEX.md missing 'pending' domain"

    def test_pending_readme_explains_promote_flow(self, tmp_path: Path) -> None:
        """VAL-STRUCT-003: pending/README.md 必须明确说明:该目录存自动捕获候选,需经 memory-promote 人工确认后才进入正式分类"""
        global_kb_root = tmp_path / "global-kb"

        create_global_kb_structure(global_kb_root)

        pending_readme = global_kb_root / "pending" / "README.md"
        assert pending_readme.is_file(), "pending/README.md missing"

        content = pending_readme.read_text(encoding="utf-8")
        content_lower = content.lower()

        # Must mention "promote" and manual confirmation
        assert "promote" in content_lower or "提升" in content, \
            "pending/README.md must mention 'promote' or '提升'"
        assert "确认" in content or "人工" in content or "manual" in content_lower, \
            "pending/README.md must mention manual confirmation (确认/人工/manual)"

    def test_idempotent_does_not_overwrite_existing_index(self, tmp_path: Path) -> None:
        """VAL-STRUCT-002: 已存在时不覆盖 INDEX.md(幂等)"""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir(parents=True, exist_ok=True)

        # Create a custom INDEX.md with unique content
        custom_index_content = "# Custom Global KB Index\n\nThis is custom content.\n"
        index_path = global_kb_root / "INDEX.md"
        index_path.write_text(custom_index_content, encoding="utf-8")

        # Run create_global_kb_structure
        result = create_global_kb_structure(global_kb_root)

        assert result["success"], f"create_global_kb_structure failed: {result.get('errors', [])}"

        # Verify INDEX.md was NOT overwritten
        actual_content = index_path.read_text(encoding="utf-8")
        assert actual_content == custom_index_content, \
            "INDEX.md was overwritten (idempotency violated)"

    def test_idempotent_creates_missing_structure(self, tmp_path: Path) -> None:
        """If global-kb exists partially, create missing parts without error"""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir(parents=True, exist_ok=True)

        # Create only operations/ with README.md
        operations_dir = global_kb_root / "operations"
        operations_dir.mkdir()
        (operations_dir / "README.md").write_text("# Operations\n\nCustom content.\n", encoding="utf-8")

        # Run create_global_kb_structure
        result = create_global_kb_structure(global_kb_root)

        assert result["success"], f"create_global_kb_structure failed: {result.get('errors', [])}"

        # Verify all four directories now exist
        assert (global_kb_root / "operations").is_dir()
        assert (global_kb_root / "engineering").is_dir()
        assert (global_kb_root / "collaboration").is_dir()
        assert (global_kb_root / "pending").is_dir()

        # Verify existing operations/README.md was NOT overwritten
        ops_readme = (global_kb_root / "operations" / "README.md").read_text(encoding="utf-8")
        assert "Custom content" in ops_readme, "Existing README.md was overwritten"

    def test_returns_success_result(self, tmp_path: Path) -> None:
        """Function should return a result dict with success=True"""
        global_kb_root = tmp_path / "global-kb"

        result = create_global_kb_structure(global_kb_root)

        assert isinstance(result, dict), "Result should be a dict"
        assert result.get("success") is True, "Result should have success=True"
        assert "created_paths" in result or "skipped_paths" in result, "Result should have 'created_paths' or 'skipped_paths' key"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Function should create parent directories if they don't exist"""
        # Use a deeply nested path that doesn't exist
        global_kb_root = tmp_path / "deep" / "nested" / "path" / "global-kb"

        result = create_global_kb_structure(global_kb_root)

        assert result["success"], f"create_global_kb_structure failed: {result.get('errors', [])}"
        assert global_kb_root.is_dir(), "global-kb root directory not created"

    def test_readme_content_describes_domain_responsibilities(self, tmp_path: Path) -> None:
        """Each domain README should describe what belongs in that domain"""
        global_kb_root = tmp_path / "global-kb"

        create_global_kb_structure(global_kb_root)

        # Operations domain should mention operations-related topics
        ops_readme = (global_kb_root / "operations" / "README.md").read_text(encoding="utf-8").lower()
        assert any(keyword in ops_readme for keyword in ["运维", "服务器", "部署", "operation", "server", "deploy"]), \
            "operations/README.md should describe operations-related topics"

        # Engineering domain should mention engineering-related topics
        eng_readme = (global_kb_root / "engineering" / "README.md").read_text(encoding="utf-8").lower()
        assert any(keyword in eng_readme for keyword in ["工程", "ci", "工具链", "engineering", "toolchain", "ci/cd"]), \
            "engineering/README.md should describe engineering-related topics"

        # Collaboration domain should mention collaboration-related topics
        collab_readme = (global_kb_root / "collaboration" / "README.md").read_text(encoding="utf-8").lower()
        assert any(keyword in collab_readme for keyword in ["协作", "agent", "团队", "collaboration", "team"]), \
            "collaboration/README.md should describe collaboration-related topics"
