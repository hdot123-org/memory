# -*- coding: utf-8 -*-
"""doc_router.py 单元测试。

覆盖所有函数和边界情况：
- resolve_doc_path 每个 category
- resolve_doc_path 未知 category → draft fallback
- is_registered_doc_dir 注册目录 → True
- is_registered_doc_dir 例外目录 → True
- is_registered_doc_dir 未注册目录 → False
- is_registered_doc_dir 非 memory/ 路径 → False
"""

from pathlib import Path

import pytest

from memory_core.tools.doc_router import (
    DOC_CATEGORIES,
    EXCEPTION_DIRS,
    REPO_ROOT,
    is_registered_doc_dir,
    resolve_doc_path,
)


class TestDocCategories:
    """DOC_CATEGORIES 常量测试。"""

    def test_has_10_categories(self) -> None:
        """DOC_CATEGORIES 必须包含 10 个分类标签。"""
        assert len(DOC_CATEGORIES) == 10

    def test_has_required_categories(self) -> None:
        """必须包含所有必需的分类标签。"""
        required = {
            "decision",
            "lesson",
            "refactor-log",
            "plan",
            "runbook",
            "bug-report",
            "audit",
            "rfc",
            "note",
            "draft",
        }
        assert set(DOC_CATEGORIES.keys()) == required

    def test_all_paths_are_relative(self) -> None:
        """所有路径必须是相对路径（不以 / 开头）。"""
        for category, path in DOC_CATEGORIES.items():
            assert not path.startswith("/"), f"{category} 路径不能是绝对路径"

    def test_all_paths_end_with_slash(self) -> None:
        """所有路径必须以 / 结尾。"""
        for category, path in DOC_CATEGORIES.items():
            assert path.endswith("/"), f"{category} 路径必须以 / 结尾"


class TestResolveDocPath:
    """resolve_doc_path() 函数测试。"""

    def test_resolve_decision_category(self) -> None:
        """decision 分类返回正确路径。"""
        result = resolve_doc_path("decision", "D-001.md")
        expected = REPO_ROOT / "memory/kb/decisions/D-001.md"
        assert result == expected

    def test_resolve_lesson_category(self) -> None:
        """lesson 分类返回正确路径。"""
        result = resolve_doc_path("lesson", "L-001.md")
        expected = REPO_ROOT / "memory/kb/lessons/L-001.md"
        assert result == expected

    def test_resolve_refactor_log_category(self) -> None:
        """refactor-log 分类返回正确路径。"""
        result = resolve_doc_path("refactor-log", "R-001.md")
        expected = REPO_ROOT / "memory/docs/refactor-logs/R-001.md"
        assert result == expected

    def test_resolve_plan_category(self) -> None:
        """plan 分类返回正确路径。"""
        result = resolve_doc_path("plan", "P-001.md")
        expected = REPO_ROOT / "memory/docs/plans/P-001.md"
        assert result == expected

    def test_resolve_runbook_category(self) -> None:
        """runbook 分类返回正确路径。"""
        result = resolve_doc_path("runbook", "RB-001.md")
        expected = REPO_ROOT / "memory/docs/runbooks/RB-001.md"
        assert result == expected

    def test_resolve_bug_report_category(self) -> None:
        """bug-report 分类返回正确路径。"""
        result = resolve_doc_path("bug-report", "B-001.md")
        expected = REPO_ROOT / "memory/docs/bug-reports/B-001.md"
        assert result == expected

    def test_resolve_audit_category(self) -> None:
        """audit 分类返回正确路径。"""
        result = resolve_doc_path("audit", "A-001.md")
        expected = REPO_ROOT / "memory/docs/audit/A-001.md"
        assert result == expected

    def test_resolve_rfc_category(self) -> None:
        """rfc 分类返回正确路径。"""
        result = resolve_doc_path("rfc", "RFC-001.md")
        expected = REPO_ROOT / "memory/docs/rfcs/RFC-001.md"
        assert result == expected

    def test_resolve_note_category(self) -> None:
        """note 分类返回正确路径。"""
        result = resolve_doc_path("note", "N-001.md")
        expected = REPO_ROOT / "memory/docs/notes/N-001.md"
        assert result == expected

    def test_resolve_draft_category(self) -> None:
        """draft 分类返回正确路径。"""
        result = resolve_doc_path("draft", "draft-001.md")
        expected = REPO_ROOT / "memory/docs/drafts/draft-001.md"
        assert result == expected

    def test_resolve_unknown_category_fallback_to_draft(self) -> None:
        """未知分类应该 fallback 到 draft。"""
        result = resolve_doc_path("unknown-category", "test.md")
        expected = REPO_ROOT / "memory/docs/drafts/test.md"
        assert result == expected

    def test_resolve_empty_category_fallback_to_draft(self) -> None:
        """空字符串分类应该 fallback 到 draft。"""
        result = resolve_doc_path("", "test.md")
        expected = REPO_ROOT / "memory/docs/drafts/test.md"
        assert result == expected

    def test_resolve_path_is_absolute(self) -> None:
        """返回的路径应该是绝对路径。"""
        result = resolve_doc_path("decision", "D-001.md")
        assert result.is_absolute()


