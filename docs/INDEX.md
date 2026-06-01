# 全局知识文档索引

> 本目录是 memory-core 仓库的展示层，AutoWiki 扫描此目录生成 Factory App Wiki。
> 运行时路由仍由 `memory/kb/` 和 `memory/docs/` 负责。

## 目录结构

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

### CLASSIFICATION.md — 文档分类决策树
写入文档时的分类指引，Droid 每次"文档记录"时参照此文件。

## 与 memory/ 目录的关系

```
docs/                  ← 展示层（AutoWiki 可见）
  infrastructure/      ← 基础设施知识摘要
  guides/              ← 使用指南
  CLASSIFICATION.md    ← 分类决策树

memory/                ← 运行时知识层（Droid 实际读取）
  kb/infra/            ← 基础设施知识详情
  kb/global/           ← 全局规则
  docs/design/         ← 架构设计
  docs/runbooks/       ← 运维手册
  docs/plans/          ← 执行计划
  ...
```

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-06-01 | 初始创建，迁移基础设施文档 |
