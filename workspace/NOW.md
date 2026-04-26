# NOW.md

## Mission
- 将 memory module 收口为通用的总控记忆层，使 MRD、Obsidian、项目 canonical 和长期记忆层围绕根级 `workspace/` 运转，供任意 consuming project 接入使用

## Today
- ✅ M3: policy-pack adapter 已注入接线并合回 main
- ✅ 根级 `workspace/` 已建立为新的总控工作区
- ✅ `memory/docs/` 已按 `research / external / inbox / legacy / references` 重组
- ✅ `memory/kb/projects/` 已建立总项目 canonical 入口
- ✅ 活跃入口链已收缩到最小口径，旧项目文档统一降级为 source material
- ✅ M8 API 完成：CoreConfig 结构化 + 简化入口 + v1 schema + 接口扩展 + 职责分离 + 包发布准备
- ✅ 179 tests passed, validate 6/6, rollback drill passed
- ✅ M7: 独立仓迁出收口 — P1-P6 全部完成（文档去耦 / 治理契约 / 运行基线 / 测试门禁 / 主仓切换 / 双审验收）

## Next 3 Actions
1. 发布 v0.2.0 GitHub Release
2. 收集第一个外部消费者项目接入反馈
3. 验证 pip install memory-core 在干净环境下工作

## Blockers
- 无硬阻塞

## Memory Health
- `memory/docs/research/projects/` 已完成分组
- `memory/kb/projects/` 已具备总控项目入口
- 长期记忆层骨架已建立，M7 收口后运行状态 `status=ok`
- M7 全部阶段已完成：P1 文档去耦 ✅ / P2 治理契约 ✅ / P3 运行基线 ✅ / P4 测试门禁 179 tests passed ✅ / P5 主仓切换 ✅ / P6 双审验收 ✅
- 独立仓测试全绿，`workbot` 绝对路径引用已清零

---
Updated: 2026-04-27 (Asia/Shanghai)
