# Memory Docs Index

> 文档编号：MEM-DOCS-001
> 版本：V5.0
> 更新日期：2026-08-01

This file catalogs every document under `memory/docs/`.

## 法律地位声明

本索引所列内容均为 **incoming-raw** 原始素材。
docs 子目录下的内容属于待摄入的原始材料，不具备 canonical 合法性。
架构/规格文档请参考 `docs/` 目录。

## Document Categories

### 系统规范（system/）

系统集成规范。协议规格文档已统一到 `docs/specs/`。

| File | 说明 |
|------|------|
| `system/HOOK_INTEGRATION_SPEC.md` | 跨 IDE/平台 hook 集成规范（事件映射、验证方法） |
| `system/INDEX.md` | system 目录索引（指向 docs/specs/ 为唯一源） |

### 草案（drafts/）

待审核的产品设计方案，通过后升级到对应目录。

| File | 说明 |
|------|------|
| `drafts/INDEX.md` | drafts 目录索引 |
| `drafts/PRD-001-PRODUCT-DESIGN.md` | 记忆系统产品设计 |
| `drafts/PRETOOLUSE_GUARD_TASK_REMOVAL.md` | PreToolUse Guard 任务移除方案 |
| `drafts/A-B-C-DAILY-LOG-SYSTEM.md` | A-B-C 日志系统草案 |
| `drafts/INTEGRITY-REALTIME-LOG-SYSTEM.md` | 完整性实时日志系统草案 |
| `drafts/linear-droid-gitlab-github-pipeline-spec.md` | Linear-Droid-GitLab-GitHub 流水线规格 |

### 计划（plans/）

执行计划、里程碑、PLAN-STATUS 跟踪。

| File | 说明 |
|------|------|
| `plans/INDEX.md` | plans 目录索引 |
| `plans/PLAN-STATUS.md` | 活跃计划状态（同步自 ShowDoc） |
| `plans/PLAN-0003-9-9-HOOK-COVERAGE.md` | Hook 100% 集成计划 |
| `plans/EXECUTION_PLAN_OWNERSHIP_PROTECTION.md` | 所有权保护执行计划 |
| `plans/UPGRADE_PLAN_OWNERSHIP_PROTECTION.md` | v3 合并升级计划 |
| `plans/M7-independent-repo-cutover-plan.md` | 独立仓迁出执行计划 |
| `plans/dead-code-cleanup-2026-07-22.md` | 死代码清理计划 |
| `plans/2026-07-07-system-remediation-summary.md` | 系统修复总结 |

### 重构日志（refactor-logs/）

历史重构过程记录。

| File | 说明 |
|------|------|
| `refactor-logs/v5-dplus-refactor-2026-07-20.md` | v5 D+ 函数重构日志 |
| `refactor-logs/mypy-183-to-0-2026-07-21.md` | mypy 183→0 类型安全加固 |
| `refactor-logs/doc-routing-engine-2026-07-22.md` | 文档路由引擎实现日志 |

### 运维手册（runbooks/）

通用维护手册 + 环境特定手册。

| File | 说明 |
|------|------|
| `runbooks/INDEX.md` | runbooks 目录索引 |
| `runbooks/VERSION_SYNC_RUNBOOK.md` | 三文件版本同步操作（通用） |
| `runbooks/MIGRATION_RUNBOOK.md` | 消费项目迁移操作（通用） |
| `runbooks/CONFIG_MANAGEMENT_RUNBOOK.md` | 配置管理（通用） |
| `runbooks/CI_CD_RUNBOOK.md` | GitLab CI 配置与发布自动化（环境特定） |
| `runbooks/GIT_PUSH_SPEC.md` | Git Push 规范（环境特定） |
| `runbooks/RUNBOOKS.md` | 事件响应、监控、部署可观测性（环境特定） |
| `runbooks/APISIX-MAINTENANCE.md` | APISIX 网关维护手册（环境特定） |

### RFC 提案（rfcs/）

架构变更提案。

