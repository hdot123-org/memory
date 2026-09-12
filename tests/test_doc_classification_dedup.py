"""INFRA-1050 回归测试：文档分类路径校验去重。

scripts/check_doc_classification.py::_is_in_registered_dir() 移除了自带的
DOC_CATEGORIES/EXCEPTION_DIRS 前缀匹配副本，改为委托共享路由函数
memory_core.tools.doc_router.is_registered_doc_dir()。本文件钉住去重后的
行为契约，防止两个入口再次分叉：

- _is_in_registered_dir：注册目录 / 例外目录 / 顶层例外文件 / 未注册目录
- is_registered_doc_dir：绝对路径 / 相对路径（有无尾斜杠）/ 仓库外路径
- 两个入口对同一文件路径给出一致判定
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_core.tools.doc_router import (
    DOC_CATEGORIES,
    EXCEPTION_DIRS,
    REPO_ROOT,
    is_registered_doc_dir,
)
from tests.script_module_helpers import load_script_module

SCRIPT_PATH = REPO_ROOT / "scripts" / "check_doc_classification.py"

_mod = load_script_module(SCRIPT_PATH, "check_doc_classification_under_test")
_is_in_registered_dir = _mod._is_in_registered_dir
TOP_LEVEL_EXCEPTIONS = _mod.TOP_LEVEL_EXCEPTIONS


class TestScriptIsInRegisteredDir:
    """scripts/check_doc_classification.py::_is_in_registered_dir 契约。"""

    @pytest.mark.parametrize("registered_dir", sorted(DOC_CATEGORIES.values()))
    def test_file_in_registered_category_dir(self, registered_dir: str) -> None:
        """注册分类目录下的文件应该放行。"""
        assert _is_in_registered_dir(REPO_ROOT / registered_dir / "example.md") is True

    @pytest.mark.parametrize("exception_dir", sorted(EXCEPTION_DIRS))
    def test_file_in_exception_dir(self, exception_dir: str) -> None:
        """例外目录下的文件应该放行。"""
        assert _is_in_registered_dir(REPO_ROOT / exception_dir / "example.md") is True

    @pytest.mark.parametrize("top_level_file", sorted(TOP_LEVEL_EXCEPTIONS))
    def test_top_level_exception_file(self, top_level_file: str) -> None:
        """扫描根顶层例外文件（INDEX.md 等）应该放行。"""
        assert _is_in_registered_dir(REPO_ROOT / top_level_file) is True

    def test_top_level_exception_not_covered_by_prefix(self) -> None:
        """顶层例外文件不在任何注册目录前缀内，只靠 TOP_LEVEL_EXCEPTIONS 放行。"""
        rel = sorted(TOP_LEVEL_EXCEPTIONS)[0]
        assert is_registered_doc_dir(Path(rel)) is False

    def test_file_in_unregistered_dir(self) -> None:
        """未注册目录下的文件应该被拒绝。"""
        file_path = REPO_ROOT / "memory/docs/not-a-registered-category/example.md"
        assert _is_in_registered_dir(file_path) is False

    def test_sibling_dir_prefix_not_matched(self) -> None:
        """plans-extra 与 plans 仅前缀相似，尾斜杠语义必须排除兄弟目录。"""
        file_path = REPO_ROOT / "memory/docs/plans-extra/example.md"
        assert _is_in_registered_dir(file_path) is False


class TestSharedIsRegisteredDocDir:
    """memory_core.tools.doc_router.is_registered_doc_dir 共享契约。"""

    def test_absolute_path_in_registered_dir(self) -> None:
        """REPO_ROOT 下注册目录的绝对路径 → True。"""
        assert is_registered_doc_dir(REPO_ROOT / "memory/kb/decisions/D-001.md") is True

    def test_absolute_path_in_exception_dir(self) -> None:
        """REPO_ROOT 下例外目录的绝对路径 → True。"""
        assert is_registered_doc_dir(REPO_ROOT / "memory/kb/global/truth-model.md") is True

    def test_absolute_path_in_unregistered_dir(self) -> None:
        """REPO_ROOT 下未注册目录的绝对路径 → False。"""
        path = REPO_ROOT / "memory/docs/not-a-registered-category/x.md"
        assert is_registered_doc_dir(path) is False

    def test_absolute_path_outside_repo_root(self, tmp_path: Path) -> None:
        """仓库外绝对路径（relative_to 抛 ValueError）→ False。"""
        assert is_registered_doc_dir(tmp_path / "memory/kb/decisions/D-001.md") is False

    def test_relative_dir_without_trailing_slash(self) -> None:
        """相对目录路径缺尾斜杠时应该自动补齐 → True。"""
        assert is_registered_doc_dir(Path("memory/kb/lessons")) is True

    def test_relative_dir_with_trailing_slash(self) -> None:
        """带尾斜杠的相对目录路径 → True。"""
        assert is_registered_doc_dir(Path("memory/kb/lessons/")) is True

    def test_relative_file_path(self) -> None:
        """相对文件路径（无尾斜杠）应该匹配父目录前缀 → True。"""
        assert is_registered_doc_dir(Path("memory/docs/runbooks/rb-001.md")) is True

    def test_relative_path_outside_registered_dirs(self) -> None:
        """不属于任何注册目录的相对路径 → False。"""
        assert is_registered_doc_dir(Path("memory/docs/not-a-registered-category/x.md")) is False


class TestDedupEquivalence:
    """去重核心：脚本入口与共享路由函数对同一文件判定一致（INFRA-1050）。"""

    @pytest.mark.parametrize(
        ("rel_path", "expected"),
        [
            ("memory/kb/decisions/D-001.md", True),
            ("memory/docs/plans/P-001.md", True),
            ("memory/kb/global/truth-model.md", True),
            ("memory/docs/archive/old.md", True),
            ("memory/docs/not-a-registered-category/x.md", False),
            ("memory/docs/plans-extra/x.md", False),
        ],
    )
    def test_both_entries_agree(self, rel_path: str, expected: bool) -> None:
        """脚本入口（绝对路径）与共享函数（相对路径）判定一致。"""
        assert _is_in_registered_dir(REPO_ROOT / rel_path) is expected
        assert is_registered_doc_dir(Path(rel_path)) is expected
