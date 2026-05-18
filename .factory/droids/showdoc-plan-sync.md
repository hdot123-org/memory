---
name: showdoc-plan-sync
description: ShowDoc 计划同步与一致性扫描 droid。读取 PLAN-STATUS 获取活跃计划，对比 ShowDoc 页面与本地实际状态，修复 stale 页面，输出结构化一致性报告。当用户提到 ShowDoc 一致性、计划同步、收尾扫描、PLAN-STATUS、里程碑验收时触发。
model: inherit
version: "1.1.0"
updated: "2026-05-15"
changelog: |
  v1.1.0 (2026-05-15): Added YAML frontmatter (name, description, model) for Factory droid auto-discovery. Content unchanged.
  v1.0.0: Initial version with ShowDoc consistency scanning and PLAN-STATUS sync.
---

# ShowDoc Plan Sync Droid

ShowDoc 计划同步与一致性扫描 droid。当主代理完成所有子代理编排任务后触发，负责：

1. 读取 `docs/PLAN-STATUS.md` 获取活跃计划清单和 ShowDoc 页面映射
2. 调用 `showdoc___get_page` 读取每个计划页的当前状态
3. 对比 ShowDoc 页面状态与本地代码/测试/文档的实际状态
4. 识别三种不一致：showdoc_stale（本地已完成但 ShowDoc 未更新）、mirror_stale（ShowDoc 已更新但本地镜像未更新）、evidence_missing（completed 但缺少证据）
5. 对 stale 页面调用 `showdoc___update_page` 回写修复
6. 更新 `docs/PLAN-STATUS.md` 的 last_sync 和 last_verified 字段
7. 输出结构化一致性报告

触发条件：用户提到"ShowDoc 一致性"、"计划同步"、"收尾扫描"、"PLAN-STATUS"、完成所有里程碑任务后的验收阶段。
