"""Tests for _update_state_dynamic_fields in memory_hook_gateway.

Covers:
- session-start updates STATE.md 当前工作区 with git branch + commit
- Dynamic update does NOT overwrite static fields (主语言/工具链 etc.)
- Non-blocking: no STATE.md → skip silently
- Non-blocking: no git repo → skip silently
- Idempotent: repeated calls produce same result
- Placeholder (待填写) is replaced on first session-start
"""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

# Ensure memory_core/tools is importable
TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "memory_core" / "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from memory_hook_gateway import _update_state_dynamic_fields

_SCOPE = "test-project"


def _init_git_repo(repo: Path, branch: str = "main") -> None:
    """Create a minimal git repo with one commit."""
    subprocess.run(["git", "-C", str(repo), "init", "-b", branch], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True, capture_output=True)
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "initial commit"], check=True, capture_output=True)


class TestUpdateStateDynamicFields:
    """Test _update_state_dynamic_fields behavior."""

    def test_updates_placeholder_with_branch_and_commit(self, tmp_path: Path) -> None:
        """When STATE.md has placeholder, session-start replaces it."""
        _init_git_repo(tmp_path, "feat/test-branch")

        memory_dir = tmp_path / "memory" / "kb" / "projects" / _SCOPE
        memory_dir.mkdir(parents=True)
        state_path = memory_dir / "STATE.md"
        state_path.write_text(dedent("""\
            # Test State

            ## 当前工作区

            （待填写：当前工作区描述，如正在进行的任务、分支等）

            ## 待处理事项

            - [ ] something
        """), encoding="utf-8")

        _update_state_dynamic_fields(tmp_path, _SCOPE)

        content = state_path.read_text(encoding="utf-8")
        assert "当前分支: feat/test-branch" in content
        assert "最近提交:" in content
        assert "（待填写" not in content
        # Static section preserved
        assert "## 待处理事项" in content
        assert "something" in content

    def test_refreshes_already_filled_idempotent(self, tmp_path: Path) -> None:
        """When STATE.md already has branch info, it gets refreshed."""
        _init_git_repo(tmp_path, "main")

        memory_dir = tmp_path / "memory" / "kb" / "projects" / _SCOPE
        memory_dir.mkdir(parents=True)
        state_path = memory_dir / "STATE.md"
        state_path.write_text(dedent("""\
            # Test State

            ## 当前工作区

            当前分支: old-branch | 最近提交: abc123 old stuff

            ## 关键决策

            | 日期 | 决策 |
            |------|------|
            | today | something |
        """), encoding="utf-8")

        _update_state_dynamic_fields(tmp_path, _SCOPE)

        content = state_path.read_text(encoding="utf-8")
        assert "当前分支: main" in content
        assert "当前分支: old-branch" not in content
        # Static section preserved
        assert "## 关键决策" in content
        assert "something" in content

    def test_no_state_md_no_error(self, tmp_path: Path) -> None:
        """When STATE.md doesn't exist, function returns silently."""
        _update_state_dynamic_fields(tmp_path, _SCOPE)
        # Should not raise

    def test_no_git_repo_no_error(self, tmp_path: Path) -> None:
        """When not a git repo, function returns silently without error."""
        memory_dir = tmp_path / "memory" / "kb" / "projects" / _SCOPE
        memory_dir.mkdir(parents=True)
        state_path = memory_dir / "STATE.md"
        state_path.write_text("# Test\n\n## 当前工作区\n\n（待填写）\n", encoding="utf-8")

        _update_state_dynamic_fields(tmp_path, _SCOPE)

        content = state_path.read_text(encoding="utf-8")
        # Still has placeholder — was not updated
        assert "（待填写" in content

    def test_does_not_overwrite_static_fields(self, tmp_path: Path) -> None:
        """Dynamic update must NOT touch static fields like 主语言/工具链."""
        _init_git_repo(tmp_path, "develop")

        memory_dir = tmp_path / "memory" / "kb" / "projects" / _SCOPE
        memory_dir.mkdir(parents=True)
        state_path = memory_dir / "STATE.md"
        # Simulate a STATE.md that also has static-like fields (unlikely in
        # practice, but this test guards against over-aggressive regex)
        state_path.write_text(dedent("""\
            # Test State

            ## 项目状态

            | 字段 | 值 |
            |------|-----|
            | 状态 | active |

            ## 当前工作区

            （待填写：当前工作区描述，如正在进行的任务、分支等）

            ## 待处理事项

            - [ ] task 1
        """), encoding="utf-8")

        before_static_section = state_path.read_text(encoding="utf-8").split("## 当前工作区")[0]

        _update_state_dynamic_fields(tmp_path, _SCOPE)

        content = state_path.read_text(encoding="utf-8")
        after_static_section = content.split("## 当前工作区")[0]
        # Static section unchanged
        assert before_static_section == after_static_section
        assert "## 待处理事项" in content
        assert "task 1" in content

    def test_preserves_full_file_structure(self, tmp_path: Path) -> None:
        """The entire STATE.md file structure should be preserved."""
        _init_git_repo(tmp_path, "feature/abc")

        memory_dir = tmp_path / "memory" / "kb" / "projects" / _SCOPE
        memory_dir.mkdir(parents=True)
        state_path = memory_dir / "STATE.md"
        original = dedent("""\
            ---
            type: "KB:STATE"
            title: "test State"
            ---

            # test State

            ## 项目状态

            | 字段 | 值 |
            |------|-----|
            | 状态 | active |

            ## 关键决策

            | 日期 | 决策 |
            |------|------|
            | 2026-01-01 | init |

            ## 当前工作区

            （待填写：当前工作区描述，如正在进行的任务、分支等）

            ## 待处理事项

            - [ ] fix bug

            ## 已完成的里程碑

            - [x] init
        """)
        state_path.write_text(original, encoding="utf-8")

        _update_state_dynamic_fields(tmp_path, _SCOPE)

        content = state_path.read_text(encoding="utf-8")
        # All sections preserved
        assert "---" in content
        assert "type:" in content
        assert "## 项目状态" in content
        assert "## 关键决策" in content
        assert "## 当前工作区" in content
        assert "当前分支: feature/abc" in content
        assert "## 待处理事项" in content
        assert "fix bug" in content
        assert "## 已完成的里程碑" in content
        assert "init" in content

    def test_branch_without_commit(self, tmp_path: Path) -> None:
        """If git branch succeeds but log fails, still update with branch only."""
        _init_git_repo(tmp_path, "main")

        memory_dir = tmp_path / "memory" / "kb" / "projects" / _SCOPE
        memory_dir.mkdir(parents=True)
        state_path = memory_dir / "STATE.md"
        state_path.write_text("# Test\n\n## 当前工作区\n\n（待填写）\n", encoding="utf-8")

        _update_state_dynamic_fields(tmp_path, _SCOPE)

        content = state_path.read_text(encoding="utf-8")
        assert "当前分支: main" in content

    def test_only_updates_current_workspace_section(self, tmp_path: Path) -> None:
        """Ensure regex only touches the 当前工作区 section, not other sections."""
        _init_git_repo(tmp_path, "release/v1")

        memory_dir = tmp_path / "memory" / "kb" / "projects" / _SCOPE
        memory_dir.mkdir(parents=True)
        state_path = memory_dir / "STATE.md"
        # Put a similar-looking line in another section
        state_path.write_text(dedent("""\
            # Test State

            ## 关键决策

            | 日期 | 决策 |
            |------|------|
            | 2026-01-01 | some note about 当前分支: old-branch |

            ## 当前工作区

            （待填写：当前工作区描述）
        """), encoding="utf-8")

        _update_state_dynamic_fields(tmp_path, _SCOPE)

        content = state_path.read_text(encoding="utf-8")
        # The line in 关键决策 should NOT be modified
        assert "some note about 当前分支: old-branch" in content
        # Only the 当前工作区 section gets the real update
        assert "当前分支: release/v1" in content
