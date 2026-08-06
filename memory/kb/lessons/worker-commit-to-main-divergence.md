# Worker 直接 Commit 到 Main 导致分支 Diverge

**日期**: 2026-08-05
**严重性**: P1（重复发生 4+ 次）
**状态**: 已确认根因，需要 pre-commit hook 修复

## 问题描述

Mission worker 多次直接在 `main` 分支上 commit，然后将该 commit push 到远程 feature branch。当 GitHub squash merge 该 PR 时，remote main 产生新 commit，但本地 main 仍持有原始 commit，导致 `git merge` / `gh pr merge` 无法 fast-forward。

## 根因

`git reflog main` 清楚显示了重复模式：

```
1ffe055 main@{1}: reset: moving to origin/main     ← 手动修复
a8bc1f6 main@{2}: commit: fix: 根治 SIGINT 崩溃      ← Worker 直接 commit 到 main!
cf5d191 main@{3}: pull origin main: Fast-forward    ← Worker 运行前的干净状态
```

至少 4 次重复：
| # | Commit | PR | 修复方式 |
|---|--------|----|---------|
| 1 | `a8bc1f6` SIGINT 修复 | #300 | `reset --hard origin/main` |
| 2 | `359d91e` branch-cleanup 修复 | #289 | `reset --hard origin/main` |
| 3 | `48f9da4` INFRA-37 文档 | #277 | `reset` |
| 4 | `2e8ae57` redaction 合并 | - | `reset --hard origin/main` |

## 为什么会发生

1. Worker session 启动时，本地在 `main` 分支
2. Worker 实现代码后，**先 commit 再创建 feature branch**（或根本不创建 branch）
3. Commit 直接落在 main 上
4. Worker 把 main 上的 commit push 到远程 feature branch
5. GitHub PR squash merge 创建新 commit → 本地 main diverge

## 正确流程

```
1. git checkout -b fix/xxx     ← 先创建分支
2. 修改代码
3. git add && git commit        ← commit 在 feature branch 上
4. git push origin fix/xxx
5. gh pr create
6. gh pr merge --squash --delete-branch
7. git checkout main && git pull --ff-only origin main  ← 可以 fast-forward
```

## 修复方案

### 1. Pre-commit Hook（主要修复）

重写 `.git/hooks/pre-commit`：
- 当前分支是 `main` → 阻止 commit，提示创建 feature branch
- 当前分支是 `fix/*` / `feat/*` 等 → 允许 commit

### 2. Worker Skill 更新

在所有 worker skill 中明确第一步必须是 `git checkout -b <branch>`，不得在 main 上 commit。

## 影响范围

- 所有 mission worker session
- 任何在本地 main 上直接 commit 的操作

## Truth Basis

### Source Refs
- memory/docs/记忆系统全景文档.md

### Authority Refs
- memory/kb/global/memory-system.md
- project-map/INDEX.md

### Evidence Refs
- tests/test_business_policy_paths.py

### Conflict Status
- resolved
