> Date: 2026-08-12
> Source: CI/CD 自动化三个修复（INFRA-209 / INFRA-211 / INFRA-212）
> Tags: [lesson, ci-cd, github-actions, auto-merge, github-token, bootstrap]
> Related: [2026-08-12-auto-merge-trigger-strategy]

## 教训 A：GitHub GITHUB_TOKEN 抑制 check_run 事件

### 问题现象

auto-merge workflow 配置了 `check_run: completed` 触发器，期望 CI 完成后自动合并 PR。但 50 次 auto-merge 运行中，0 次由 `check_run` 事件触发——该 workflow 永远不会自动运行。

### 根因

GitHub 的防递归机制：使用 `GITHUB_TOKEN` 创建的 check suite 在完成后，**不会发出 `check_run` 事件**。这是 GitHub 官方文档记载的行为，目的是防止 CI workflow 触发自身形成无限循环。

但 auto-merge 不是 CI workflow 本身，它依赖 CI 完成的 `check_run` 事件——而 CI check suite 是用 `GITHUB_TOKEN` 跑的，所以事件被抑制。

### 证据

- 50 次 auto-merge 运行记录中，触发源统计：`check_run` 触发 = 0 次，`workflow_dispatch` 手动触发 = 50 次
- 3 个模型独立分析该问题，2/3 一致确认根因为 GITHUB_TOKEN 抑制机制
- [GitHub 官方文档](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#check_run) 明确记载此限制

### 解决方案

改用 `workflow_run` + `schedule` 双触发：
- `workflow_run` 监听 CI workflow 完成事件，不受 GITHUB_TOKEN 抑制
- `schedule` 每 5 分钟轮询兜底，防止 `workflow_run` 遗漏的边缘情况

### 教训

1. **GITHUB_TOKEN 创建的 check 不发出 check_run 事件** —— 依赖 `check_run: completed` 触发下游 workflow 是死路
2. **`workflow_run` 是正确的替代方案** —— 它监听的是 workflow 级别完成事件，不受 token 抑制
3. **始终加 `schedule` 兜底** —— 即使主触发器正确，GitHub 事件系统也有遗漏可能，轮询兜底是必要的防御性设计

---

## 教训 B：鸡生蛋 bootstrap 问题

### 问题现象

修复 auto-merge 的 PR（#519）本身也无法通过 auto-merge 合并——因为 main 分支上还是旧代码，`check_run` 事件依然不会来。修复代码在 PR 里，PR 合不了，修复就生效不了。

### 根因

这是经典的"鸡生蛋"问题：auto-merge 修复依赖 auto-merge 自身运行，但 auto-merge 当前是坏的。

### 解决方案

一次性 `workflow_dispatch` 手动触发合并修复 PR 自身。这是一次性操作——PR 合并后新代码进入 main，`workflow_run` 触发器生效，此后 auto-merge 可以自驱动。

### 教训

1. **修复自动化工具自身的 PR 往往无法用该工具合并** —— 需要预先规划手动操作
2. **bootstrap 问题不可回避** —— 必须有一次手动触发将修复代码推入 main，没有捷径
3. **在规划自动化修复时，预先确认该修复能否通过自身自动化流程合并** —— 不能则计划手动步骤

## Truth Basis

### Source Refs

- GitHub Actions 官方文档（check_run event 限制）
- auto-merge workflow 运行记录（50 次，0 次 check_run 触发）

### Authority Refs

- project-map/INDEX.md
- memory/kb/global/memory-system.md

### Evidence Refs

- `.github/workflows/` auto-merge workflow 配置
- PR #519, Issue #518, Linear INFRA-212
- PR #517, Issue #516, Linear INFRA-211
- PR #514, Issue #513, Linear INFRA-209

### Conflict Status

- resolved
