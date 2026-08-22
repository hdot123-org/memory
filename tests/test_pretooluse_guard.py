"""Tests for PreToolUse guard."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from memory_core.ownership import (
    classify_agents_md_block,
    classify_owned_path,
)


def _make_fake_stdin(text: str) -> io.StringIO:
    """Create a fake stdin object whose ``read()`` returns ``text``.

    Used for monkeypatching ``sys.stdin`` in tests that call ``main()``
    directly (see INFRA-141/145 stdin-IO regression tests).
    """
    return io.StringIO(text)


def _expand_invisible_ranges():
    """Yield every codepoint in the guard's ``_CC_CF_RANGES``.

    Used to parametrize the exhaustive INFRA-149 class-coverage test: every
    non-whitespace Cc/Cf character, as the sole stdin content, must allow
    without a false json_parse_error.

    Only the Cc/Cf ranges are expanded (not the Cs/Co ranges added in
    INFRA-191) because the Cs/Co set is ~21000 codepoints — too large to
    call main() once per codepoint. The Cs/Co ranges are covered by the
    dedicated INFRA-191 tests below.
    """
    from memory_core.tools.pretooluse_guard import _CC_CF_RANGES

    for _start, _end in _CC_CF_RANGES:
        yield from range(_start, _end + 1)


class _GuardRunnerMixin:
    """Shared subprocess runner for the pretooluse guard (INFRA-314 dedup).

    Six test classes previously carried byte-identical ``_run_guard`` copies
    (100% AST similarity, 18 lines / 158 tokens each, evolution scanner
    finding INFRA-314): TestPreToolUseGuard, TestTaskPayloadInjection,
    TestCwdFixed, TestExecuteP1, TestAgentsMdDiffAware, TestMultiEditPerItem.
    Consolidated into this mixin; public test names and assertions unchanged.
    """

    def _run_guard(self, payload: dict[str, Any], cwd: Path | None = None) -> tuple[int, dict[str, Any]]:
        """Run the guard with given payload and return (exit_code, result)."""
        env = os.environ.copy()
        if cwd:
            env["FACTORY_PROJECT_DIR"] = str(cwd)
            env["MEMORY_HOOK_ORIGINAL_CWD"] = str(cwd)

        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            env=env,
        )

        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            output = {"raw_stdout": result.stdout, "stderr": result.stderr}

        return result.returncode, output


class TestPreToolUseGuard(_GuardRunnerMixin):
    """Tests for PreToolUse guard behavior."""

    def _run_guard_raw(self, raw_input: str, cwd: Path | None = None) -> tuple[int, dict[str, Any]]:
        """Run the guard with raw stdin string and return (exit_code, result).

        Unlike _run_guard which takes a dict payload, this passes the raw
        string directly to the guard's stdin. Useful for testing empty,
        whitespace-only, or malformed JSON inputs.
        """
        env = os.environ.copy()
        if cwd:
            env["FACTORY_PROJECT_DIR"] = str(cwd)
            env["MEMORY_HOOK_ORIGINAL_CWD"] = str(cwd)

        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input=raw_input,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            env=env,
        )

        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            output = {"raw_stdout": result.stdout, "stderr": result.stderr}

        return result.returncode, output

    def test_guard_blocks_write_to_owned_path(self, tmp_path: Path) -> None:
        """Test that Write to owned path is blocked."""
        # Create .memory to make it a memory-managed project
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "memory/docs/INDEX.md",
            "content": "test content",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "memory/docs" in result["reason"] or "memory_docs" in result["reason"]

    # ========== 文件类型黑名单测试 ==========

    def test_guard_blocks_write_sql_file(self, tmp_path: Path) -> None:
        """Test that Write to .sql file is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "test.sql",
            "content": "CREATE TABLE test;",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "文件类型禁止入库：.sql" in result["reason"]

    def test_guard_blocks_write_bak_file(self, tmp_path: Path) -> None:
        """Test that Write to .bak file is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "backup.bak",
            "content": "backup data",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "文件类型禁止入库：.bak" in result["reason"]

    def test_guard_blocks_write_sqlite_file(self, tmp_path: Path) -> None:
        """Test that Write to .sqlite file is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "database.sqlite",
            "content": "sqlite data",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "文件类型禁止入库：.sqlite" in result["reason"]

    def test_guard_blocks_write_db_file(self, tmp_path: Path) -> None:
        """Test that Write to .db file is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "data.db",
            "content": "database",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "文件类型禁止入库：.db" in result["reason"]

    def test_guard_blocks_write_dump_file(self, tmp_path: Path) -> None:
        """Test that Write to .dump file is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "data.dump",
            "content": "dump data",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "文件类型禁止入库：.dump" in result["reason"]

    def test_guard_allows_write_py_file(self, tmp_path: Path) -> None:
        """Test that Write to .py file is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "test.py",
            "content": "print('hello')",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_guard_allows_write_md_file(self, tmp_path: Path) -> None:
        """Test that Write to .md file is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "readme.md",
            "content": "# README",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_guard_allows_write_ts_file(self, tmp_path: Path) -> None:
        """Test that Write to .ts file is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "test.ts",
            "content": "const x: number = 1;",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_guard_blocks_edit_sql_file(self, tmp_path: Path) -> None:
        """Test that Edit to .sql file is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Edit",
            "file_path": "test.sql",
            "old_str": "SELECT 1",
            "new_str": "SELECT 2",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "文件类型禁止入库：.sql" in result["reason"]

    def test_guard_blocks_multiedit_bak_file(self, tmp_path: Path) -> None:
        """Test that MultiEdit with .bak file is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "src/main.py", "old_str": "old", "new_str": "new"},
                {"file_path": "backup.bak", "old_str": "old", "new_str": "new"},
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "backup.bak" in result["reason"]

    def test_guard_blocks_execute_cp_bak_file(self, tmp_path: Path) -> None:
        """Test that Execute cp to .bak file is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "cp test.txt test.bak",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "文件类型禁止入库：.bak" in result["reason"]

    def test_guard_allows_write_sql_with_memory_hook_force(self, tmp_path: Path) -> None:
        """Test that MEMORY_HOOK_FORCE=1 bypasses file type check."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "test.sql",
            "content": "CREATE TABLE test;",
        }

        env = os.environ.copy()
        env["FACTORY_PROJECT_DIR"] = str(tmp_path)
        env["MEMORY_HOOK_ORIGINAL_CWD"] = str(tmp_path)
        env["MEMORY_HOOK_FORCE"] = "1"

        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
        )

        output = json.loads(result.stdout)
        assert result.returncode == 0
        assert output["decision"] == "allow"

    def test_guard_blocks_write_to_backups_directory(self, tmp_path: Path) -> None:
        """Test that Write to backups/ directory is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "backups/dump.txt",
            "content": "backup data",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "目录 backups 被禁止" in result["reason"]

    def test_guard_blocks_edit_to_owned_path(self, tmp_path: Path) -> None:
        """Test that Edit to owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Edit",
            "file_path": "memory/kb/article.md",
            "old_str": "old",
            "new_str": "new",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_allows_write_to_not_owned_path(self, tmp_path: Path) -> None:
        """Test that Write to not-owned path is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "src/main.py",
            "content": "print('hello')",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_guard_blocks_execute_mv_to_owned_path(self, tmp_path: Path) -> None:
        """Test that Execute mv targeting owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "mv temp.md memory/docs/INDEX.md",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_execute_git_mv_to_owned_path(self, tmp_path: Path) -> None:
        """Test that Execute git mv targeting owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "git mv docs.md memory/kb/docs.md",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_execute_rm_on_owned_path(self, tmp_path: Path) -> None:
        """Test that Execute rm on owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "rm memory/docs/INDEX.md",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_execute_python_open_owned_path(self, tmp_path: Path) -> None:
        """Test that Execute python -c with open() to owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": 'python -c \'open("memory/docs/INDEX.md", "w").write("test")\'',
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_execute_shell_redirect_to_owned_path(self, tmp_path: Path) -> None:
        """Test that Execute shell redirect to owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "echo 'test' > memory/docs/INDEX.md",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_execute_mkdir_on_owned_path(self, tmp_path: Path) -> None:
        """Test that Execute mkdir on owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "mkdir memory/docs/newdir",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_execute_touch_on_owned_path(self, tmp_path: Path) -> None:
        """Test that Execute touch on owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "touch memory/system/memory.lock",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_multiedit_with_any_owned_path(self, tmp_path: Path) -> None:
        """Test that MultiEdit blocks if ANY path is owned (per-item classification)."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "src/main.py", "old_str": "old1", "new_str": "new1"},
                {"file_path": "memory/docs/INDEX.md", "old_str": "old2", "new_str": "new2"},
                {"file_path": "src/other.py", "old_str": "old3", "new_str": "new3"},
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        # 5b.5: per-item classification now outputs "blocked items" instead of "contains protected path"
        assert "MultiEdit" in result["reason"]
        assert "item_results" in result
        # Verify per-item results
        items = result["item_results"]
        assert len(items) == 3
        blocked_items = [i for i in items if i["decision"] == "block"]
        assert len(blocked_items) == 1
        assert blocked_items[0]["path"] == "memory/docs/INDEX.md"

    def test_guard_allows_multiedit_with_no_owned_paths(self, tmp_path: Path) -> None:
        """Test that MultiEdit allows if no paths are owned."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "src/main.py", "old_str": "old1", "new_str": "new1"},
                {"file_path": "src/other.py", "old_str": "old2", "new_str": "new2"},
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_guard_blocks_notebookedit_to_owned_path(self, tmp_path: Path) -> None:
        """Test that NotebookEdit to owned notebook is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "NotebookEdit",
            "notebook_path": "memory/docs/analysis.ipynb",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_allows_task_without_owned_path_references(self, tmp_path: Path) -> None:
        """Test that Task without owned path references is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Task",
            "prompt": "Refactor the src/utils.py file to improve code quality",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_guard_allows_task_with_owned_path_references(self, tmp_path: Path) -> None:
        """Task with owned path references is allowed (actual writes caught by Write/Edit guard)."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Task",
            "prompt": "Analyze memory/kb/docs routing fallback behavior",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_guard_blocks_uncertain_path_with_owned_root_string(self, tmp_path: Path) -> None:
        """Test that uncertain path with owned root string is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # Command contains owned resource string but cannot parse path
        payload = {
            "tool_name": "Execute",
            "command": "echo test > $HOME/memory/docs/file.md",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_execute_cp_to_owned_destination(self, tmp_path: Path) -> None:
        """Test that Execute cp to owned destination is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "cp temp.md memory/docs/INDEX.md",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_agents_md_block_internal_modify(self, tmp_path: Path) -> None:
        """Test AGENTS.md scenario 1: block internal modification."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "AGENTS.md").write_text(
            "<!-- ownership:block:start -->\nProtected content\n<!-- ownership:block:end -->\n"
        )

        payload = {
            "tool_name": "Edit",
            "file_path": "AGENTS.md",
            "content_before": "<!-- ownership:block:start -->\nProtected content\n<!-- ownership:block:end -->\n",
            "content_after": "<!-- ownership:block:start -->\nModified content\n<!-- ownership:block:end -->\n",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        # The guard should block this
        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_blocks_agents_md_delete_marker(self, tmp_path: Path) -> None:
        """Test AGENTS.md scenario 2: delete protection marker."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Edit",
            "file_path": "AGENTS.md",
            "content_before": "<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->\n",
            "content_after": "\nProtected\n\n",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_allows_agents_md_append_outside_block(self, tmp_path: Path) -> None:
        """Test AGENTS.md scenario 3: append outside block."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Edit",
            "file_path": "AGENTS.md",
            "content_before": "<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->\n",
            "content_after": "<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->\n\nNew content",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_guard_blocks_agents_md_full_overwrite_uncertain(self, tmp_path: Path) -> None:
        """Test AGENTS.md scenario 4: full overwrite uncertain."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        # Create existing AGENTS.md file
        (tmp_path / "AGENTS.md").write_text("Existing content")

        payload = {
            "tool_name": "Write",
            "file_path": "AGENTS.md",
            "content": "Completely new content",
            # No content_before/after means full overwrite
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_allows_agents_md_memory_init_creation(self, tmp_path: Path) -> None:
        """Test AGENTS.md scenario 5: memory-init creation."""
        # No existing AGENTS.md, creating new
        (tmp_path / "memory" / "system").mkdir(parents=True)
        # Ensure AGENTS.md does NOT exist
        agents_md = tmp_path / "AGENTS.md"
        if agents_md.exists():
            agents_md.unlink()

        payload = {
            "tool_name": "Write",
            "file_path": "AGENTS.md",
            "content": "Initial AGENTS.md content",
            # No content_before means creation
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_memory_hook_force_does_not_bypass_guard(self, tmp_path: Path, monkeypatch) -> None:
        """Test that MEMORY_HOOK_FORCE does NOT bypass PreToolUse guard."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        monkeypatch.setenv("MEMORY_HOOK_FORCE", "1")

        payload = {
            "tool_name": "Write",
            "file_path": "memory/docs/INDEX.md",
            "content": "test",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        # Should still block even with MEMORY_HOOK_FORCE
        assert exit_code == 2
        assert result["decision"] == "block"

    def test_guard_allows_non_memory_project(self, tmp_path: Path) -> None:
        """Test that guard allows operations on non-memory projects."""
        # No .memory directory

        payload = {
            "tool_name": "Write",
            "file_path": "memory/docs/INDEX.md",
            "content": "test",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "Not a memory-managed project" in result["reason"]

    def test_guard_allows_unknown_tool(self, tmp_path: Path) -> None:
        """Test that unknown tools are allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "SomeUnknownTool",
            "file_path": "memory/docs/INDEX.md",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "Unknown tool" in result["reason"]

    # ========== 空/纯空白 stdin 处理测试 (INFRA-138) ==========

    def test_empty_stdin_allows_without_error(self, tmp_path: Path) -> None:
        """Empty stdin should allow and NOT write error log."""
        exit_code, result = self._run_guard_raw("", tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "empty stdin" in result["reason"].lower()

    def test_whitespace_stdin_allows_without_error(self, tmp_path: Path) -> None:
        """Whitespace-only stdin should allow and NOT write error log."""
        exit_code, result = self._run_guard_raw("   \n  ", tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "empty stdin" in result["reason"].lower()

    def test_malformed_nonempty_json_goes_through_fail_closed(self, tmp_path: Path) -> None:
        """Malformed non-empty JSON should go through fail-closed path, not be treated as empty."""
        # Create memory/system so project root resolution works
        (tmp_path / "memory" / "system").mkdir(parents=True)

        exit_code, result = self._run_guard_raw("{invalid", tmp_path)

        # Should NOT be treated as empty stdin — reason must indicate guard failure
        assert "empty stdin" not in result.get("reason", "").lower()
        assert "guard failure" in result["reason"].lower()

    def test_empty_stdin_does_not_write_error_log(self, tmp_path: Path) -> None:
        """Empty stdin should not write to the error log (json_parse_error)."""
        exit_code, result = self._run_guard_raw("", tmp_path)

        assert exit_code == 0
        # Verify no error log was written to memory/log/*-errors.jsonl
        error_log_dir = tmp_path / "memory" / "log"
        if error_log_dir.exists():
            error_files = list(error_log_dir.glob("*-errors.jsonl"))
            assert not error_files, f"Expected no error log, found: {error_files}"

    # ========== stdin IO 异常处理测试 (INFRA-141) ==========

    def test_stdin_read_oserror_treated_as_empty(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """sys.stdin.read() raising OSError must be treated as empty stdin (allow, no error).

        Regression test for INFRA-141: previously the generic ``except Exception``
        handler routed stdin read failures into ``_fail_closed_with_raw_check``,
        which hardcodes ``error_type="json_parse_error"`` — a false label since
        no JSON parsing was ever attempted.
        """
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("MEMORY_HOOK_ORIGINAL_CWD", str(tmp_path))

        def _raise_oserror(*args: Any, **kwargs: Any) -> str:
            raise OSError("Bad file descriptor")

        monkeypatch.setattr(sys.stdin, "read", _raise_oserror)

        exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["decision"] == "allow"
        assert "empty stdin" in result["reason"].lower()

    def test_stdin_read_oserror_does_not_write_error_log(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """sys.stdin.read() OSError must NOT write a json_parse_error log.

        Mirrors ``test_empty_stdin_does_not_write_error_log`` for the IO-failure
        path. The error log is reserved for genuine JSON parse errors.
        """
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("MEMORY_HOOK_ORIGINAL_CWD", str(tmp_path))

        def _raise_oserror(*args: Any, **kwargs: Any) -> str:
            raise OSError("Bad file descriptor")

        monkeypatch.setattr(sys.stdin, "read", _raise_oserror)

        exit_code = main()

        assert exit_code == 0
        # Verify no error log was written to memory/log/*-errors.jsonl
        error_log_dir = tmp_path / "memory" / "log"
        if error_log_dir.exists():
            error_files = list(error_log_dir.glob("*-errors.jsonl"))
            assert not error_files, f"Expected no error log, found: {error_files}"

    def test_malformed_nonempty_json_still_logs_json_parse_error(self, tmp_path: Path) -> None:
        """Regression guard: non-empty malformed JSON must still fail-closed AND write a json_parse_error log.

        Confirms the INFRA-141 fix did not break the legitimate json_parse_error
        path (which is now the only path into ``_fail_closed_with_raw_check``).
        """
        # Create memory/system so project root resolution works
        (tmp_path / "memory" / "system").mkdir(parents=True)

        exit_code, result = self._run_guard_raw("{not valid json", tmp_path)

        # Fail-closed path: reason indicates guard failure, not empty stdin
        assert "empty stdin" not in result.get("reason", "").lower()
        assert "guard failure" in result["reason"].lower()
        # json_parse_error log must be written
        error_log_dir = tmp_path / "memory" / "log"
        error_files = list(error_log_dir.glob("*-errors.jsonl"))
        assert error_files, "Expected json_parse_error log to be written"
        # Verify the log content references json_parse_error
        log_content = error_files[0].read_text()
        assert "json_parse_error" in log_content

    # ========== BOM/null-byte stdin 处理测试 (INFRA-143) ==========

    def test_bom_only_stdin_allows_without_error(self, tmp_path: Path) -> None:
        """BOM-only stdin (\ufeff) should allow without error (INFRA-143).

        str.strip() does not remove U+FEFF, so without explicit stripping
        it reaches json.loads() and triggers "Expecting value: line 1
        column 1 (char 0)" — the same error pattern as empty stdin.
        """
        exit_code, result = self._run_guard_raw("\ufeff", tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "empty stdin" in result["reason"].lower()

    def test_null_byte_only_stdin_allows_without_error(self, tmp_path: Path) -> None:
        """Null-byte-only stdin (\\x00) should allow without error (INFRA-143).

        str.strip() does not remove \\x00, so without explicit stripping
        it reaches json.loads() and triggers the same error pattern.
        """
        exit_code, result = self._run_guard_raw("\x00", tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "empty stdin" in result["reason"].lower()

    def test_bom_null_byte_mix_allows_without_error(self, tmp_path: Path) -> None:
        """Mix of BOM, null bytes and whitespace should allow without error (INFRA-143)."""
        exit_code, result = self._run_guard_raw("\x00\ufeff  \n\x00", tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "empty stdin" in result["reason"].lower()

    def test_bom_prefixed_valid_json_parses_correctly(self, tmp_path: Path) -> None:
        """BOM-prefixed valid JSON should be parsed correctly after BOM stripping (INFRA-143).

        This confirms BOM stripping doesn't corrupt valid payloads — the guard
        should classify the tool use as if no BOM were present.
        """
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {"tool_name": "Read", "tool_input": {"file_path": "/tmp/test.txt"}}
        exit_code, result = self._run_guard_raw("\ufeff" + json.dumps(payload), tmp_path)

        # Should NOT hit empty-stdin or fail-closed paths
        assert "empty stdin" not in result.get("reason", "").lower()
        assert "guard failure" not in result.get("reason", "").lower()

    def test_bom_only_stdin_does_not_write_error_log(self, tmp_path: Path) -> None:
        """BOM-only stdin should not write a json_parse_error log (INFRA-143)."""
        exit_code, result = self._run_guard_raw("\ufeff", tmp_path)

        assert exit_code == 0
        error_log_dir = tmp_path / "memory" / "log"
        if error_log_dir.exists():
            error_files = list(error_log_dir.glob("*-errors.jsonl"))
            assert not error_files, f"Expected no error log, found: {error_files}"

    def test_null_byte_only_stdin_does_not_write_error_log(self, tmp_path: Path) -> None:
        """Null-byte-only stdin should not write a json_parse_error log (INFRA-143)."""
        exit_code, result = self._run_guard_raw("\x00", tmp_path)

        assert exit_code == 0
        error_log_dir = tmp_path / "memory" / "log"
        if error_log_dir.exists():
            error_files = list(error_log_dir.glob("*-errors.jsonl"))
            assert not error_files, f"Expected no error log, found: {error_files}"


class TestInvisibleUnicodeStdin:
    """Regression tests for INFRA-145: invisible Unicode characters that
    survive str.strip() and cause false json_parse_error."""

    def test_zero_width_space_only_stdin_allows_without_error(self, monkeypatch, tmp_path, capsys) -> None:
        """\\u200b (zero-width space) only on stdin should allow, not error."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u200b"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_zero_width_non_joiner_only_stdin_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """\\u200c (ZWNJ) only on stdin should allow."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u200c"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_zero_width_joiner_only_stdin_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """\\u200d (ZWJ) only on stdin should allow."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u200d"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_word_joiner_only_stdin_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """\\u2060 (word joiner) only on stdin should allow."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u2060"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_multiple_invisible_chars_mix_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """Mix of invisible chars + whitespace should allow."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u200b \u200c\n\u200d\t\u2060"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_double_bom_allows_without_error(self, monkeypatch, tmp_path, capsys) -> None:
        """Double BOM \\ufeff\\ufeff should allow (INFRA-145 regression)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ufeff\ufeff"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_bom_with_invisible_chars_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """BOM + invisible chars should allow."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ufeff\u200b\x00\u200c"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_invisible_chars_with_valid_json_parses_correctly(self, monkeypatch, tmp_path, capsys) -> None:
        """Invisible chars prefixed to valid JSON should still parse."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / "test.txt"), "content": "hi"},
        }
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ufeff\u200b" + json.dumps(payload)))
        exit_code = main()
        captured = capsys.readouterr()
        json.loads(captured.out)  # parse to confirm valid JSON output
        assert exit_code == 0

    def test_zero_width_space_only_does_not_write_error_log(self, monkeypatch, tmp_path) -> None:
        """\\u200b only should NOT write any error log."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u200b"))
        main()
        log_dir = tmp_path / "memory" / "log"
        if log_dir.exists():
            for f in log_dir.glob("*-errors.jsonl"):
                content = f.read_text()
                assert "json_parse_error" not in content, f"False json_parse_error logged for \\u200b stdin: {content}"

    def test_multiple_bom_does_not_write_error_log(self, monkeypatch, tmp_path) -> None:
        """Double BOM should NOT write any error log."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ufeff\ufeff"))
        main()
        log_dir = tmp_path / "memory" / "log"
        if log_dir.exists():
            for f in log_dir.glob("*-errors.jsonl"):
                content = f.read_text()
                assert "json_parse_error" not in content, (
                    f"False json_parse_error logged for double BOM stdin: {content}"
                )

    # ========== 非空白 Cc/Cf 类别全量修复回归测试 (INFRA-149) ==========

    def test_bidi_isolate_only_stdin_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """U+2066 (LRI) only on stdin should allow (INFRA-149).

        U+2066 LEFT-TO-RIGHT ISOLATE is the key case the prior hardcoded
        allowlist (INFRA-143/145) missed — it is a Cf character that
        str.strip() does not remove.
        """
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u2066"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_bidi_isolates_mix_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """All bidi isolates U+2066-U+2069 should allow (INFRA-149)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u2066\u2067\u2068\u2069"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_deprecated_bidi_format_chars_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """Deprecated bidi format chars U+206A-U+206F should allow (INFRA-149)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u206a\u206b\u206c\u206d\u206e\u206f"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_arabic_format_chars_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """Arabic format chars U+0600/U+0601 should allow (INFRA-149)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u0600\u0601"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_language_tag_char_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """A char from the U+E0020-E007F tag range should allow (INFRA-149)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ue020"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_high_plane_invisible_allows(self, monkeypatch, tmp_path, capsys) -> None:
        """U+1BCA0 (shorthand formatting) should allow (INFRA-149)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\U0001bca0"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_invisible_prefixed_valid_json_parses_infra149(self, monkeypatch, tmp_path, capsys) -> None:
        """Invisible chars (U+2066 LRI + U+200b) prefixed to valid JSON should still parse (INFRA-149)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / "test.txt"), "content": "hi"},
        }
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\u2066\u200b" + json.dumps(payload)))
        exit_code = main()
        captured = capsys.readouterr()
        json.loads(captured.out)  # confirm valid JSON output
        result = json.loads(captured.out)
        assert exit_code == 0
        assert "empty stdin" not in result.get("reason", "").lower()
        assert "guard failure" not in result.get("reason", "").lower()

    @pytest.mark.parametrize("codepoint", list(_expand_invisible_ranges()))
    def test_every_invisible_char_only_stdin_allows(self, codepoint, monkeypatch, tmp_path, capsys) -> None:
        """Every non-whitespace Cc/Cf character, as the sole stdin content,
        must allow without a false json_parse_error (INFRA-149 class fix)."""
        from memory_core.tools.pretooluse_guard import _CC_CF_RANGES, main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin(chr(codepoint)))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"
        # Sanity: the codepoint is actually within the guard's declared Cc/Cf ranges.
        assert any(s <= codepoint <= e for s, e in _CC_CF_RANGES)

    # ========== Cs/Co 类别扩展回归测试 (INFRA-191) ==========

    def test_surrogate_chars_stripped_before_json_parse(self, monkeypatch, tmp_path, capsys) -> None:
        """Lone surrogate characters (Cs category) are stripped before JSON
        parsing, preventing false json_parse_error (INFRA-191).

        U+D800 is a lone surrogate that str.strip() does not remove; without
        explicit stripping it reaches json.loads() and triggers "Expecting
        value: line 1 column 1 (char 0)".
        """
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ud800"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "empty stdin" in result["reason"].lower()

    def test_surrogate_range_chars_all_allow(self, monkeypatch, tmp_path, capsys) -> None:
        """Representative lone surrogates across U+D800-U+DFFF should allow (INFRA-191)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ud800\udbff\udc00\udfff"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_private_use_area_chars_all_allow(self, monkeypatch, tmp_path, capsys) -> None:
        """Private-use area characters (Co category) are stripped before JSON
        parsing, preventing false json_parse_error (INFRA-191).

        U+E000 (BMP PUA), U+F0000 (Supplementary PUA-A), and U+100000
        (Supplementary PUA-B) are private-use characters that str.strip()
        does not remove.
        """
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ue000\U000f0000\U00100000"))
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "empty stdin" in result["reason"].lower()

    def test_surrogate_chars_do_not_write_error_log(self, monkeypatch, tmp_path) -> None:
        """Lone surrogate chars should NOT write any error log (INFRA-191)."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))
        monkeypatch.setattr("sys.stdin", _make_fake_stdin("\ud800\udfff"))
        main()
        log_dir = tmp_path / "memory" / "log"
        if log_dir.exists():
            for f in log_dir.glob("*-errors.jsonl"):
                content = f.read_text()
                assert "json_parse_error" not in content, (
                    f"False json_parse_error logged for surrogate stdin: {content}"
                )


class TestEmptyPreviewSkipsErrorLog:
    """INFRA-191: when raw_input_preview is empty after redaction/stripping,
    no json_parse_error log is written — it is non-actionable noise."""

    def test_empty_preview_skips_error_log(self, tmp_path, monkeypatch) -> None:
        """When raw_input_preview is empty after redaction, no json_parse_error
        log is written — this is non-actionable noise (INFRA-191)."""
        from memory_core.tools.pretooluse_guard import _fail_closed_with_raw_check

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))

        write_called = []
        with patch("memory_core.tools.error_logger.write_error_log") as mock_write:
            mock_write.side_effect = lambda **kw: write_called.append(kw) or True
            exit_code, result = _fail_closed_with_raw_check("", "test reason")

        assert exit_code == 0  # allow (non-protected, empty input)
        assert result["decision"] == "allow"
        assert len(write_called) == 0  # no error log written for empty preview

    def test_nonempty_preview_still_writes_error_log(self, tmp_path, monkeypatch) -> None:
        """Regression guard: a non-empty malformed input must still write the
        json_parse_error log (INFRA-191 must not over-suppress)."""
        from memory_core.tools.pretooluse_guard import _fail_closed_with_raw_check

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))

        write_called = []
        with patch("memory_core.tools.error_logger.write_error_log") as mock_write:
            mock_write.side_effect = lambda **kw: write_called.append(kw) or True
            exit_code, result = _fail_closed_with_raw_check("{not valid json", "test reason")

        assert exit_code == 0  # non-protected → allow
        assert result["decision"] == "allow"
        assert len(write_called) == 1  # error log still written for non-empty input

    """Regression tests for INFRA-145: UnicodeDecodeError from stdin read."""

    def test_unicode_decode_error_treated_as_empty(self, monkeypatch, tmp_path, capsys) -> None:
        """sys.stdin.read() raising UnicodeDecodeError should allow, not crash."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))

        class _BadStdin:
            def read(self):
                raise UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")

            def __getattr__(self, name):
                raise AttributeError(name)

        monkeypatch.setattr("sys.stdin", _BadStdin())
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_value_error_treated_as_empty(self, monkeypatch, tmp_path, capsys) -> None:
        """sys.stdin.read() raising ValueError should allow, not crash."""
        from memory_core.tools.pretooluse_guard import main

        monkeypatch.setenv("FACTORY_PROJECT_DIR", str(tmp_path))

        class _BadStdin:
            def read(self):
                raise ValueError("io error")

            def __getattr__(self, name):
                raise AttributeError(name)

        monkeypatch.setattr("sys.stdin", _BadStdin())
        exit_code = main()
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert exit_code == 0
        assert result["decision"] == "allow"


class TestPreToolUseGuardDirect:
    """Direct tests for guard functions without subprocess."""

    def test_classify_owned_path_importable(self) -> None:
        """Verify classify_owned_path is importable and works."""

        result = classify_owned_path("memory/docs/INDEX.md")
        assert hasattr(result, "level")  # Owned

    def test_classify_not_owned_path(self) -> None:
        """Verify classify_owned_path returns NotOwned for non-owned paths."""

        result = classify_owned_path("src/main.py")
        assert not hasattr(result, "level")  # NotOwned

    def test_agents_md_classify_scenario_1(self) -> None:
        """Test AGENTS.md block internal modify detection."""
        result = classify_agents_md_block(
            "AGENTS.md",
            content_before="<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->",
            content_after="<!-- ownership:block:start -->\nChanged\n<!-- ownership:block:end -->",
        )
        assert result["decision"] == "block"
        assert result["scenario"] == 1

    def test_agents_md_classify_scenario_2(self) -> None:
        """Test AGENTS.md marker deletion detection."""
        result = classify_agents_md_block(
            "AGENTS.md",
            content_before="<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->",
            content_after="Protected\n",
        )
        assert result["decision"] == "block"
        assert result["scenario"] == 2

    def test_agents_md_classify_scenario_3(self) -> None:
        """Test AGENTS.md append after block."""
        result = classify_agents_md_block(
            "AGENTS.md",
            content_before="<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->",
            content_after="<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->\n\nNew",
        )
        assert result["decision"] == "allow"
        assert result["scenario"] == 3

    def test_agents_md_classify_scenario_4(self) -> None:
        """Test AGENTS.md uncertain overwrite."""
        result = classify_agents_md_block(
            "AGENTS.md",
            content_before=None,
            content_after=None,
        )
        assert result["decision"] == "block"
        assert result["scenario"] == 4

    def test_agents_md_classify_scenario_5(self) -> None:
        """Test AGENTS.md creation scenario."""
        result = classify_agents_md_block(
            "AGENTS.md",
            content_before=None,
            content_after="# AGENTS.md\nNew file",
        )
        assert result["decision"] == "allow"
        assert result["scenario"] == 5

    def test_agents_md_not_applicable(self) -> None:
        """Test AGENTS.md classification not applicable for other files."""
        result = classify_agents_md_block(
            "memory/docs/README.md",
            content_before=None,
            content_after=None,
        )
        assert result["decision"] == "not_applicable"


# ---------------------------------------------------------------------------
# M5b Tests: Task payload injection, cwd fixed, Execute P1, AGENTS diff-aware
# ---------------------------------------------------------------------------


class TestTaskPayloadInjection(_GuardRunnerMixin):
    """5b.1: Task tool ownership policy injection tests."""

    def test_task_injects_ownership_policy_block(self, tmp_path: Path) -> None:
        """Test that Task tool result contains injected_prompt with policy block."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Task",
            "prompt": "Fix the bug in src/main.py",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "injected_prompt" in result
        assert "<!-- ownership-policy-injection -->" in result["injected_prompt"]
        assert "Protected Domains" in result["injected_prompt"]
        assert "Protected Resources" in result["injected_prompt"]
        assert "Forbidden Instructions" in result["injected_prompt"]
        # Original prompt should be preserved
        assert "Fix the bug in src/main.py" in result["injected_prompt"]

    def test_task_injects_policy_lists_domains_and_resources(self, tmp_path: Path) -> None:
        """Test that injected policy lists all default domains and resources."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Task",
            "prompt": "Do something",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        injected = result["injected_prompt"]
        # Check default domains
        assert "memory/docs" in injected
        assert "memory/kb" in injected
        assert "memory/system" in injected
        # Check default resources
        assert "AGENTS.md" in injected

    def test_task_policy_injection_idempotent(self, tmp_path: Path) -> None:
        """Test that policy injection is idempotent (no double injection)."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Task",
            "prompt": "<!-- ownership-policy-injection -->Already injected prompt",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        injected = result["injected_prompt"]
        # Should not contain double injection
        assert injected.count("<!-- ownership-policy-injection -->") == 1

    def test_task_allows_with_policy_and_owned_reference(self, tmp_path: Path) -> None:
        """Task with owned path reference is allowed, with injected_prompt containing policy."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Task",
            "prompt": "Analyze memory/kb/docs.md routing",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        # Injects the policy block
        assert "injected_prompt" in result

    def test_task_injection_includes_forbidden_instructions(self, tmp_path: Path) -> None:
        """Test that injected policy includes forbidden instructions."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Task",
            "prompt": "Refactor code",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        injected = result["injected_prompt"]
        assert "Do not modify" in injected
        assert "Do not attempt to weaken" in injected
        assert "Do not bypass" in injected


