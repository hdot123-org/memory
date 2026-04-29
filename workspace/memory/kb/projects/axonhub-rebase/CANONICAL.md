---
type: [KB:PROJECT]
title: "AxonHub Rebase Project Canonical"
shortname: AXONHUB-REBASE
status: active
created: 2026-04-29
updated: 2026-04-29
scope: project
source: local-canonical
confidence: high
tags: [axonhub, rebase, security-fix, upstream-merge]
related: [projects-spec]
---

# AxonHub Rebase Project Canonical

## 目标

将 hdot123/axonhub fork 上已完成的 100 项 F-D 安全修复迁移到上游 looplj/axonhub 的最新 unstable 分支之上。

## 仓库

| 位置 | 路径 |
|------|------|
| 本地仓库 | `/Users/busiji/tool/axonhub` |
| fork（origin） | `https://github.com/hdot123/axonhub` |
| 上游（upstream） | `https://github.com/looplj/axonhub` |

## 分支模型

- `branch-1`：稳定主线，与 GitHub 对齐
- `branch-2`：任务分支，从 branch-1 或 upstream/unstable 创建，任务完成后删除

## 基线

| 端 | commit | 说明 |
|----|--------|------|
| 上游基线 | `9acca6be` | `upstream/unstable` HEAD |
| 我们的基线 | `65eb7783` | 旧上游 HEAD，我们的修复基于此 |
| origin/branch-1 | `b0c3fedd` | 当前稳定线，38 commits |

## 技术栈

- Go 1.26+, Ent ORM, gqlgen, Gin, FX
- 独立 Go module: `llm/`
- 前端: React 19 + TypeScript

## CE-01 部署

- 服务器: `ce-01`（REDACTED_IP）
- 仓库路径: `/root/axonhub-ci/`
- Docker: postgres 16 + axonhub-app（端口 8090）
- 用途: L2 通过后的远程编译 + 测试 + Docker 部署验证

## 项目文件

| 文件 | 位置 | 用途 |
|------|------|------|
| 计划 | `kb/projects/axonhub-rebase/PLAN.md` | 完整计划（不动） |
| 状态 | `kb/projects/axonhub-rebase/STATE.md` | 执行状态（持续更新） |
| 工作副本-计划 | `/Users/busiji/tool/REBASE-PLAN.md` | 本地工作副本 |
| 工作副本-状态 | `/Users/busiji/tool/REBASE-STATE.md` | 本地工作副本 |
| 看板 | https://github.com/users/hdot123/projects/15 | 主线程任务指令卡 |

## Worker 分工

W1-W5 并行（ent层/orchestrator层/biz层/llm层/gql层+CI），W6 串行收尾（测试+go generate+全量验证）。

## 冲突概况

41 个重叠文件，4 个重度、8 个中度、29 个轻度。详见 PLAN.md。

## 验收流程

L1（Worker级）→ L2（集成）→ CE-01（远程部署）→ L3（最终）→ P1（merge+push）

## Truth Basis

### Source Refs
- `/Users/busiji/tool/REBASE-PLAN.md`
- `/Users/busiji/memory/workspace/memory/kb/global/projects-spec.md`

### Authority Refs
- `/Users/busiji/tool/REBASE-STATE.md`

### Conflict Status
- `active`