class TestIsRegisteredDocDir:
    """is_registered_doc_dir() 函数测试。"""

    @pytest.mark.parametrize(
        "path,expected",
        [
            (Path("memory/kb/decisions/"), True),
            (Path("memory/kb/lessons/"), True),
            (Path("memory/docs/refactor-logs/"), True),
            (Path("memory/docs/plans/"), True),
            (Path("memory/docs/runbooks/"), True),
            (Path("memory/docs/bug-reports/"), True),
            (Path("memory/docs/audit/"), True),
            (Path("memory/docs/rfcs/"), True),
            (Path("memory/docs/notes/"), True),
            (Path("memory/docs/drafts/"), True),
        ],
    )
    def test_registered_directories(self, path: Path, expected: bool) -> None:
        """注册目录应该返回 True。"""
        assert is_registered_doc_dir(path) == expected

    @pytest.mark.parametrize(
        "path,expected",
        [
            (Path("memory/docs/archive/"), True),
            (Path("memory/docs/system/"), True),
            (Path("memory/kb/projects/"), True),
        ],
    )
    def test_exception_directories(self, path: Path, expected: bool) -> None:
        """例外目录应该返回 True。"""
        assert is_registered_doc_dir(path) == expected

    @pytest.mark.parametrize(
        "path,expected",
        [
            (Path("memory/docs/unknown/"), False),
            (Path("memory/docs/test/"), False),
            (Path("memory/kb/test/"), False),
            (Path("memory/other/"), False),
        ],
    )
    def test_unregistered_directories(self, path: Path, expected: bool) -> None:
        """未注册目录应该返回 False。"""
        assert is_registered_doc_dir(path) == expected

    @pytest.mark.parametrize(
        "path,expected",
        [
            (Path("docs/architecture/"), False),
            (Path("docs/specs/"), False),
            (Path("src/"), False),
            (Path("/"), False),
        ],
    )
    def test_non_memory_paths(self, path: Path, expected: bool) -> None:
        """非 memory/ 路径应该返回 False。"""
        assert is_registered_doc_dir(path) == expected

    def test_subdirectory_of_registered(self) -> None:
        """注册目录的子目录应该返回 True。"""
        path = Path("memory/kb/decisions/2024/")
        assert is_registered_doc_dir(path) is True

    def test_subdirectory_of_exception(self) -> None:
        """例外目录的子目录应该返回 True。"""
        path = Path("memory/docs/archive/2023/")
        assert is_registered_doc_dir(path) is True

    def test_subdirectory_of_unregistered(self) -> None:
        """未注册目录的子目录应该返回 False。"""
        path = Path("memory/docs/unknown/subdir/")
        assert is_registered_doc_dir(path) is False


class TestExceptionDirs:
    """EXCEPTION_DIRS 常量测试。"""

    def test_has_3_exceptions(self) -> None:
        """EXCEPTION_DIRS 必须包含 3 个例外。"""
        assert len(EXCEPTION_DIRS) == 3

    def test_contains_required_exceptions(self) -> None:
        """必须包含所有必需的例外。"""
        required = {
            "memory/docs/archive/",
            "memory/docs/system/",
            "memory/kb/projects/",
        }
        assert EXCEPTION_DIRS == required
