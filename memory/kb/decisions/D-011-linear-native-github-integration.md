# D-011: Linear 原生 GitHub 集成替代自定义脚本

| Field | Value |
|-------|-------|
| ID | D-011 |
| Status | accepted |
| Date | 2026-08-01 |

## 背景

Factory 水轮 SDLC 循环需要 GitHub PR 事件自动驱动 Linear issue 状态流转。最初方案是自定义脚本 `github-linear-sync.sh`,通过 webhook 接收 GitHub PR 事件,调 Linear GraphQL API 更新 issue 状态。

调查发现 Linear 提供原生 GitHub App 集成,支持 PR 关联 + 状态自动流转,且 workspace 已完成连接配置。

## 决策

**停用自定义 `github-linear-sync.sh`,全面采用 Linear 原生 GitHub 集成。**

### 原因

1. **功能完备**: 原生集成已覆盖全部所需状态流转 (verified)
2. **零维护**: Linear 官方维护,无需本地脚本
3. **消除竞态**: 自定义脚本与原生集成同时响应同一事件,产生冗余 API 调用和潜在状态冲突
4. **更丰富的关联**: 原生集成自动添加 PR attachment、linkback comment,脚本只改 state

## 验证证据

### 干净测试 (github-linear-sync.sh 已禁用)

| 测试 | Issue | 操作 | 结果 |
|------|-------|------|------|
| PR open → In Progress | INFRA-13 | 创建 PR #238 | Triage → In Progress ✅ |
| PR merge → Done | INFRA-13 | 合并 PR #238 | In Progress → Done ✅ |
| PR attachment 自动关联 | INFRA-13 | PR 创建后 | [github] attachment 自动添加 ✅ |
| PR linkback comment | INFRA-10 | PR #236 | `<!-- linear-linkback -->` ✅ |

### 4 个 Team 全部配置

| Team | start → | review → | merge → |
|------|---------|----------|---------|
| INFRA | In Progress | In Review | Done |
| GW | In Progress | In Review | Done |
| WORKBOT | In Progress | In Review | Done |
| DEFAULT | In Progress | In Review | Done |

## 变更内容

- `hooks.json`: 移除 `github-linear-sync` hook 条目
- `github-linear-sync.sh`: 保留文件作为存档,不再执行
- 状态流转: 完全由 Linear GitHub App 原生处理

## 风险

- Linear 原生集成不支持 "PR closed without merge → Backlog" (自定义脚本有此规则)
- 如需该行为,可在 Linear team settings 中添加对应规则,或重新启用脚本