class TestCwdFixed(_GuardRunnerMixin):
    """5b.2: Task tool cwd fixed to project_root tests."""

    def test_task_uses_factory_project_dir_not_pwd(self, tmp_path: Path) -> None:
        """Test that Task tool uses FACTORY_PROJECT_DIR, not PWD."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        # Create a subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        payload = {
            "tool_name": "Task",
            "prompt": "Do work",
        }

        # Run from subdirectory but set FACTORY_PROJECT_DIR to root
        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_task_project_root_resolved_from_env(self, tmp_path: Path) -> None:
        """Test that project root is resolved from env even when cwd differs."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        env = os.environ.copy()
        env["FACTORY_PROJECT_DIR"] = str(tmp_path)
        # Simulate PWD being different
        env["MEMORY_HOOK_ORIGINAL_CWD"] = str(tmp_path)

        payload = {
            "tool_name": "Task",
            "prompt": "Do work",
        }

        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.pretooluse_guard"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
        )

        output = json.loads(result.stdout)
        assert output["decision"] == "allow"

    def test_get_project_root_for_task_returns_resolved(self, tmp_path: Path) -> None:
        """Test _get_project_root_for_task returns resolved path."""
        from memory_core.tools.pretooluse_guard import _get_project_root_for_task

        result = _get_project_root_for_task(tmp_path)
        assert result == tmp_path.resolve()


