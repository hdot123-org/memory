"""
Tests for MCP global interface tools: read_global and propose_write

Tests cover:
- read_global: file reading, path validation, pending exclusion
- propose_write: deduplication, frontmatter generation, pending-only routing
- report polish: source field backfill, project basename normalization
"""

import os
import tempfile
from pathlib import Path

from memory_core.tools.mcp_server import _propose_write, _read_global


class TestReadGlobal:
    """Test read_global MCP tool"""

    def test_read_existing_file(self):
        """Test reading an existing file from global KB"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up test global KB
            global_root = Path(tmpdir)
            test_file = global_root / "engineering" / "test.md"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_content = "# Test\n\nThis is test content."
            test_file.write_text(test_content, encoding="utf-8")

            # Use environment variable to override global KB root
            old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            try:
                os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)
                result = _read_global("engineering/test.md")

                assert result["status"] == "success"
                assert result["content"] == test_content
                assert result["relative_path"] == "engineering/test.md"
                assert result["path"].endswith("engineering/test.md")
            finally:
                if old_env is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_env

    def test_read_nonexistent_file(self):
        """Test reading a non-existent file returns error"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)

            old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            try:
                os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)
                result = _read_global("engineering/nonexistent.md")

                assert result["status"] == "error"
                assert "not found" in result["message"].lower()
            finally:
                if old_env is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_env

    def test_read_pending_excluded(self):
        """Test that pending/ directory is excluded from read_global"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            pending_file = global_root / "pending" / "proposal.md"
            pending_file.parent.mkdir(parents=True, exist_ok=True)
            pending_file.write_text("# Pending proposal", encoding="utf-8")

            old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            try:
                os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)
                result = _read_global("pending/proposal.md")

                assert result["status"] == "error"
                assert "pending" in result["message"].lower()
            finally:
                if old_env is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_env

    def test_read_path_traversal_blocked(self):
        """Test that path traversal attempts are blocked"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)

            old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            try:
                os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)
                # Test ../ traversal
                result = _read_global("../etc/passwd")
                assert result["status"] == "error"
                assert "traversal" in result["message"].lower() or "invalid" in result["message"].lower()

                # Test absolute path
                result = _read_global("/etc/passwd")
                assert result["status"] == "error"
                assert "absolute" in result["message"].lower() or "invalid" in result["message"].lower()
            finally:
                if old_env is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_env

    def test_read_empty_path(self):
        """Test that empty relative_path is rejected"""
        result = _read_global("")
        assert result["status"] == "error"
        assert "invalid" in result["message"].lower() or "required" in result["message"].lower()

    def test_read_pending_dot_slash_variant_rejected(self):
        """Test that './pending/foo.md' is rejected (normpath bypass prevention)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            pending_file = global_root / "pending" / "foo.md"
            pending_file.parent.mkdir(parents=True, exist_ok=True)
            pending_file.write_text("# Pending content", encoding="utf-8")

            old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            try:
                os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)
                # Try to read via ./pending/ variant
                result = _read_global("./pending/foo.md")
                assert result["status"] == "error"
                assert "pending" in result["message"].lower()
                assert "denied" in result["message"].lower()
            finally:
                if old_env is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_env

    def test_read_pending_case_variant_rejected(self):
        """Test that 'Pending/foo.md' is rejected (case-variant bypass prevention)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            pending_file = global_root / "pending" / "foo.md"
            pending_file.parent.mkdir(parents=True, exist_ok=True)
            pending_file.write_text("# Pending content", encoding="utf-8")

            old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            try:
                os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)
                # Try to read via Pending/ (capitalized) variant
                result = _read_global("Pending/foo.md")
                # Should be rejected (on case-insensitive FS like APFS, this resolves to pending/)
                assert result["status"] == "error"
                assert "pending" in result["message"].lower()
            finally:
                if old_env is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_env

    def test_read_formal_domain_unaffected(self):
        """Test that normal formal domain reads are not affected by pending checks"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            # Create a formal domain file
            formal_file = global_root / "engineering" / "test.md"
            formal_file.parent.mkdir(parents=True, exist_ok=True)
            formal_content = "# Formal Content\n\nThis is formal domain content."
            formal_file.write_text(formal_content, encoding="utf-8")

            old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            try:
                os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)
                result = _read_global("engineering/test.md")
                assert result["status"] == "success"
                assert result["content"] == formal_content
            finally:
                if old_env is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_env


class TestProposeWrite:
    """Test propose_write MCP tool"""

    def _set_env(self, global_root):
        """Helper to set MEMORY_CORE_GLOBAL_KB_ROOT env var"""
        self._old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
        os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)

    def _restore_env(self):
        """Helper to restore MEMORY_CORE_GLOBAL_KB_ROOT env var"""
        if self._old_env is None:
            os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
        else:
            os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = self._old_env

    def test_propose_new_item(self):
        """Test proposing a new item to pending/"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            pending_dir = global_root / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)

            self._set_env(global_root)
            try:
                result = _propose_write(
                    title="Test Proposal",
                    content="# Test Content\n\nThis is a test.",
                    domain="engineering",
                    source_refs=[{"project": "test-proj", "path": "docs/test.md"}],
                )

                assert result["status"] == "success"
                assert result["action"] == "written"
                assert result["relative_path"].startswith("pending/")
                assert result["relative_path"].endswith(".md")

                # Verify file was created
                file_path = global_root / result["relative_path"]
                assert file_path.exists()

                # Verify frontmatter
                content = file_path.read_text(encoding="utf-8")
                assert "---" in content
                assert "Test Proposal" in content
                assert "domain: engineering" in content
                assert "source: mcp-propose" in content
                assert "source_refs:" in content
                assert "test-proj" in content
            finally:
                self._restore_env()

    def test_propose_duplicate_detection(self):
        """Test that duplicate proposals are detected"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            pending_dir = global_root / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)

            self._set_env(global_root)
            try:
                # First proposal
                result1 = _propose_write(
                    title="Duplicate Test",
                    content="# Same Content",
                    domain="engineering",
                    source_refs=[{"project": "proj1", "path": "doc1.md"}],
                )
                assert result1["status"] == "success"
                assert result1["action"] == "written"

                # Second proposal with same title and content
                result2 = _propose_write(
                    title="Duplicate Test",
                    content="# Same Content",
                    domain="engineering",
                    source_refs=[{"project": "proj2", "path": "doc2.md"}],
                )

                # Should detect duplicate and merge source_refs
                assert result2["status"] == "success"
                assert result2["action"] == "merged"

                # Verify source_refs were merged
                file_path = global_root / result2["relative_path"]
                content = file_path.read_text(encoding="utf-8")
                assert "proj1" in content
                assert "proj2" in content
            finally:
                self._restore_env()

    def test_propose_different_content_same_title(self):
        """Test that different content with same title creates separate files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            pending_dir = global_root / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)

            self._set_env(global_root)
            try:
                result1 = _propose_write(
                    title="Same Title",
                    content="# Content A",
                    domain="engineering",
                    source_refs=[{"project": "proj1", "path": "doc1.md"}],
                )
                assert result1["status"] == "success"
                assert result1["action"] == "written"

                result2 = _propose_write(
                    title="Same Title",
                    content="# Content B - Completely Different",
                    domain="engineering",
                    source_refs=[{"project": "proj2", "path": "doc2.md"}],
                )

                assert result2["status"] == "success"
                assert result2["action"] == "written"
                # Should have different paths (with hash suffix)
                assert result1["relative_path"] != result2["relative_path"]
            finally:
                self._restore_env()

    def test_propose_invalid_domain(self):
        """Test that invalid domain is rejected"""
        result = _propose_write(
            title="Test",
            content="Test content",
            domain="invalid_domain",
            source_refs=[],
        )

        assert result["status"] == "error"
        assert "domain" in result["message"].lower()

    def test_propose_missing_required_fields(self):
        """Test that missing required fields are rejected"""
        # Missing title
        result = _propose_write(
            title="",
            content="Test content",
            domain="engineering",
            source_refs=[],
        )
        assert result["status"] == "error"
        assert "title" in result["message"].lower()

        # Missing content
        result = _propose_write(
            title="Test",
            content="",
            domain="engineering",
            source_refs=[],
        )
        assert result["status"] == "error"
        assert "content" in result["message"].lower()

        # Missing domain
        result = _propose_write(
            title="Test",
            content="Test content",
            domain="",
            source_refs=[],
        )
        assert result["status"] == "error"
        assert "domain" in result["message"].lower()

    def test_propose_no_git_commit(self):
        """Test that propose_write does not create git commits"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)

            # Initialize git repo
            import subprocess

            subprocess.run(["git", "init"], cwd=global_root, capture_output=True, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"], cwd=global_root, capture_output=True, check=True
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=global_root, capture_output=True, check=True
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "Initial"], cwd=global_root, capture_output=True, check=True
            )

            # Get initial commit count
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=global_root,
                capture_output=True,
                text=True,
                check=True,
            )
            initial_commits = int(result.stdout.strip())

            pending_dir = global_root / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)

            self._set_env(global_root)
            try:
                # Propose an item
                _propose_write(
                    title="No Commit Test",
                    content="# Test",
                    domain="engineering",
                    source_refs=[],
                )

                # Verify no new commits
                result = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD"],
                    cwd=global_root,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                final_commits = int(result.stdout.strip())
                assert final_commits == initial_commits
            finally:
                self._restore_env()

    def test_propose_creates_pending_dir(self):
        """Test that pending/ directory is created if it doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            # Don't create pending/ yet

            self._set_env(global_root)
            try:
                result = _propose_write(
                    title="Create Dir Test",
                    content="# Test",
                    domain="engineering",
                    source_refs=[],
                )

                assert result["status"] == "success"
                assert (global_root / "pending").exists()
                assert (global_root / "pending").is_dir()
            finally:
                self._restore_env()


