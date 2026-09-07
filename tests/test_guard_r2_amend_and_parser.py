"""R2' guard tests: memory-amend sanctioned channel + three parser fixes.

Covers:
- Execute 放行：memory-amend 裸名 / 绝对安装路径（首 token 精确匹配）；
  echo 前缀不获放行；放行不跨段（后续 rm 段照常过检）。
- Parser 修复 1：git -C/--git-dir/--no-pager 等全局 flag 后的 readonly
  子命令不再误判为写；写子命令仍判写。
- Parser 修复 2：for/in/do/done 循环结构化解析——只读循环体放行，
  写循环体仍拦，命令替换先行检查不被绕过，算术 for 头保持 fail-closed。
- Parser 修复 3：无可提取路径 + 整条命令含 memory/ 字串不再涂抹拦截；
  uncertain owned 通配路径的 B1 语义不变。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_core.tools import _guard_classify as _gc
from memory_core.tools._guard_classify import (
    _segment_has_write_intent,
    classify_tool_use,
    is_sanctioned_amend_token,
)
from memory_core.tools._rule_types import RuleResult


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """Minimal consumer project with an owned memory/ tree."""
    (tmp_path / "memory" / "system").mkdir(parents=True)
    (tmp_path / "memory" / "kb" / "decisions").mkdir(parents=True)
    return tmp_path


def _classify(command: str, project_root: Path) -> RuleResult:
    return classify_tool_use({"tool_name": "Execute", "tool_input": {"command": command}}, project_root)


def _decision(result: RuleResult) -> str:
    return str(result.detail.get("decision"))


# ---------------------------------------------------------------------------
# R2'-1: memory-amend sanctioned 追加通道
# ---------------------------------------------------------------------------


class TestSanctionedAmendToken:
    def test_bare_name_is_sanctioned(self) -> None:
        assert is_sanctioned_amend_token("memory-amend") is True

    def test_prefix_and_substring_tokens_not_sanctioned(self) -> None:
        assert is_sanctioned_amend_token("memory-amend-x") is False
        assert is_sanctioned_amend_token("xmemory-amend") is False
        assert is_sanctioned_amend_token("echo") is False

    def test_absolute_install_path_sanctioned_via_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_gc, "_amend_install_path_cache", "/opt/tools/memory-amend")
        monkeypatch.setattr(_gc, "_amend_install_path_resolved", True)
        assert is_sanctioned_amend_token("/opt/tools/memory-amend") is True
        assert is_sanctioned_amend_token("/opt/tools/other-tool") is False

    def test_reset_amend_install_path_cache_re_resolves(self) -> None:
        """缓存重置后旧缓存失效，shutil.which 重新解析。"""
        _gc._amend_install_path_cache = "/stale/memory-amend-path"
        _gc._amend_install_path_resolved = True
        try:
            _gc._reset_amend_install_path_cache()
            assert _gc._amend_install_path_resolved is False
            assert is_sanctioned_amend_token("/stale/memory-amend-path") is False
        finally:
            _gc._reset_amend_install_path_cache()


class TestSanctionedAmendExecute:
    def test_bare_name_segment_allowed(self, fake_project: Path) -> None:
        """段首 token 精确为 memory-amend 的段（含 owned 目标）放行。"""
        result = _classify("memory-amend memory/kb/decisions/d.md", fake_project)
        assert _decision(result) == "allow"

    def test_absolute_path_segment_allowed(self, fake_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_gc, "_amend_install_path_cache", "/opt/tools/memory-amend")
        monkeypatch.setattr(_gc, "_amend_install_path_resolved", True)
        result = _classify("/opt/tools/memory-amend memory/kb/decisions/d.md", fake_project)
        assert _decision(result) == "allow"

    def test_echo_prefix_not_sanctioned(self, fake_project: Path) -> None:
        """echo memory-amend 首 token 是 echo：重定向 owned 目标仍拦。"""
        result = _classify("echo memory-amend >> memory/kb/decisions/d.md", fake_project)
        assert _decision(result) == "block"

    def test_sanction_does_not_leak_to_rm_segment(self, fake_project: Path) -> None:
        """memory-amend 段放行，但其后的 rm 段命中 owned 仍拦。"""
        result = _classify("memory-amend memory/kb/decisions/d.md; rm -rf memory/kb", fake_project)
        assert _decision(result) == "block"
        assert "write intent targeting owned resources" in result.message

    def test_amend_then_non_owned_rm_allowed(self, fake_project: Path) -> None:
        """memory-amend 后接非 owned 的 rm 段照常放行（rm /tmp 本就允许）。"""
        result = _classify("memory-amend x.md; rm -rf /tmp/y", fake_project)
        assert _decision(result) == "allow"

    def test_heredoc_amend_real_usage_allowed(self, fake_project: Path) -> None:
        """真实用法（heredoc 喂 stdin）：amend 段放行 + 正文行不再被涂抹拦截。"""
        command = "memory-amend memory/kb/decisions/d.md --header \"补充结论\" <<'EOF'\n更正：某结论有误\nEOF"
        result = _classify(command, fake_project)
        assert _decision(result) == "allow"


# ---------------------------------------------------------------------------
# R2'-2a: git 全局 flag 解析
# ---------------------------------------------------------------------------


class TestGitGlobalFlagParsing:
    @pytest.mark.parametrize(
        "segment",
        [
            "git -C /repo log",
            "git -C /repo status",
            "git --git-dir=/x/gd --work-tree=/x/wt log",
            "git --git-dir /x/gd log",
            "git --no-pager diff",
            "git -c core.pager=cat log",
            "git --no-optional-locks status",
            "git -C /repo cat-file -p abc123",
        ],
    )
    def test_readonly_subcmd_after_global_flags(self, segment: str) -> None:
        assert _segment_has_write_intent(segment) is False, f"'{segment}' should be readonly"

    @pytest.mark.parametrize(
        "segment",
        [
            "git -C /repo push",
            "git -C /repo add file.py",
            "git --no-pager checkout main",
            "git --work-tree=/x/wt reset --hard",
        ],
    )
    def test_write_subcmd_after_global_flags_still_write(self, segment: str) -> None:
        assert _segment_has_write_intent(segment) is True, f"'{segment}' should be write"

    def test_end_to_end_git_dash_c_log_with_owned_refs_allowed(self, fake_project: Path) -> None:
        """修复实证：`git -C <repo> log -- memory/kb/...` 不再被误拦。"""
        result = _classify("git -C /repo log -- memory/kb/decisions/", fake_project)
        assert _decision(result) == "allow"

    def test_git_log_redirect_owned_still_write(self) -> None:
        """回归：git log 重定向 owned 目标仍判写（Round-3 矩阵项）。"""
        assert _segment_has_write_intent("git log > memory/kb/out.txt") is True


# ---------------------------------------------------------------------------
# R2'-2b: shell 复合结构（循环）结构化解析
# ---------------------------------------------------------------------------


class TestShellCompoundStructures:
    def test_for_head_wordlist_is_data(self) -> None:
        assert _segment_has_write_intent("for x in memory/log/*.md") is False

    def test_bare_structural_keywords_have_no_intent(self) -> None:
        assert _segment_has_write_intent("done") is False
        assert _segment_has_write_intent("fi") is False
        assert _segment_has_write_intent("}") is False

    def test_do_strips_to_real_command(self) -> None:
        assert _segment_has_write_intent('do wc -l "$x"') is False
        assert _segment_has_write_intent('do rm -f "$x"') is True

    def test_readonly_for_loop_allowed_end_to_end(self, fake_project: Path) -> None:
        """修复实证：对 memory/log 的只读 wc 循环不再被误拦。"""
        result = _classify('for x in memory/log/*.md; do wc -l "$x"; done', fake_project)
        assert _decision(result) == "allow"

    def test_write_loop_body_still_blocked(self, fake_project: Path) -> None:
        """写循环体（重定向 owned 目标）仍拦。"""
        result = _classify('for f in *.md; do echo "$f" >> memory/log/out.md; done', fake_project)
        assert _decision(result) == "block"

    def test_command_substitution_in_head_still_write(self) -> None:
        """$(…) 先行检查不被绕过：循环头含命令替换仍判写。"""
        assert _segment_has_write_intent("for x in $(ls memory/kb)") is True

    def test_arithmetic_for_head_stays_fail_closed(self) -> None:
        """无法识别的 for 头（算术形式被分段截断）保持 fail-closed。"""
        assert _segment_has_write_intent("for ((i=0") is True

    def test_brace_group_body_checked(self) -> None:
        assert _segment_has_write_intent("{ rm -rf x") is True
        assert _segment_has_write_intent("{ wc -l x") is False


# ---------------------------------------------------------------------------
# R2'-2c: legacy 路径涂抹收紧
# ---------------------------------------------------------------------------


class TestLegacySmearTightened:
    def test_unparseable_segment_with_memory_string_elsewhere_allowed(self, fake_project: Path) -> None:
        """写意图段无可提取路径 + 整条命令他处含 memory/ 字串 → 不再涂抹拦截。

        （该段自身不含 owned 引用，段级门不触发；mysterycmd 无路径可提取。）
        """
        result = _classify('mysterycmd "$x"; echo referencing memory/kb/notes', fake_project)
        assert _decision(result) == "allow"

    def test_uncertain_owned_wildcard_still_blocked(self, fake_project: Path) -> None:
        """B1 语义保持：uncertain owned 通配路径仍拦（ VAL-GUARD-015 同族）。"""
        result = _classify("rm -f memory/*/tmp && echo done", fake_project)
        assert _decision(result) == "block"

    def test_write_segment_owning_refs_still_blocked_without_paths(self, fake_project: Path) -> None:
        """段级门兜底：未知命令段自身含 owned 引用仍拦（不依赖涂抹）。"""
        result = _classify("mysterytool --target memory/kb/x.md", fake_project)
        assert _decision(result) == "block"