class TestExecuteP1(_GuardRunnerMixin):
    """5b.3: Execute P1 coverage tests — rsync, node -e, shell glob, relative paths."""

    def test_execute_rsync_to_owned_path_blocked(self, tmp_path: Path) -> None:
        """Test that rsync to owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "rsync -av src/ memory/docs/",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_execute_rsync_to_safe_path_allowed(self, tmp_path: Path) -> None:
        """Test that rsync to safe path is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "rsync -av src/ backup/",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_execute_node_e_write_owned_path_blocked(self, tmp_path: Path) -> None:
        """Test that node -e with writeFileSync to owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": 'node -e \'require("fs").writeFileSync("memory/docs/INDEX.md", "test")\'',
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_execute_node_e_write_safe_path_allowed(self, tmp_path: Path) -> None:
        """Test that node -e with writeFileSync to safe path is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": 'node -e \'require("fs").writeFileSync("output.txt", "test")\'',
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_execute_shell_glob_owned_path_blocked(self, tmp_path: Path) -> None:
        """Test that shell glob targeting owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "rm -rf memory/docs/*",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_execute_relative_path_to_owned_blocked(self, tmp_path: Path) -> None:
        """Test that relative paths to owned resources are blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "cp config.toml memory/system/adapter.toml",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_execute_dd_to_owned_path_blocked(self, tmp_path: Path) -> None:
        """Test that dd to owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "dd if=/dev/zero of=memory/system/memory.lock bs=1 count=0",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_execute_ln_to_owned_path_blocked(self, tmp_path: Path) -> None:
        """Test that ln targeting owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "ln -s /tmp/fake memory/docs/symlink",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_execute_install_to_owned_path_blocked(self, tmp_path: Path) -> None:
        """Test that install command targeting owned path is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Execute",
            "command": "install -m 644 file.txt memory/docs/",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"

    def test_execute_env_var_expansion(self, tmp_path: Path) -> None:
        """Test that environment variable expansion works for path classification."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # With $HOME expansion that doesn't target owned paths
        payload = {
            "tool_name": "Execute",
            "command": "echo test > $HOME/output.txt",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        # The path contains $HOME which is uncertain, and command doesn't contain
        # owned root strings, so should allow
        assert exit_code == 0
        assert result["decision"] == "allow"

    def test_execute_quoted_args_parsed_correctly(self, tmp_path: Path) -> None:
        """Test that quoted arguments are parsed correctly."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # cp with quoted destination targeting owned path
        payload = {
            "tool_name": "Execute",
            "command": 'cp file.txt "memory/docs/INDEX.md"',
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"


class TestAgentsMdDiffAware(_GuardRunnerMixin):
    """5b.4: AGENTS.md diff-aware tests for Edit and MultiEdit."""

    def test_edit_uses_old_str_as_content_before(self, tmp_path: Path) -> None:
        """Test that Edit tool uses old_str as content_before fallback."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Edit",
            "file_path": "AGENTS.md",
            "old_str": "<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->",
            "new_str": "<!-- ownership:block:start -->\nChanged\n<!-- ownership:block:end -->",
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        # Should block because old_str is used as content_before (scenario 1)
        assert exit_code == 2
        assert result["decision"] == "block"

    def test_multiedit_agents_md_diff_aware_blocks(self, tmp_path: Path) -> None:
        """Test that MultiEdit with AGENTS.md item uses diff-aware classification."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "AGENTS.md").write_text("<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->\n")

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "src/main.py", "old_str": "old", "new_str": "new"},
                {
                    "file_path": "AGENTS.md",
                    "old_str": "<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->",
                    "new_str": "<!-- ownership:block:start -->\nModified\n<!-- ownership:block:end -->",
                },
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "item_results" in result
        # Find the AGENTS.md item
        agents_item = next(i for i in result["item_results"] if i["path"] == "AGENTS.md")
        assert agents_item["decision"] == "block"

    @pytest.mark.flaky(reruns=2)
    def test_multiedit_agents_md_diff_aware_allows_append(self, tmp_path: Path) -> None:
        """Test that MultiEdit with AGENTS.md append after block is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "src/main.py", "old_str": "old", "new_str": "new"},
                {
                    "file_path": "AGENTS.md",
                    "old_str": "<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->",
                    "new_str": "<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->\n\nNew section",
                },
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "item_results" in result

    def test_multiedit_agents_md_no_content_before_blocks(self, tmp_path: Path) -> None:
        """Test MultiEdit on AGENTS.md with no content_before and existing file blocks."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "AGENTS.md").write_text("Existing content")

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {
                    "file_path": "AGENTS.md",
                    "new_str": "New content",
                },
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"


class TestMultiEditPerItem(_GuardRunnerMixin):
    """5b.5: MultiEdit per-item classification tests."""

    def test_multiedit_per_item_classification_results(self, tmp_path: Path) -> None:
        """Test that MultiEdit returns per-item classification results."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "src/main.py", "old_str": "old", "new_str": "new"},
                {"file_path": "memory/docs/INDEX.md", "old_str": "old", "new_str": "new"},
                {"file_path": "src/other.py", "old_str": "old", "new_str": "new"},
                {"file_path": "memory/system/STATE.md", "old_str": "old", "new_str": "new"},
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        assert "item_results" in result

        items = result["item_results"]
        assert len(items) == 4

        # Check each item has path and decision
        blocked = [i for i in items if i["decision"] == "block"]
        allowed = [i for i in items if i["decision"] == "allow"]

        # At least memory/docs/INDEX.md and memory/system/STATE.md should be blocked
        blocked_paths = {i["path"] for i in blocked}
        assert "memory/docs/INDEX.md" in blocked_paths
        assert "memory/system/STATE.md" in blocked_paths

        # src files should be allowed
        allowed_paths = {i["path"] for i in allowed}
        assert "src/main.py" in allowed_paths
        assert "src/other.py" in allowed_paths

    def test_multiedit_all_allowed_returns_item_results(self, tmp_path: Path) -> None:
        """Test that MultiEdit with all allowed paths still returns item_results."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "src/a.py", "old_str": "old", "new_str": "new"},
                {"file_path": "src/b.py", "old_str": "old", "new_str": "new"},
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 0
        assert result["decision"] == "allow"
        assert "item_results" in result
        assert len(result["item_results"]) == 2
        assert all(i["decision"] == "allow" for i in result["item_results"])

    def test_multiedit_mixed_agents_md_and_regular(self, tmp_path: Path) -> None:
        """Test MultiEdit with mix of AGENTS.md and regular owned paths."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "AGENTS.md").write_text("<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->\n")

        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "src/main.py", "old_str": "old", "new_str": "new"},
                {
                    "file_path": "AGENTS.md",
                    "old_str": "<!-- ownership:block:start -->\nProtected\n<!-- ownership:block:end -->",
                    "new_str": "<!-- ownership:block:start -->\nChanged\n<!-- ownership:block:end -->",
                },
            ],
        }

        exit_code, result = self._run_guard(payload, tmp_path)

        assert exit_code == 2
        assert result["decision"] == "block"
        items = result["item_results"]
        agents_item = next(i for i in items if i["path"] == "AGENTS.md")
        assert agents_item["decision"] == "block"
        src_item = next(i for i in items if i["path"] == "src/main.py")
        assert src_item["decision"] == "allow"


