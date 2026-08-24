# INFRA-538 闭环记录：M2 代码修复与 CI 解除阻塞

- **日期**: 2026-08-24
- **状态**: 已完成（代码经 PR #1005 合入 main，本 PR 补 Linear 引用闭环）
- **类型**: 运维记录 / issue 闭环

## 背景

INFRA-538 要求修复三项 M2 scrutiny R1 代码缺陷以解除 CI 阻塞：

1. `reconcile-evolution.sh` 使用 gh 不存在的 JSON 字段（`status`/`conclusion`/`pushedAt`）
2. `trigger-ci-droid.sh` 的 sessions-index mtime 为毫秒纪元，72h 新鲜度门恒真
3. `verify_scanner_identity` 调用 `gh pr view` 缺 `-R` 标志，交叉校验永远走保守路径

## 执行发现（Factory Droid 核查）

三项修复在 issue 创建前已由 PR #1005（commit `47e0522`，2026-08-24 09:08 +0800 合入）落地 main：

| 修复项 | 位置 | 状态 |
|--------|------|------|
| A. gh 字段名 | `webhook-scripts/reconcile-evolution.sh:112-114,141-143` | 已修复（`state`/`completedAt`/`commits[-1].committedDate`） |
| B. mtime 毫秒归一 | `webhook-scripts/trigger-ci-droid.sh` `check_sessions_index_fresh` | 已修复（`mtime > 1e12 → /= 1000`） |
| C. scanner repo 上下文 | `webhook-scripts/trigger-ci-droid.sh` `verify_scanner_identity` | 已修复（从 `PENDING_CWD` 推导 repo slug 传 `-R`） |

PR #1005 报告的验证结果：pytest 69/69 通过、shellcheck 全绿、含 3 项新增测试。

issue 仍处「进行中」的根因：PR #1005 body 未含 `Fixes INFRA-538` 引用，Linear 自动闭环未触发。

## 闭环动作

1. 独立核查 main（`47e0522`）三处代码确认修复在位
2. 确认 main CI 全绿（run 32678851378，CI success）
3. 创建引用分支 `factory/infra-538-ci-closure`，PR body 含 `Fixes INFRA-538`
4. 合并后由 GitHub ↔ Linear 自动化将 issue 流转为 Done

## 残留观察

`scripts/repo_health_check.sh:233` 的 `gh run list --json status,conclusion` 是 `gh run list` 的合法字段，与本次修复的 `gh pr checks/view` 字段问题无关，无需处理。
