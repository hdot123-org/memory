"""evolution config 契约：error_patterns 走 pack 模板原生 jsonl 路径。

feature engine-jsonl-and-pack-adapters（m6-harden）：infra v0.5.1 引擎
run_audit_tool 不支持 output_format=jsonl stdout 时，本仓用 registry_jsonl
inline override 保住 error_patterns 扫描连续性；引擎补 jsonl 逐行解析分支
（infra-core #80）后移除 override，回归 pack 模板原生路径。本测试锁定：

1. config 声明 rule_packs: [{pack: memory}]；
2. error_patterns 不再有 inline override（registry_jsonl 文件模式退场）；
3. resolve_rule_packs 展开后 error_patterns 来自 pack 模板且声明 jsonl
   （要求 pyproject pin 的 infra-core ≥ #80 的 ToolSpec.output_format 契约；
   pin 落后旧 tag 时本断言失败——pin 与 config 撤 override 必须同 PR 原子变更）；
4. memory-core 原生未迁工具（consistency_check / validate_project）inline 保留。
"""

from pathlib import Path

import yaml
from infra_core.engine.evolution_scanner import resolve_rule_packs

CONFIG_PATH = Path(__file__).resolve().parent.parent / ".evolution" / "config.yml"


def _load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_rule_packs_declares_memory_pack() -> None:
    config = _load_config()
    assert config.get("rule_packs") == [{"pack": "memory"}]


def test_error_patterns_inline_override_removed() -> None:
    config = _load_config()
    inline_names = {t.get("name") for t in config.get("audit_tools", [])}
    assert "error_patterns" not in inline_names, (
        "error_patterns registry_jsonl inline override 应已移除（pack 模板原生 jsonl 路径）"
    )


def test_native_inline_tools_retained() -> None:
    """memory-core 原生未迁工具（协议件）inline 保留，不经 pack。"""
    config = _load_config()
    inline = {t["name"]: t for t in config.get("audit_tools", [])}
    assert inline["consistency_check"]["command"] == "memory-consistency-check --json"
    assert inline["validate_project"]["command"] == "memory-validate --target . --json"


def test_error_patterns_resolves_to_pack_jsonl_template() -> None:
    config = _load_config()
    # 未知 pack 会 sys.exit(1)——rule_packs: [memory] 必须可解析展开
    resolve_rule_packs(config)
    tool = next(t for t in config["audit_tools"] if t["name"] == "error_patterns")
    assert tool["output_format"] == "jsonl", (
        "error_patterns 必须来自 pack 模板且声明 jsonl（infra-core ≥ #80）；"
        "若断言失败，说明 pyproject 的 infra-core pin 落后于本次撤 override 变更"
    )
    assert "infra-error-patterns" in tool["command"]


def test_effective_audit_tools_meet_engine_minimum() -> None:
    """生效审计工具数 ≥ 6（严于引擎下限的本仓 CI 契约）。

    引擎 v0.7.1（infra-core #104）起 check_config_yml 按 resolve_rule_packs
    展开后的生效工具数断言 ≥ MIN_AUDIT_TOOLS（5），pack 化配置不再结构性
    误报 EVOLUTION_CONFIG_INSUFFICIENT——本仓 v0.7.1 tick 实证 0 findings，
    INFRA-661 期的 suppress.json 抑制条目已随之移除（INFRA-661 范围协调
    处置）。

    本仓保留 ≥ 6 的契约（当前生效 7 = pack 5 + inline 协要件 2，较引擎
    下限超配）：真实退化（pack 收缩、工具误禁用）直接在 CI 失败，而非等
    scanner tick 浮出 finding。
    """
    config = _load_config()
    resolve_rule_packs(config)

    effective_names = [t["name"] for t in config["audit_tools"]]
    assert len(effective_names) >= 6, (
        f"生效审计工具数 {len(effective_names)} < 本仓契约下限 6；"
        f"当前生效: {effective_names}——pack 收缩或工具误禁用需先修正工具集"
    )