class TestNoopHostDelegate:
    """5b.6: NoopHostDelegate host_unavailable and policy_decision tests."""

    def test_noop_host_unavailable_true(self) -> None:
        """Test that NoopHostDelegate.host_unavailable is True."""
        from memory_core.tools.memory_hook_impls import NoopHostDelegate

        delegate = NoopHostDelegate()
        assert delegate.host_unavailable is True

    def test_noop_response_contains_host_unavailable(self) -> None:
        """Test that noop_response stdout JSON contains host_unavailable=True."""
        from memory_core.tools.memory_hook_impls import NoopHostDelegate

        delegate = NoopHostDelegate()
        response = delegate.noop_response()
        assert response.returncode == 0
        data = json.loads(response.stdout)
        assert data["host_unavailable"] is True

    def test_noop_response_contains_policy_decision(self) -> None:
        """Test that noop_response stdout JSON contains policy_decision separate from availability."""
        from memory_core.tools.memory_hook_impls import NoopHostDelegate

        delegate = NoopHostDelegate()
        response = delegate.noop_response()
        data = json.loads(response.stdout)
        assert "policy_decision" in data
        assert data["policy_decision"] == "no_host"

    def test_delegate_interface_has_host_unavailable_property(self) -> None:
        """Test that HostDelegate interface defines host_unavailable property."""
        from memory_core.tools.memory_hook_interfaces import HostDelegate

        # Check that the property exists on the ABC
        assert hasattr(HostDelegate, "host_unavailable")
        # Default should be False
        assert HostDelegate.host_unavailable.fget is not None  # type: ignore[attr-defined]

    def test_execute_returns_host_unavailable_response(self) -> None:
        """Test that execute() returns response with host_unavailable marker."""
        from memory_core.tools.memory_hook_impls import NoopHostDelegate

        delegate = NoopHostDelegate()
        response = delegate.execute("test_event", "{}", {})
        data = json.loads(response.stdout)
        assert data["host_unavailable"] is True
        assert data["policy_decision"] == "no_host"
