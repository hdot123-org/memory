# Memory Docs Index

> 文档编号：MEM-DOCS-001
> 版本：V4.1
> 创建日期：2026-04-15
> 更新日期：2026-05-26
> 维护人：memory system

This file catalogs every document under `memory/docs/`.

## 法律地位声明

本索引所列内容均为 **incoming-raw** 原始素材，受 `project-map/` 管辖。
docs 子目录下的所有内容属于待摄入的原始材料，**未被地图明确吸收**，不具备 canonical 合法性。
只有当 `project-map/` 显式注册后，相关条目才获得合法上下文地位。

## Document Categories

### 系统规范（system/）

memory-core 接入协议规范，消费者必须遵守。

| File | 说明 |
|------|------|
| `memory/docs/system/BOUNDARY.md` | 仓库边界定义（什么属于 memory-core，什么属于消费项目） |
| `memory/docs/system/DOT_MEMORY_SPEC.md` | `.memory/` 目录规范（结构、文件、校验规则） |
| `memory/docs/system/INDEX.md` | system 目录索引 |
| `memory/docs/system/MEMORY_LOCK_SPEC.md` | `memory.lock` 版本锁规范（版本兼容规则） |
| `memory/docs/system/MULTI_PROJECT_SCAN_SPEC.md` | 多项目扫描注册规范（SPEC-012） |

### 草案（drafts/）

待审核的产品设计方案，通过后升级到对应目录。

完整草案索引见 [memory/docs/drafts/INDEX.md](memory/docs/drafts/INDEX.md)。

| File | 说明 |
|------|------|
| `memory/docs/drafts/INDEX.md` | drafts 目录索引 |
| `memory/docs/drafts/PRD-001-PRODUCT-DESIGN.md` | 记忆系统产品设计 |
| `memory/docs/drafts/PRETOOLUSE_GUARD_TASK_REMOVAL.md` | PreToolUse Guard 任务移除方案 |

### 计划（plans/）

执行计划、里程碑、PLAN-STATUS 跟踪。

完整计划索引见 [memory/docs/plans/INDEX.md](memory/docs/plans/INDEX.md)。

| File | 说明 |
|------|------|
| `memory/docs/plans/INDEX.md` | plans 目录索引 |
| `memory/docs/plans/PLAN-STATUS.md` | 活跃计划状态（同步自 ShowDoc） |
| `memory/docs/plans/PLAN-0003-9-9-HOOK-COVERAGE.md` | Hook 100% 集成计划 |
| `memory/docs/plans/EXECUTION_PLAN_OWNERSHIP_PROTECTION.md` | 所有权保护执行计划 |
| `memory/docs/plans/UPGRADE_PLAN_OWNERSHIP_PROTECTION.md` | v3 合并升级计划 |
| `memory/docs/plans/M7-independent-repo-cutover-plan.md` | 独立仓迁出执行计划 |

### 运维手册（runbooks/）

通用维护手册（所有消费者适用）+ 环境特定手册（GitLab CI 等，仅供参考）。

完整运维手册索引见 [memory/docs/runbooks/INDEX.md](memory/docs/runbooks/INDEX.md)。

| File | 说明 |
|------|------|
| `memory/docs/runbooks/INDEX.md` | runbooks 目录索引（通用维护 vs 环境特定分类） |
| `memory/docs/runbooks/VERSION_SYNC_RUNBOOK.md` | 三文件版本同步操作（通用） |
| `memory/docs/runbooks/MIGRATION_RUNBOOK.md` | 消费项目迁移操作（通用） |
| `memory/docs/runbooks/CONFIG_MANAGEMENT_RUNBOOK.md` | 配置管理：adapter/ownership/memory.lock（通用） |
| `memory/docs/runbooks/GIT_PUSH_SPEC.md` | Git Push 规范：GitLab → GitHub 单向同步（环境特定） |
| `memory/docs/runbooks/RUNBOOKS.md` | 事件响应、监控、部署可观测性（环境特定） |

### RFC 提案（rfcs/）

架构变更提案，通过后实施并归档。

完整 RFC 索引见 [memory/docs/rfcs/INDEX.md](memory/docs/rfcs/INDEX.md)。

| File | 说明 |
|------|------|
| `memory/docs/rfcs/INDEX.md` | rfcs 目录索引 |
| `memory/docs/rfcs/RFC-0001-eliminate-dot-memory.md` | 消除 .memory 目录提案 |

