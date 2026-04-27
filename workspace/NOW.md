# NOW.md

## Mission
- 将 memory module 收口为通用的总控记忆层，使 MRD、Obsidian、项目 canonical 和长期记忆层围绕根级 `workspace/` 运转，供任意 consuming project 接入使用

## Today
- ✅ M3: policy-pack adapter 注入接线
- ✅ M7: 独立仓迁出收口 — P1-P6 全部完成
- ✅ M8: API 完成（CoreConfig 结构化 + 简化入口 + v1 schema + 接口扩展 + 职责分离 + 包发布准备）
- ✅ Re-audit 全部修复（runtime guards / ArtifactWriter / WriteTargetPolicyImpl date bug / cmux_hook_state tests）
- ✅ Python 3.9 兼容性修复
- **216 tests passed**, validate 6/6

## Next 3 Actions
1. 发布 v0.2.0 GitHub Release
2. 收集第一个外部消费者项目接入反馈
3. 验证 pip install memory-core 在干净环境下工作

## Blockers
- 无

## Memory Health
- 长期记忆层骨架已建立，re-audit 修复全部合入，运行状态 `status=ok`
- 独立仓测试全绿，`workbot` 绝对路径引用已清零

---
Updated: 2026-04-27 (Asia/Shanghai)
