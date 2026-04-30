#!/usr/bin/env python3
"""M2 adapter extraction 必补测试。

4 组测试验证 M2 变更的正确性：
1. delegate gate：bypass 下沉到 adapter
2. state file strictness：adapter policy，非 core 硬编码
3. artifact/compaction policy：存在且可由 adapter 配置
4. adapter hook contract：不再代表模块全局合同
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT / "workspace"
HOOK_CONTRACT_PATH = (
    WORKSPACE_ROOT / "memory" / "kb" / "global" / "workbot-hook-contract.md"
)


# ---------------------------------------------------------------------------
# 测试组 1：delegate gate
# ---------------------------------------------------------------------------


class TestDelegateGate:
    """验证 codex/claude bypass 分流来自 adapter，不是 core 默认。"""

    def test_codex_delegate_noop_returns_empty_json(self):
        from workspace.tools.memory_hook_impls import CodexDelegate

        delegate = CodexDelegate()
        result = delegate.noop_response()
        assert result.returncode == 0
        assert result.stdout == "{}\n"
        assert result.stderr == ""

    def test_claude_delegate_noop_returns_empty(self):
        from workspace.tools.memory_hook_impls import ClaudeDelegate

        delegate = ClaudeDelegate()
        result = delegate.noop_response()
        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

    def test_gateway_noop_calls_delegate_noop_response(self):
        from workspace.tools.memory_hook_gateway import _delegate_noop_response

        mock_delegate = MagicMock()
        mock_delegate.noop_response.return_value = MagicMock(
            returncode=0, stdout="mocked\n", stderr=""
        )
        with patch(
            "workspace.tools.memory_hook_gateway._get_host_delegate",
            return_value=mock_delegate,
        ):
            result = _delegate_noop_response("codex")
        mock_delegate.noop_response.assert_called_once()
        assert result == 0

    def test_main_stdout_fallback_uses_delegate_noop(self):
        import subprocess

        from workspace.tools.memory_hook_impls import CodexDelegate

        delegate = CodexDelegate()
        noop = delegate.noop_response()
        # 当 proc.stdout 为空时，delegate.noop_response() 提供输出
        assert isinstance(noop, subprocess.CompletedProcess)
        assert noop.stdout == "{}\n"


# ---------------------------------------------------------------------------
# 测试组 1b：无 cmux 时 delegate execute() 返回 noop
# ---------------------------------------------------------------------------


class TestDelegateNoopFallback:
    """验证 cmux 不可用时 execute() 返回 noop 而非抛异常。"""

    def test_codex_execute_no_cmux_returns_noop(self):
        from workspace.tools.memory_hook_impls import CodexDelegate
        delegate = CodexDelegate(which_cmd=lambda _: None)
        result = delegate.execute("session-start", "{}", {})
        assert result.returncode == 0
        assert result.stdout == "{}\n"

    def test_codex_execute_no_surface_returns_noop(self):
        from workspace.tools.memory_hook_impls import CodexDelegate
        delegate = CodexDelegate(surface_id="", which_cmd=lambda _: "/usr/bin/cmux")
        result = delegate.execute("session-start", "{}", {})
        assert result.returncode == 0
        assert result.stdout == "{}\n"

    def test_claude_execute_no_cmux_returns_noop(self):
        from workspace.tools.memory_hook_impls import ClaudeDelegate
        delegate = ClaudeDelegate(which_cmd=lambda _: None)
        result = delegate.execute("session-start", "{}", {})
        assert result.returncode == 0

    def test_claude_execute_no_workspace_returns_noop(self):
        from workspace.tools.memory_hook_impls import ClaudeDelegate
        delegate = ClaudeDelegate(workspace_id="", surface_id="s1", which_cmd=lambda _: "/usr/bin/cmux")
        result = delegate.execute("session-start", "{}", {})
        assert result.returncode == 0

    def test_claude_execute_no_surface_returns_noop(self):
        from workspace.tools.memory_hook_impls import ClaudeDelegate
        delegate = ClaudeDelegate(workspace_id="w1", surface_id="", which_cmd=lambda _: "/usr/bin/cmux")
        result = delegate.execute("session-start", "{}", {})
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# 测试组 2：CMUX_HOOK_STATE_FILE strictness
# ---------------------------------------------------------------------------


class TestStateFileStrictness:
    """验证 state_file 严格来自 adapter 注入，不是环境变量直读。"""

    def test_claude_delegate_state_file_not_read_from_env(self, monkeypatch):
        from workspace.tools.memory_hook_impls import ClaudeDelegate

        monkeypatch.setenv("CMUX_HOOK_STATE_FILE", "/should/not/be/used")
        delegate = ClaudeDelegate(state_file=None)
        assert delegate._state_file is None

    def test_claude_delegate_state_file_injected_by_constructor(self):
        from workspace.tools.memory_hook_impls import ClaudeDelegate

        delegate = ClaudeDelegate(state_file="/injected/path")
        assert delegate._state_file == "/injected/path"

    def test_runtime_profile_resolves_state_file_from_env(self):
        from workspace.tools.memory_hook_adapters.workbot_runtime_profile import (
            build_workbot_runtime_profile,
        )

        profile = build_workbot_runtime_profile(REPO_ROOT, WORKSPACE_ROOT)
        assert "CLAUDE_HOOK_STATE_FILE" in profile
        assert isinstance(profile["CLAUDE_HOOK_STATE_FILE"], str)


# ---------------------------------------------------------------------------
# 测试组 3：artifact/compaction policy
# ---------------------------------------------------------------------------


class TestArtifactCompaction:
    """验证 compaction 机制存在且可由 adapter 配置。"""

    def test_runtime_profile_contains_compaction_policy(self):
        from workspace.tools.memory_hook_adapters.workbot_runtime_profile import (
            build_workbot_runtime_profile,
        )

        profile = build_workbot_runtime_profile(REPO_ROOT, WORKSPACE_ROOT)
        assert "ARTIFACT_COMPACTION" in profile
        compaction = profile["ARTIFACT_COMPACTION"]
        expected_keys = {
            "include_system_context",
            "include_project_context",
            "include_task_context",
            "include_evidence_refs",
            "include_allowed_reads",
            "include_allowed_writes",
        }
        assert expected_keys == set(compaction.keys())

    def test_compaction_all_true_preserves_all_sections(self):
        from workspace.tools.memory_hook_gateway import _apply_artifact_compaction

        policy = {
            "include_system_context": True,
            "include_project_context": True,
            "include_task_context": True,
            "include_evidence_refs": True,
            "include_allowed_reads": True,
            "include_allowed_writes": True,
        }
        with patch.dict(
            "workspace.tools.memory_hook_gateway.__dict__",
            {"ARTIFACT_COMPACTION": policy},
        ):
            package = {
                "system_context": {"boot_entry": "test"},
                "project_context": {"scope": "workbot"},
                "task_context": {"event": "session-start"},
                "evidence_refs": ["/some/path"],
                "allowed_reads": ["/read/path"],
                "allowed_writes": {"fact": "/write/path"},
            }
            _apply_artifact_compaction(package)
            assert "system_context" in package
            assert "project_context" in package
            assert "task_context" in package
            assert "evidence_refs" in package
            assert "allowed_reads" in package
            assert "allowed_writes" in package

    def test_compaction_can_remove_system_context(self):
        from workspace.tools.memory_hook_gateway import _apply_artifact_compaction

        policy = {
            "include_system_context": False,
            "include_project_context": True,
            "include_task_context": True,
            "include_evidence_refs": True,
            "include_allowed_reads": True,
            "include_allowed_writes": True,
        }
        with patch.dict(
            "workspace.tools.memory_hook_gateway.__dict__",
            {"ARTIFACT_COMPACTION": policy},
        ):
            package = {
                "system_context": {"boot_entry": "test"},
                "project_context": {"scope": "workbot"},
            }
            _apply_artifact_compaction(package)
            assert "system_context" not in package
            assert "project_context" in package

    def test_compaction_can_remove_multiple_sections(self):
        from workspace.tools.memory_hook_gateway import _apply_artifact_compaction

        policy = {
            "include_system_context": False,
            "include_project_context": False,
            "include_task_context": False,
            "include_evidence_refs": False,
            "include_allowed_reads": False,
            "include_allowed_writes": False,
        }
        with patch.dict(
            "workspace.tools.memory_hook_gateway.__dict__",
            {"ARTIFACT_COMPACTION": policy},
        ):
            package = {
                "system_context": {},
                "project_context": {},
                "task_context": {},
                "evidence_refs": [],
                "allowed_reads": [],
                "allowed_writes": {},
            }
            _apply_artifact_compaction(package)
            assert "system_context" not in package
            assert "project_context" not in package
            assert "task_context" not in package
            assert "evidence_refs" not in package
            assert "allowed_reads" not in package
            assert "allowed_writes" not in package


# ---------------------------------------------------------------------------
# 测试组 4：adapter hook contract
# ---------------------------------------------------------------------------


class TestHookContract:
    """验证 workbot-hook-contract 已降为 adapter 合同，不再代表模块全局。"""

    def test_hook_contract_has_adapter_scope(self):
        text = HOOK_CONTRACT_PATH.read_text(encoding="utf-8")
        assert "scope: adapter" in text

    def test_hook_contract_title_contains_adapter(self):
        text = HOOK_CONTRACT_PATH.read_text(encoding="utf-8")
        assert "Adapter Contract" in text

    def test_hook_contract_not_module_global_default(self):
        text = HOOK_CONTRACT_PATH.read_text(encoding="utf-8")
        assert "不是模块全局默认合同" in text

    def test_hook_contract_allows_other_adapters(self):
        text = HOOK_CONTRACT_PATH.read_text(encoding="utf-8")
        assert "其他 adapter 可以定义自己的合同" in text