### 工程笔记（notes/）

技术调研、问题分析、临时记录。

完整工程笔记索引见 [memory/docs/notes/INDEX.md](memory/docs/notes/INDEX.md)。

| File | 说明 |
|------|------|
| `memory/docs/notes/INDEX.md` | notes 目录索引 |
| `memory/docs/notes/prompt-truncation-engineering-solutions.md` | Task prompt 截断解决方案 |

### 审计记录（audit/）

仓库审计、session 审计、同步审计。

完整审计记录索引见 [memory/docs/audit/INDEX.md](memory/docs/audit/INDEX.md)。

| File | 说明 |
|------|------|
| `memory/docs/audit/INDEX.md` | audit 目录索引 |
| `memory/docs/audit/2026-05-09-memory-core-audit.md` | memory-core 审计报告 |
| `memory/docs/audit/factory-guides-poweruser-summary.md` | Factory 指南摘要 |
| `memory/docs/audit/session-5f742a02-opening-strategy-audit.md` | Session 审计 |
| `memory/docs/audit/showdoc-migration-complete-2026-05-19.md` | ShowDoc 迁移审计 |
| `memory/docs/audit/showdoc-sync-2026-05-14.md` | ShowDoc 同步审计 |

### Bug 报告（bug-reports/）

问题记录和崩溃分析。

完整 Bug 报告索引见 [memory/docs/bug-reports/INDEX.md](memory/docs/bug-reports/INDEX.md)。

| File | 说明 |
|------|------|
| `memory/docs/bug-reports/INDEX.md` | bug-reports 目录索引 |
| `memory/docs/bug-reports/factory-session-orphan-shutdown-crash.md` | Factory session 孤儿崩溃分析 |

### 已归档（archive/）

过时/已完成的历史文档，仅供参考。

完整归档文档索引见 [memory/docs/archive/INDEX.md](memory/docs/archive/INDEX.md)。

| File | 说明 |
|------|------|
| `memory/docs/archive/INDEX.md` | archive 目录索引 |
| `memory/docs/archive/DISPATCH_TEMPLATE.md` | 分派模板 |
| `memory/docs/archive/FIXTURES_VS_REAL.md` | Fixture 与真实数据对比 |
| `memory/docs/archive/MIGRATION_CHECKLIST.md` | 迁移清单 |
| `memory/docs/archive/MIGRATION_FORMAT_SPEC.md` | 迁移格式规范 |
| `memory/docs/archive/MIGRATION_RULES.md` | 迁移规则 |
| `memory/docs/archive/TASK_CARD_TEMPLATE.md` | 任务卡模板 |
| `memory/docs/archive/VALIDATION_COMPLETION.md` | 验证完成报告 |
| `memory/docs/archive/VALIDATION_FINAL.md` | 最终验证报告 |
| `memory/docs/archive/VALIDATION_WAVE1.md` | Wave 1 验证报告 |
| `memory/docs/archive/VALIDATION_WAVE2.md` | Wave 2 验证报告 |

### 其他文件

| File | 说明 |
|------|------|
| `memory/docs/记忆系统全景文档.md` | 记忆系统全景概览 |

---

## Changelog

| Version | Date       | Author | Change                                       |
|---------|------------|--------|----------------------------------------------|
| V4.2    | 2026-08-06 | droid  | 文档引用路径改为项目根相对路径，移除不存在的 design/residue/decisions/research 章节及不存在的 runbooks CI/CD 条目（INFRA-69） |
| V4.1    | 2026-05-26 | droid  | 添加子目录 INDEX.md 交叉引用（design/drafts/plans/runbooks/rfcs/notes/residue/audit/bug-reports/archive） |
| V4.0    | 2026-05-26 | droid  | 按分类重组目录，新增 drafts/plans/runbooks/rfcs/notes/residue/audit/bug-reports |
| V3.0    | 2026-04-27 | codex  | Cleaned up: removed phantom entries, audit checklists, kept only files on disk |
| V2.0    | 2026-04-27 | codex  | Added M8 API completion record               |
| V1.9    | 2026-04-26 | codex  | DES-001~DES-011 marked as 可评审              |
| V1.8    | 2026-04-26 | codex  | Added DES design document series index        |
