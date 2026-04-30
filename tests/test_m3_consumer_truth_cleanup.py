#!/usr/bin/env python3
"""M3 consumer truth cleanup 必补测试。

4 组测试验证 M3 变更的正确性：
1. governance/routing contract：模块层不再默认内建 workbot 路由真相
2. project binding truth：workbot.md 不再把错误路径当正式绑定
3. release whitelist / dispatch-off：不配置下游时不会默认 dispatch workbot
4. rollback compatibility：neutral core、adapter、legacy fallback 兼容
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT / "memory_core"

ROUTING_PATH = WORKSPACE_ROOT / "memory" / "kb" / "global" / "workbot-memory-routing.md"
LEGAL_CORE_PATH = WORKSPACE_ROOT / "project-map" / "legal-core-map.md"
INGESTION_PATH = WORKSPACE_ROOT / "project-map" / "ingestion-registry-map.md"
WORKBOT_MD_PATH = WORKSPACE_ROOT / "memory" / "kb" / "projects" / "workbot.md"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release-and-dispatch.yml"


# ---------------------------------------------------------------------------
# 测试组 1：governance/routing contract
# ---------------------------------------------------------------------------


class TestGovernanceRoutingContract:
    """验证模块层不再默认内建 workbot 路由真相。"""

    def test_routing_has_adapter_scope(self):
        text = ROUTING_PATH.read_text(encoding="utf-8")
        assert "Scope: adapter" in text

    def test_routing_declares_not_module_default(self):
        text = ROUTING_PATH.read_text(encoding="utf-8")
        assert "不是模块默认路由" in text

    def test_routing_allows_other_adapters(self):
        text = ROUTING_PATH.read_text(encoding="utf-8")
        assert "其他 adapter 可以定义自己的路由规则" in text

    def test_legal_core_has_adapter_scope(self):
        text = LEGAL_CORE_PATH.read_text(encoding="utf-8")
        assert "Scope: adapter" in text

    def test_legal_core_declares_not_module_default(self):
        text = LEGAL_CORE_PATH.read_text(encoding="utf-8")
        assert "不是模块默认合法性定义" in text

    def test_ingestion_has_adapter_scope(self):
        text = INGESTION_PATH.read_text(encoding="utf-8")
        assert "Scope: adapter" in text

    def test_ingestion_declares_not_module_default(self):
        text = INGESTION_PATH.read_text(encoding="utf-8")
        assert "不是模块默认登记" in text

    def test_no_workbot_hardcoded_in_routing(self):
        text = ROUTING_PATH.read_text(encoding="utf-8")
        assert "/Users/busiji" not in text


# ---------------------------------------------------------------------------
# 测试组 2：project binding truth
# ---------------------------------------------------------------------------


class TestProjectBindingTruth:
    """验证 workbot.md 不再把错误路径当正式绑定。"""

    def test_workbot_md_has_adapter_scope(self):
        text = WORKBOT_MD_PATH.read_text(encoding="utf-8")
        assert "scope: adapter" in text

    def test_workbot_md_declares_consumer_adapter(self):
        text = WORKBOT_MD_PATH.read_text(encoding="utf-8")
        assert "不是模块默认身份真相" in text

    def test_workbot_md_no_absolute_paths(self):
        text = WORKBOT_MD_PATH.read_text(encoding="utf-8")
        assert "/Users/busiji" not in text

    def test_workbot_md_cmux_is_adapter_choice(self):
        text = WORKBOT_MD_PATH.read_text(encoding="utf-8")
        assert "workbot adapter 的运行时选择" in text

    def test_workbot_md_allows_other_consumers(self):
        text = WORKBOT_MD_PATH.read_text(encoding="utf-8")
        assert "其他 consumer adapter 可以有自己的" in text


# ---------------------------------------------------------------------------
# 测试组 3：release whitelist / dispatch-off
# ---------------------------------------------------------------------------


class TestReleaseWhitelist:
    """验证不配置下游时不会默认 dispatch workbot。"""

    def test_workflow_no_hardcoded_workbot_target(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "hdot123/workbot" not in text

    def test_workflow_dispatch_targets_default_empty(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        # Find dispatch_targets input and verify default is empty
        assert 'default: ""' in text or "default: ''" in text

    def test_workflow_dispatch_step_requires_non_empty_targets(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        # The dispatch step should have a condition checking targets != ''
        assert "dispatch_targets != ''" in text

    def test_workflow_uses_generic_dispatch_token(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "DISPATCH_TOKEN" in text
        assert "WORKBOT_REPO_DISPATCH_TOKEN" not in text

    def test_workflow_tag_computation_preserved(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "v*" in text
        assert "sort=-v:refname" in text


# ---------------------------------------------------------------------------
# 测试组 4：rollback compatibility
# ---------------------------------------------------------------------------


class TestRollbackCompatibility:
    """验证 neutral core、adapter、legacy fallback 兼容。"""

    def test_gateway_imports_cleanly(self):
        from memory_core.tools.memory_hook_gateway import build_context_package

        assert callable(build_context_package)

    def test_impls_imports_cleanly(self):
        from memory_core.tools.memory_hook_impls import (
            CodexDelegate,
            ClaudeDelegate,
            PolicyRegistryImpl,
        )

        assert callable(CodexDelegate)
        assert callable(ClaudeDelegate)
        assert callable(PolicyRegistryImpl)

    def test_adapter_profile_imports_cleanly(self):
        from memory_core.tools.memory_hook_adapters.workbot_runtime_profile import (
            build_workbot_runtime_profile,
        )

        profile = build_workbot_runtime_profile(REPO_ROOT, WORKSPACE_ROOT)
        assert "CLAUDE_HOOK_STATE_FILE" in profile
        assert "ARTIFACT_COMPACTION" in profile

    def test_neutral_policy_imports_cleanly(self):
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        assert NeutralGatewayBusinessPolicy is not None

    def test_rollback_script_exists_and_compiles(self):
        rollback_path = WORKSPACE_ROOT / "tools" / "memory_hook_provider_rollback.py"
        assert rollback_path.exists()
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(rollback_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_core_provider_switch_works(self):
        from memory_core.tools.memory_hook_gateway import _resolve_core_builder

        name, builder, errors = _resolve_core_builder("legacy", allow_fallback=True)
        assert name == "legacy"
        assert callable(builder)
        assert errors == []
