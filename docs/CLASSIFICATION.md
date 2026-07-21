# 文档分类决策树

> 本文件是 Droid 文档记录的人类参考文档。
> **路由表以 `memory_core/tools/doc_router.py` 中的 `DOC_CATEGORIES` 为准（single source of truth）。**
> 当用户说"文档记录"、"记一下"、"写个文档"时，按此决策树分类。

## 分类流程图

```
用户说"文档记录"
  │
  ├─ 内容是什么？
  │
  ├─ 服务器/网络/凭证/基础设施？
  │   └─ → docs/infrastructure/
  │       ├─ 服务器资产 → servers.md（追加条目）
  │       ├─ 网络拓扑 → network-topology.md
  │       ├─ 凭证架构 → 1password-mcp.md
  │       └─ 新基础设施 → 新建专题文件
  │
  ├─ 操作步骤/运维手册/故障排查？
  │   └─ → memory/docs/runbooks/
  │       └─ 也同步摘要到 docs/infrastructure/（如果涉及服务器操作）
  │
  ├─ 架构设计/模块设计/API 契约？
  │   └─ → docs/architecture/
  │
  ├─ 协议规格/系统规格/协议文档？
  │   └─ → docs/specs/
  │
  ├─ 决策记录（为什么选 X 而不是 Y）？
  │   └─ → memory/kb/decisions/
  │
  ├─ 教训/经验/踩坑？
  │   └─ → memory/kb/lessons/
  │
  ├─ 重构记录/代码变更记录？
  │   └─ → memory/docs/refactor-logs/
  │
  ├─ 计划/里程碑/执行方案？
  │   └─ → memory/docs/plans/
  │
  ├─ RFC/变更提案？
  │   └─ → memory/docs/rfcs/
  │
  ├─ Bug/崩溃/问题记录？
  │   └─ → memory/docs/bug-reports/
  │
  ├─ Droid 使用技巧/配置指南？
  │   └─ → docs/guides/
  │
  ├─ 临时笔记/调研/待整理？
  │   └─ → memory/docs/notes/
  │
  └─ 不确定？
      └─ → 先放 memory/docs/drafts/，用户后续归类
```

## 快速分类表

| 关键词 | 目标路径 | 说明 |
|--------|---------|------|
| 服务器、IP、端口、部署、Docker | `docs/infrastructure/` | 基础设施资产 |
| 运维、手册、故障、排查、runbook | `memory/docs/runbooks/` | 运维手册 |
| 设计、架构、模块、API 契约 | `docs/architecture/` | 架构设计（tracked） |
| 协议、规格、系统规格 | `docs/specs/` | 协议规格（tracked） |
| 决策、选型、为什么、对比 | `memory/kb/decisions/` | 决策记录 |
| 踩坑、教训、经验、注意 | `memory/kb/lessons/` | 经验教训 |
| 计划、里程碑、排期、TODO | `memory/docs/plans/` | 执行计划 |
| RFC、提案、变更 | `memory/docs/rfcs/` | 变更提案 |
| Bug、崩溃、报错、异常 | `memory/docs/bug-reports/` | 问题记录 |
| Droid、配置、BYOK、模型 | `docs/guides/` | 使用指南 |
| 审计、检查、扫描 | `memory/docs/audit/` | 审计记录 |
| 重构、代码变更、refactor | `memory/docs/refactor-logs/` | 重构日志 |
| 笔记、调研、临时记录 | `memory/docs/notes/` | 临时笔记 |
| 不确定、先记下来 | `memory/docs/drafts/` | 草稿暂存 |

## 双写规则

当文档同时属于两个类别时，**主文档放最具体的类别，在 `docs/` 展示层放摘要引用**：

```
例子：写了一个新的服务器运维 runbook
  → 全文 → memory/docs/runbooks/new-runbook.md
  → 摘要 → docs/infrastructure/（引用 runbook 路径）
```

## 路径分类原则

- **Tracked docs/** (架构、规格、指南) — 公开的项目文档，git tracked
- **memory/docs/** (runbooks、audit、plans、bug-reports) — 实例特定文档，gitignored，运维数据

## 版本

- v1.2 — 2026-07-21 增加 refactor-logs、notes 类别；标注路由表以 DOC_CATEGORIES 为准
- v1.1 — 2026-07-17 更新架构设计和协议规格路由到 tracked docs/
- v1.0 — 2026-06-01 初始版本
