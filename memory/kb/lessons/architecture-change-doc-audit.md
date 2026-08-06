---
title: "架构变更后历史文档需全量审计"
type: lesson
severity: medium
status: accepted
date: 2026-08-01
tags: [documentation, architecture-change, audit, consistency]
---

# 架构变更后历史文档需全量审计

## 问题描述

v0.9.4 将生命周期事件存储从全局单文件 `events.jsonl` 改为按项目按日期分片（`projects/{id}/events/{date}.jsonl`）。代码变更合并后，发现 4 份历史文档仍引用旧的 `events.jsonl` 路径：

1. **PRD-001-PRODUCT-DESIGN.md** — 架构图中使用旧路径
2. **HOOK_INTEGRATION_SPEC.md** — 验证命令查找旧路径
3. **excessive-hook-events.md** — 教训文档描述旧结构
4. **system-remediation-summary.md** — 修复计划引用旧路径

## 根因

架构变更时只关注代码实现，没有同步审计历史文档。文档分散在多个目录（drafts/、system/、kb/lessons/、plans/），没有变更后的文档审计检查清单。

## 解决方案

### 架构变更后必须执行文档审计

```bash
# 搜索所有引用旧路径的文件
rg "events\.jsonl" memory/docs/ memory/kb/ --type md
```

### 审计范围

| 目录 | 审查内容 |
|------|---------|
| `memory/docs/` | 架构图、规范、计划、runbooks |
| `memory/kb/lessons/` | 教训文档中的路径引用 |
| `memory/kb/decisions/` | 决策记录中的影响描述 |
| `README.md` | 安装/验证命令 |

### 审计时机

- **理想**：在同一个 PR 中一起修改（代码 + 文档）
- **现实**：合并后立即执行审计 PR（如本次 PR #233）

## 经验教训

1. **代码变更和文档变更应视为一体** — 架构变更不只是改代码，还包括所有引用旧结构的文档
2. **文档审计需要系统性** — 不能只改当前正在编辑的文件，要全局搜索所有引用
3. **教训文档也需要维护** — `excessive-hook-events.md` 虽然是历史教训，但其中描述的路径也需要随架构变更更新

## 相关 PR

- PR #231: 架构变更（events.jsonl → 分片）
- PR #233: 文档审计修复（4 份文件）

---
**来源：** v0.9.4 生命周期事件分片后的文档一致性审计
**日期：** 2026-08-01

## Truth Basis

### Source Refs

- memory/docs/记忆系统全景文档.md

### Authority Refs

- memory/kb/global/memory-system.md
- memory/kb/global/kb-format-spec.md
- project-map/INDEX.md

### Evidence Refs

- tests/test_discover_canonical_files.py
- tests/test_consistency_check.py
- memory_core/tools/consistency_check.py

### Conflict Status

- resolved