class TestReportPolish:
    """报告 polish：candidates 序列化 source 字段 + source_refs.project basename"""

    def test_candidates_report_has_source_field(self):
        """报告中每个 candidate 条目的 source 字段非 null（与落盘 frontmatter 一致）"""
        from memory_core.evolution.analyzer import IncrementalAnalyzer
        from memory_core.evolution.extractor import NoLlmExtractor
        from memory_core.tools.evolve_cli import _run_projects

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create a test project with a lesson file
            proj_root = tmpdir / "test-proj"
            proj_root.mkdir()
            kb_dir = proj_root / "memory" / "kb" / "lessons"
            kb_dir.mkdir(parents=True)
            lesson_file = kb_dir / "test-lesson.md"
            lesson_file.write_text("# Test Lesson\n\nThis is a test lesson content.", encoding="utf-8")

            # Set up evolution root
            evo_root = tmpdir / "evolution"
            evo_root.mkdir()

            # Create analyzer and extractor
            state_file = evo_root / "state.json"
            config = {"analyze": {"include_docs": True, "include_daily_logs": True, "max_files_per_project": 50}}
            analyzer = IncrementalAnalyzer(state_file, config)
            no_llm_extractor = NoLlmExtractor()

            # Prepare run report and candidates list
            run_report = {"projects": [], "errors": []}
            all_candidates = []

            # Call _run_projects (production code path)
            had_fatal, _ = _run_projects(
                projects_to_process=[proj_root],
                analyzer=analyzer,
                no_llm=True,
                no_llm_extractor=no_llm_extractor,
                llm_extractor=None,
                is_single_project=True,
                evolution_root=evo_root,
                run_report=run_report,
                all_candidates=all_candidates,
            )

            # Verify the report was generated
            assert len(run_report["projects"]) > 0
            proj_report = run_report["projects"][0]

            # Verify candidates have source field
            assert len(proj_report["candidates"]) > 0
            for cand in proj_report["candidates"]:
                assert "source" in cand
                assert cand["source"] == "memory-evolve"

            # Also verify all_candidates list
            assert len(all_candidates) > 0
            for cand in all_candidates:
                assert "source" in cand
                assert cand["source"] == "memory-evolve"

    def test_source_refs_project_basename_normalization(self):
        """source_refs.project 统一为 basename（与 refined 一致）"""
        from memory_core.evolution.analyzer import IncrementalAnalyzer
        from memory_core.evolution.extractor import NoLlmExtractor
        from memory_core.tools.evolve_cli import _run_projects

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create a test project with a lesson file
            proj_root = tmpdir / "test-proj"
            proj_root.mkdir()
            kb_dir = proj_root / "memory" / "kb" / "lessons"
            kb_dir.mkdir(parents=True)
            lesson_file = kb_dir / "test-lesson.md"
            lesson_file.write_text("# Test Lesson\n\nThis is a test lesson content.", encoding="utf-8")

            # Set up evolution root
            evo_root = tmpdir / "evolution"
            evo_root.mkdir()

            # Create analyzer and extractor
            state_file = evo_root / "state.json"
            config = {"analyze": {"include_docs": True, "include_daily_logs": True, "max_files_per_project": 50}}
            analyzer = IncrementalAnalyzer(state_file, config)
            no_llm_extractor = NoLlmExtractor()

            # Prepare run report and candidates list
            run_report = {"projects": [], "errors": []}
            all_candidates = []

            # Call _run_projects (production code path)
            _run_projects(
                projects_to_process=[proj_root],
                analyzer=analyzer,
                no_llm=True,
                no_llm_extractor=no_llm_extractor,
                llm_extractor=None,
                is_single_project=True,
                evolution_root=evo_root,
                run_report=run_report,
                all_candidates=all_candidates,
            )

            # Verify source_refs.project is basename (not absolute path)
            assert len(all_candidates) > 0
            for cand in all_candidates:
                assert "source_refs" in cand
                for ref in cand["source_refs"]:
                    assert "project" in ref
                    # Should be basename, not absolute path
                    assert ref["project"] == "test-proj"
                    assert not Path(ref["project"]).is_absolute()

    def test_propose_write_formal_domain_dedup(self):
        """propose_write 与正式域既有条目指纹冲突 → 明确信号、不新建、不覆盖"""
        with tempfile.TemporaryDirectory() as tmpdir:
            global_root = Path(tmpdir)
            pending_dir = global_root / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)

            # 预置正式域条目
            formal_content = "# Formal Entry\n\nThis is existing content."
            formal_dir = global_root / "engineering"
            formal_dir.mkdir(parents=True, exist_ok=True)
            formal_file = formal_dir / "existing-item.md"
            formal_file.write_text(formal_content, encoding="utf-8")

            old_env = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(global_root)
            try:
                # propose_write 与正式域相同内容
                result = _propose_write(
                    title="Formal Dedup Test",
                    content=formal_content,
                    domain="engineering",
                    source_refs=[{"project": "test-proj", "path": "doc.md"}],
                )

                # 应检测到重复
                assert result["status"] == "success"
                assert result["action"] in ("skipped", "merged")
                assert "Duplicate" in result.get("message", "") or "duplicate" in result.get("message", "").lower()

                # pending/ 不应新增文件（除 README 外）
                pending_files = [f for f in pending_dir.glob("*.md") if f.name != "README.md"]
                assert len(pending_files) == 0

                # 正式域原文件未被覆盖
                assert formal_file.read_text(encoding="utf-8") == formal_content
            finally:
                if old_env is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_env