| File | 说明 |
|------|------|
| `rfcs/INDEX.md` | rfcs 目录索引 |
| `rfcs/RFC-0001-eliminate-dot-memory.md` | 消除 .memory 目录提案 |

### 工程笔记（notes/）

技术调研、问题分析。

| File | 说明 |
|------|------|
| `notes/INDEX.md` | notes 目录索引 |
| `notes/prompt-truncation-engineering-solutions.md` | Task prompt 截断解决方案 |
| `notes/projects/AEdu/INDEX.md` | AEdu 项目研究索引（从 research/ 迁移） |

### 审计记录（audit/）

仓库审计、session 审计、同步审计、残留记录。

| File | 说明 |
|------|------|
| `audit/INDEX.md` | audit 目录索引 |
| `audit/2026-05-09-memory-core-audit.md` | memory-core 审计报告 |
| `audit/audit-sop.md` | 审计标准操作流程 |
| `audit/coverage-gaps-2026-07-18.md` | 覆盖率差距分析 |
| `audit/SUMMARY.md` | 审计摘要 |
| `audit/factory-guides-poweruser-summary.md` | Factory 指南摘要 |
| `audit/session-5f742a02-opening-strategy-audit.md` | Session 审计 |
| `audit/showdoc-migration-complete-2026-05-19.md` | ShowDoc 迁移审计 |
| `audit/showdoc-sync-2026-05-14.md` | ShowDoc 同步审计 |
| `audit/RESIDUE_INVENTORY.md` | 残留清单（原 residue/ 目录） |
| `audit/RESIDUE_DISPOSITION_PLAN.md` | 处置计划（原 residue/ 目录） |
| `audit/audit-verification/` | 审计验证子目录（含执行摘要、方法论、JSON 数据） |

### Bug 报告（bug-reports/）

| File | 说明 |
|------|------|
| `bug-reports/INDEX.md` | bug-reports 目录索引 |
| `bug-reports/factory-session-orphan-shutdown-crash.md` | Factory session 孤儿崩溃分析 |

### 已归档（archive/）

过时/已完成的历史文档。

| File | 说明 |
|------|------|
| `archive/INDEX.md` | archive 目录索引 |
| `archive/DISPATCH_TEMPLATE.md` | 分派模板 |
| `archive/FIXTURES_VS_REAL.md` | Fixture 与真实数据对比 |
| `archive/MIGRATION_CHECKLIST.md` | 迁移清单 |
| `archive/MIGRATION_FORMAT_SPEC.md` | 迁移格式规范 |
| `archive/MIGRATION_RULES.md` | 迁移规则 |
| `archive/RELEASE_NOTES_v0.2.0.md` | v0.2.0 发布说明 |
| `archive/TASK_CARD_TEMPLATE.md` | 任务卡模板 |
| `archive/VALIDATION_COMPLETION.md` | 验证完成报告 |
| `archive/VALIDATION_FINAL.md` | 最终验证报告 |
| `archive/VALIDATION_WAVE1.md` | Wave 1 验证报告 |
| `archive/VALIDATION_WAVE2.md` | Wave 2 验证报告 |

---

## 与其他目录的关系

| 目录 | 用途 |
|------|------|
| `docs/specs/` | 协议规格文档唯一源（BOUNDARY, DOT_MEMORY_SPEC 等） |
| `docs/architecture/` | 架构设计文档（01-architecture ~ API-CONTRACT） |
| `docs/guides/` | 使用指南（observability, posthog 等） |
| `memory/kb/decisions/` | 决策记录（D-001 ~ D-011） |
| `memory/kb/lessons/` | 经验教训 |

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| V5.0 | 2026-08-01 | 全面同步: 删除幽灵引用(design/residue/research/decisions/记忆系统全景文档), 补充遗漏目录(refactor-logs/audit-verification), 去重 specs 到 docs/specs/ |
| V4.1 | 2026-05-26 | 添加子目录 INDEX.md 交叉引用 |
| V4.0 | 2026-05-26 | 按分类重组目录 |
