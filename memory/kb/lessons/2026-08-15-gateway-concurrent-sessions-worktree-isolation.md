> Date: 2026-08-15
> Source: INFRA-344 linear-gateway 会话（factory 会话；并发方为 INFRA-345 会话 / PR #727）
> Tags: [lesson, linear-gateway, git-worktree, 并发会话, concurrency, 运维流程]
> Related: [worker-commit-to-main-divergence]

## 教训：并发网关会话共用本地检出导致分支被切走 — 用 worktree 隔离

### 现象

INFRA-344 会话在 `~/memory` 共享检出上创建 feature 分支并有未提交修改时，并发的 INFRA-345 会话（PR #727）在同一检出执行了 checkout main → pull --ff-only → reset --hard。后果：

- 当前 feature 分支被切回 main，随后 commit 触发 pre-commit「禁止直接 commit 到 main」拦截
- 未提交修改险些被 reset --hard 清除 — 因已 `git add` 进 index 而幸存

### 根因

多个 linear-gateway 会话共享同一 repoPath（`~/memory`）。git 检出的 HEAD / index / worktree 是进程间共享的单一状态，无任何并发保护：任一会话的 checkout / reset 操作都会即时影响所有正在使用该检出的会话。

### 教训

1. 网关会话不应在共享检出上直接 `checkout -b` 干活。linear-gateway skill 的 `git worktree add ~/factory/runs/{issueRef}-{timestamp}` 写法才是并发安全的正确路径
2. 修改尽早 `git add` 进 index — staged 内容更抗 reset --hard（本次即因此幸存）
3. 发现分支被切走时，先查 `git reflog` + `git status --short` 再恢复；注意 `M `（staged）与 ` M`（unstaged）的列位差异，误读会漏判 index 中幸存的修改

### 行动项

- 网关会话默认 worktree 隔离执行，共享检出仅作只读使用
- 中途 HEAD 被异动的恢复链路：`git diff --cached > patch` → 恢复共享树 → worktree 内 `git apply` → 在 worktree 内提交推送

## Truth Basis

### Source Refs

- INFRA-344 linear-gateway 会话（factory 会话，2026-08-15）编排器提供的任务上下文

### Authority Refs

- linear-gateway skill（`git worktree add ~/factory/runs/{issueRef}-{timestamp}` 并发隔离写法）
- memory/kb/INDEX.md（lessons/ 为 active section）
- AGENTS.md（「禁止直接推送 main」/ pre-commit 拦截背景）

### Evidence Refs

- PR #727（INFRA-345 会话产物；触发共享检出 checkout main → pull --ff-only → reset --hard 的并发方）
- PR #728 / commit ef3f7d4（INFRA-344 产物；经隔离 worktree `~/factory/runs/infra-344` 完成提交）
- memory/log/2026-08-15.md「INFRA-344 linear-gateway 执行（factory 会话）」条目（同日事实记录）

### Conflict Status

- resolved
