#!/usr/bin/env python3
"""M3 文档 scope 覆盖补全测试。

验证全局文档层正确声明了 adapter 级 scope，防止模块默认泄露：
a. workbot-memory-system.md  Scope: adapter
b. workbot-truth-model.md     scope: adapter (frontmatter)
c. workbot-project-map-governance.md  Scope: adapter
d. workbot-policy-pack.md     adapter 级别声明
e. workbot-policy-pack.json   adapter_scope: true
f. memory-hook-policy-pack.json  adapter_scope: true
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GLOBAL_DIR = REPO_ROOT / "workspace" / "memory" / "kb" / "global"

MEMORY_SYSTEM_PATH = GLOBAL_DIR / "workbot-memory-system.md"
TRUTH_MODEL_PATH = GLOBAL_DIR / "workbot-truth-model.md"
PROJECT_MAP_GOVERNANCE_PATH = GLOBAL_DIR / "workbot-project-map-governance.md"
POLICY_PACK_MD_PATH = GLOBAL_DIR / "workbot-policy-pack.md"
POLICY_PACK_JSON_PATH = GLOBAL_DIR / "workbot-policy-pack.json"
MEMORY_HOOK_POLICY_PACK_PATH = GLOBAL_DIR / "memory-hook-policy-pack.json"


class TestWorkbotMemorySystemScope:
    """workbot-memory-system.md 必须声明 Scope: adapter。"""

    def test_memory_system_has_adapter_scope(self):
        text = MEMORY_SYSTEM_PATH.read_text(encoding="utf-8")
        assert "Scope: adapter" in text

    def test_memory_system_declares_not_module_default(self):
        text = MEMORY_SYSTEM_PATH.read_text(encoding="utf-8")
        assert "不是模块默认记忆系统" in text

    def test_memory_system_allows_other_adapters(self):
        text = MEMORY_SYSTEM_PATH.read_text(encoding="utf-8")
        assert "其他 adapter 可以定义自己的记忆系统规则" in text


class TestWorkbotTruthModelScope:
    """workbot-truth-model.md 必须声明 scope: adapter (frontmatter)。"""

    def test_truth_model_has_adapter_scope_in_frontmatter(self):
        text = TRUTH_MODEL_PATH.read_text(encoding="utf-8")
        assert "scope: adapter" in text

    def test_truth_model_declares_not_module_default(self):
        text = TRUTH_MODEL_PATH.read_text(encoding="utf-8")
        assert "不是模块默认真相模型" in text

    def test_truth_model_allows_other_adapters(self):
        text = TRUTH_MODEL_PATH.read_text(encoding="utf-8")
        assert "其他 adapter 可以定义自己的真相判定规则" in text


class TestWorkbotProjectMapGovernanceScope:
    """workbot-project-map-governance.md 必须声明 Scope: adapter。"""

    def test_project_map_governance_has_adapter_scope(self):
        text = PROJECT_MAP_GOVERNANCE_PATH.read_text(encoding="utf-8")
        assert "Scope: adapter" in text

    def test_project_map_governance_declares_not_module_default(self):
        text = PROJECT_MAP_GOVERNANCE_PATH.read_text(encoding="utf-8")
        assert "不是模块默认治理" in text

    def test_project_map_governance_allows_other_adapters(self):
        text = PROJECT_MAP_GOVERNANCE_PATH.read_text(encoding="utf-8")
        assert "其他 adapter 可以定义自己的治理规则" in text


class TestWorkbotPolicyPackMdScope:
    """workbot-policy-pack.md 必须声明 adapter 级别。"""

    def test_policy_pack_md_declares_adapter_level(self):
        text = POLICY_PACK_MD_PATH.read_text(encoding="utf-8")
        assert "workbot adapter 级别的策略包规范" in text

    def test_policy_pack_md_declares_not_module_default(self):
        text = POLICY_PACK_MD_PATH.read_text(encoding="utf-8")
        assert "不是模块默认策略" in text

    def test_policy_pack_md_allows_other_adapters(self):
        text = POLICY_PACK_MD_PATH.read_text(encoding="utf-8")
        assert "其他 adapter 可以定义自己的策略包" in text


class TestWorkbotPolicyPackJsonAdapterScope:
    """workbot-policy-pack.json 必须包含 adapter_scope: true。"""

    def test_policy_pack_json_has_adapter_scope_true(self):
        data = json.loads(POLICY_PACK_JSON_PATH.read_text(encoding="utf-8"))
        assert data.get("adapter_scope") is True

    def test_policy_pack_json_scope_is_workbot(self):
        data = json.loads(POLICY_PACK_JSON_PATH.read_text(encoding="utf-8"))
        assert data.get("scope") == "workbot"

    def test_policy_pack_json_schema_version(self):
        data = json.loads(POLICY_PACK_JSON_PATH.read_text(encoding="utf-8"))
        assert data.get("schema_version") == "m3-policy-pack-v1"


class TestMemoryHookPolicyPackJsonAdapterScope:
    """memory-hook-policy-pack.json 必须包含 adapter_scope: true。"""

    def test_memory_hook_policy_pack_has_adapter_scope_true(self):
        data = json.loads(MEMORY_HOOK_POLICY_PACK_PATH.read_text(encoding="utf-8"))
        assert data.get("adapter_scope") is True

    def test_memory_hook_policy_pack_scope_is_default(self):
        data = json.loads(MEMORY_HOOK_POLICY_PACK_PATH.read_text(encoding="utf-8"))
        assert data.get("scope") == "default"

    def test_memory_hook_policy_pack_schema_version(self):
        data = json.loads(MEMORY_HOOK_POLICY_PACK_PATH.read_text(encoding="utf-8"))
        assert data.get("schema_version") == "m3-policy-pack-v1"
