# 全局知识文档索引

> 本目录是 memory-core 仓库的展示层，AutoWiki 扫描此目录生成 Factory App Wiki。
> 运行时路由仍由 `memory/kb/` 和 `memory/docs/` 负责。

## 目录结构

### architecture/ — 架构设计
memory-core 架构系列文档，包括整体架构、网关、核心装配、接口、适配器、策略治理、数据管道等。

| 文件 | 说明 |
|------|------|
| [01-architecture.md](architecture/01-architecture.md) | 整体架构设计 |
| [02-gateway.md](architecture/02-gateway.md) | 网关层设计 |
| [03-core-assembly.md](architecture/03-core-assembly.md) | 核心装配 |
| [04-interfaces.md](architecture/04-interfaces.md) | 接口定义 |
| [05-implementations.md](architecture/05-implementations.md) | 实现层 |
| [06-adapters.md](architecture/06-adapters.md) | 适配器 |
| [07-policy-governance.md](architecture/07-policy-governance.md) | 策略与治理 |
| [08-data-pipeline.md](architecture/08-data-pipeline.md) | 数据管道 |
| [09-provider-fallback.md](architecture/09-provider-fallback.md) | Provider 回退 |
| [10-consumer-boundary.md](architecture/10-consumer-boundary.md) | 消费端边界 |
| [API-CONTRACT.md](architecture/API-CONTRACT.md) | API 契约 |

### specs/ — 协议规格
memory-core 协议规格文档，定义 .memory/ 协议的行为规范。

| 文件 | 说明 |
|------|------|
| [BOUNDARY.md](specs/BOUNDARY.md) | 边界定义 |
| [DOT_MEMORY_SPEC.md](specs/DOT_MEMORY_SPEC.md) | .memory/ 协议规格 |
| [MEMORY_LOCK_SPEC.md](specs/MEMORY_LOCK_SPEC.md) | 内存锁规格 |
| [MULTI_PROJECT_SCAN_SPEC.md](specs/MULTI_PROJECT_SCAN_SPEC.md) | 多项目扫描规格 |

### infrastructure/ — 基础设施
服务器资产、网络拓扑、凭证架构等基础设施文档。

| 文件 | 说明 |
|------|------|
| [servers.md](infrastructure/servers.md) | 服务器资产清单 |
| [1password-mcp.md](infrastructure/1password-mcp.md) | 1Password Connect MCP 架构 |

### guides/ — 使用指南
Droid 使用、模型配置、Droid Computer 管理等指南。

| 文件 | 说明 |
|------|------|
| [droid-computers.md](guides/droid-computers.md) | Droid Computer 管理指南 |
| [byok-models.md](guides/byok-models.md) | 自定义模型配置指南 |
| [observability-and-error-tracking.md](guides/observability-and-error-tracking.md) | 可观测性和错误追踪概述 |

### CLASSIFICATION.md — 文档分类决策树
写入文档时的分类指引，Droid 每次"文档记录"时参照此文件。

## 与 memory/ 目录的关系

```
docs/                  ← 展示层（AutoWiki 可见，git tracked）
  architecture/        ← 架构设计文档
  specs/               ← 协议规格文档
  infrastructure/      ← 基础设施知识摘要
  guides/              ← 使用指南
  CLASSIFICATION.md    ← 分类决策树

memory/                ← 运行时知识层（gitignored，实例特定）
  kb/infra/            ← 基础设施知识详情
  kb/global/           ← 全局规则
  docs/design/         ← 实例特定设计文档（REF-000/001、审计报告等）
  docs/runbooks/       ← 运维手册
  docs/plans/          ← 执行计划
  docs/audit/          ← 审计记录
  docs/bug-reports/    ← Bug 记录
  ...
```

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-17 | 添加 architecture/ 和 specs/ 目录条目，更新 memory/ 关系图 |
| 2026-06-01 | 初始创建，迁移基础设施文档 |
