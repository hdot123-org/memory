> Date: 2026-08-16
> Source: ci-gateway PR #733 合并流程（本 session 2026-08-16 处理完毕）
> Tags: [lesson, auto-merge, behind, update-branch, strict-up-to-date, branch-protection, deadlock, ci-gateway]
> Related: [2026-08-16-ci-ok-droid-review-timeout-race, 2026-08-15-ci-webhook-pr-zero-fallback]

## strict up-to-date 保护下 BEHIND 分支的 auto-merge 无限期挂死

### 现象

PR #733（分支 `feat/ci-droid-review-timeout-hardening`，"fix: droid-review CI 防挂死加固"）**19 项 check 全绿**（含 droid-review 8m46s、ci-ok 6m10s），仓库自身 Auto Merge 自动化已于 04:51:22Z 启用 GitHub 原生 auto-merge（SQUASH + delete-branch，由 hdot123/DISPATCH_TOKEN 触发），但 PR 无限期挂起、无法合并。

### 根因链

1. main 前移（release 0.31.0 #734 等已合入）→ head 分支 `mergeStateStatus=BEHIND`
2. 自动化链路：`.github/workflows/auto-merge.yml`（触发：workflow_run / pull_request_target / schedule */10 / workflow_dispatch）→ 共享 action `hdot123/shared-workflows/auto-merge@5a0fc1b`
3. 该 action 仅在「PR OPEN + 所有 check 完成且通过 + mergeable」时执行 `gh pr merge --squash --delete-branch`；被 BEHIND 拒绝后回退为启用 GitHub 原生 auto-merge
4. **链路任何环节都不调用 `gh pr update-branch`，而 GitHub 原生 auto-merge 也不会自动同步 BEHIND 分支** —— 在 strict up-to-date 分支保护下，形成死锁模式：已启用 auto-merge 的 PR 在 main 前移后无限期挂起，无任何自动机制解除

### 已验证有效的解法（本次全流程走通，未用 --admin）

1. 编排层 ci-gateway 流程执行 `gh pr update-branch 733`：main → feature 标准 merge commit，新 head `c992e234536fc21ae21d635e90ae8b0b0273facb`，无冲突
2. CI 重跑全绿后，原生 auto-merge 自动完成合并
3. 全程未使用 `--admin`（合并纪律铁律）

### 关键教训

1. **「check 全绿 + 原生 auto-merge 已启用 + 长时间不合并」是 BEHIND 死锁的指纹**。排查时先查 `mergeStateStatus`，而非怀疑 check 或审查状态。
2. **恢复动作是 `gh pr update-branch`，不是重新启用 auto-merge 或绕过保护**。更新分支 → CI 重跑 → 原生 auto-merge 自动接管，全程可在不违反合并纪律的前提下完成。
3. **结构缺陷**：auto-merge 链路假设「check 绿 = 可合并」，漏掉了 strict up-to-date 下 BEHIND 这一独立维度；原生 auto-merge 的启用条件也不包含分支同步。

### 改进方向（供后续决策，本次未实施）

1. 共享 action 在启用原生 auto-merge 前检测 `mergeStateStatus=BEHIND` 并先执行 `gh pr update-branch`
2. 或在 auto-merge.yml 的 schedule 任务中增加对 BEHIND 状态 auto-merge PR 的定期 sweep 更新
3. 或评估放宽 strict up-to-date 保护（需权衡，涉及合并纪律）

## Truth Basis

### Source Refs

- 本 session 2026-08-16 ci-gateway PR #733 合并流程实证
- `.github/workflows/auto-merge.yml`（本仓库）与共享 action `hdot123/shared-workflows/auto-merge@5a0fc1b`

### Authority Refs

- AGENTS.md（合并纪律铁律：禁止 --admin；CI 失败不得继续；分支保护 strict up-to-date）
- ~/.factory/skills/ci-gateway/SKILL.md（PR 合并网关流程）

### Evidence Refs

- PR #733：19 项 check 全绿（droid-review 8m46s、ci-ok 6m10s）
- 原生 auto-merge 于 2026-08-16T04:51:22Z 由 hdot123/DISPATCH_TOKEN 启用（SQUASH + delete-branch）
- main 前移证据：release 0.31.0 (#734) 等已合入 main
- `gh pr update-branch 733` 后新 head `c992e234536fc21ae21d635e90ae8b0b0273facb`（标准 merge commit，无冲突），CI 重跑全绿后原生 auto-merge 自动完成合并，全程未用 `--admin`
- 关联教训：memory/kb/lessons/2026-08-16-ci-ok-droid-review-timeout-race.md（同属 2026-08 风暴期 CI 链路稳定性问题；PR #733 本身即 droid-review 防挂死加固修复，本次挂起是链路中另一个独立盲点的实证）

### Conflict Status

- resolved
