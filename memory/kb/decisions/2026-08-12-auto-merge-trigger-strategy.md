# auto-merge 触发策略从 check_run 改为 workflow_run + schedule

## 状态
accepted

## 日期
2026-08-12

## 背景

auto-merge workflow 原配置 `check_run: completed` 触发器，期望 CI 全绿后自动合并符合条件（标签 + 分支保护检查通过）的 PR。但该触发器从未实际触发——50 次运行全部为手动 `workflow_dispatch`。

根因：GitHub 使用 `GITHUB_TOKEN` 创建的 check suite 完成后**不发出 `check_run` 事件**（防递归机制）。auto-merge 依赖的 CI check 恰好由 `GITHUB_TOKEN` 驱动，因此事件被永久抑制。

详见经验教训：`lessons/2026-08-12-ci-cd-automation-fixes.md`（教训 A）。

## 决策

将 auto-merge 触发策略从单一 `check_run` 改为 **`workflow_run` + `schedule` 双触发**。

### 方案对比

| 维度 | 旧方案 | 新方案 |
|------|--------|--------|
| 触发器 | `check_run: completed` | `workflow_run` + `schedule` |
| 问题 | GITHUB_TOKEN 抑制事件，永不触发 | `workflow_run` 不受 token 抑制 |
| 兜底 | 无 | `schedule` 每 5 分钟轮询 |
| 可靠性 | 0% 自动触发（50/50 手动） | 主触发器可靠 + 轮询兜底 |

### 新方案细节

- **`workflow_run`**：监听 CI workflow（ci.yml）的 `completed` 事件，类型为 `success`。此事件在 workflow 层面发出，不受 `GITHUB_TOKEN` check 抑制。
- **`schedule`**：每 5 分钟（`*/5`）轮询一次，作为 `workflow_run` 的兜底。覆盖 GitHub 事件系统偶发遗漏。
- **幂等设计**：两次触发同时运行时，auto-merge 逻辑检查 PR 是否已合并，避免重复操作。

## 理由

1. **`workflow_run` 是 GitHub 官方推荐的下游 workflow 触发方式** —— 专为"一个 workflow 完成后触发另一个"场景设计
2. **`schedule` 兜底是防御性最佳实践** —— GitHub 事件系统非 100% 可靠，轮询兜底消除单点故障
3. **改动面小** —— 仅触发器配置变更，auto-merge 合并逻辑不变

## 影响

- auto-merge workflow 触发器配置变更
- CI 全绿后 PR 自动合并延迟从"无限（不触发）"降低到"最多 5 分钟"
- 需一次性手动 `workflow_dispatch` 合并此修复 PR 自身（bootstrap 问题，详见教训 B）

## PR / Issue

- PR: #519
- Issue: #518
- Linear: INFRA-212

## Truth Basis

### Source Refs

- GitHub Actions 官方文档（workflow_run event, check_run event 限制）
- auto-merge workflow 运行记录

### Authority Refs

- project-map/INDEX.md

### Evidence Refs

- `.github/workflows/auto-merge.yml`（触发器配置变更）
- `memory/kb/lessons/2026-08-12-ci-cd-automation-fixes.md`（教训 A + B）

### Conflict Status

- resolved
