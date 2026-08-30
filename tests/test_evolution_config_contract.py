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
