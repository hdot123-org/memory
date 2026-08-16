> Date: 2026-08-14
> Source: Linear 门禁回退重触发事件（INFRA-288，PR #642）
> Tags: [lesson, linear, github, linear-gateway, idempotency, pr-linkage]
> Related: [2026-08-11-linear-github-sync-deadlock]

## Linear Gateway 幂等复用：PR 缺失关联导致门禁回退循环

### 背景

INFRA-288（Harden suppression expiry tests for UTC determinism）的工作已通过 PR #642 完成并合并到 main（d38604d），但该 PR body 未包含 `Fixes INFRA-288` 关联。

Linear 侧状态门禁检测到「未检测到 Droid 执行记录（session ID）」，自动将 issue 回退到「进行中」，随后 Issue 触发器重新拉起了 linear-gateway 门铃 —— 同一任务面临二次执行。

### 问题本质

两条独立闭环依赖两个不同信号，缺一即断：

1. **GitHub Issue 自动关闭**：依赖 PR merge 时 scanner 的 `auto_close_resolved()` —— 与 Linear 关联无关
2. **Linear 状态流转**：依赖 PR body 中的 `Fixes INFRA-xxx` 引用 —— PR 缺失该引用则 Linear 永远无法通过 merge 流转为 Done

PR 合并后**事后补关联是否触发 Linear 流转**：待观察（Linear 原生集成通常在 merge 事件时刻解析引用，事后编辑 body 可能不追溯生效）。

### 正确处理路径（本次验证有效）

1. **幂等检查优先**：门铃触发后先 `gh pr list --state all` 按分支/关键词搜索已有 PR，不做任何代码变更
2. **树对比确认**：`git diff <branch-head> <merge-commit> --stat` 为空 → 本地分支内容与 main 完全一致 → 工作确实已完成
3. **在 main 内容上复验**：临时 worktree checkout origin/main，用项目 venv 跑 pytest/mypy/ruff，确认合并结果有效
4. **补关联**：`gh pr edit <PR#> --body` 追加 `Fixes INFRA-xxx` 段落
5. **中文回写**：comment 说明幂等复用情况 + attachmentCreate 附 PR 链接，提示若未自动流转需人工确认
6. **不重复建分支/PR**：重复 webhook 不得导致重复代码变更

### 判别要点

- 门禁 comment「未检测到 Droid 执行记录」≠ 任务未完成，只说明上一次执行未经 Droid session
- 工作是否已完成的判据：**main 上的树内容**，而非 Linear 状态或 PR 关联

### 预防措施

1. **PR 创建时 body 必须含 `Fixes INFRA-xxx`**（linear-gateway skill 已有要求，需严格执行）
2. **门铃处理第一步永远是幂等检查**：`gh pr list --state all` + 现有分支扫描
3. 非 Droid 流程完成的合并（如人工 PR）会触发门禁回退 → 按「幂等复用」路径处理，勿重复执行

## Truth Basis

### Source Refs

- INFRA-288 门禁 comment（2026-08-14T14:43:00Z，状态自动回退「进行中」）
- PR #642 元数据（mergedAt 2026-08-14T14:42:35Z，原 body 无 Fixes 关联）
- `git diff 57da808 d38604d --stat` 为空（本地分支与合并树一致）

### Authority Refs

- AGENTS.md（Issue 流转约定：两条独立闭环路径）
- ~/.factory/skills/linear-gateway/SKILL.md（幂等性规则第 10 节）

### Evidence Refs

- pytest 10/10 通过（main 内容复验，2026-08-14）
- Linear commentCreate d38fd322 / attachmentCreate b3d61ff4 回执

### Conflict Status

- resolved
