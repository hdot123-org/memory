> Date: 2026-08-16
> Source: ci-gateway CI 完成通知「PR #731 failure」（本 session 2026-08-16 03:25–03:53 UTC 处理完毕）
> Tags: [lesson, ci-gateway, ci-ok, droid-review, timeout, race, runner-queue, auto-merge, gh-run-rerun]
> Related: [2026-08-15-ci-webhook-pr-zero-fallback, webhook-session-routing]

## ci-ok 轮询窗口与 droid-review 总时长赛跑：超时假阴性失败的正确恢复路径

### 现象

ci-gateway session 收到注入通知：

> CI 完成通知：PR #731 状态为 failure。

现场核验 `gh pr checks 731`：**仅 ci-ok 为 fail（1h0m15s），droid-review 为 pending，其余全部 check 通过**（test 3.12 / qa-ok / boundary / coverage / mypy --strict 等）。

### 根因链

1. droid-review workflow run 31921608592 于 02:18:47Z 创建，但 job 因 GitHub-hosted runner（ubuntu-latest）分配延迟 **排队约 46 分钟**，03:04:53Z 才启动
2. "Run Droid Auto Review" 步骤实际运行 37m52s（Qwen 3.7 Plus via Kong BYOM，大 PR 属正常时长）
3. ci-ok 内嵌的 droid-review 轮询器预算为 **120 次 × 30s = 60 分钟**，在 03:22:14Z 耗尽并退出非零 —— 早于 review 完成时间（约 03:45Z）
4. 即：**ci-ok 轮询预算（60 min）< droid-review 总耗时（排队 46 min + 运行 38 min ≈ 84 min）**，纯属时序竞争，非代码缺陷、非审查发现

ci-ok job log 的判定证据（`gh run view --job <id> --log`）：

```
Attempt 120/120: ... droid-review conclusion: pending
⚠ droid-review not complete after 120 attempts
##[error]Process completed with exit code 1.
```

### 已验证有效的恢复序列（本次全流程走通）

1. 确认 droid-review job 在真实运行（`--json jobs` 看 step 状态），而非 check run 幽灵 pending
2. **等待 droid-review 完成**（分片轮询，勿死等单条命令）
3. 完成且 conclusion=success 后：`gh run rerun <ci-run-id> --failed` 只重跑 ci-ok —— 此时轮询第一次查询即命中已完成结论，**5 秒内通过**
4. ci-ok 绿后 "Auto-merge PR" workflow 自动合并（本例 mergedAt 03:46:27Z，merge commit e7e5f85）并自动删除远程分支
5. 合并后三件事：main CI 确认 success、本地 `git pull --ff-only` 同步、pending-ci.json 清理（本例已不存在）

### 关键教训

1. **「ci-ok fail + droid-review pending + 其余全绿」是超时假阴性的指纹**。先读 ci-ok job log 找 "not complete after N attempts" 证据，区分「代码失败 / 审查发现」与「时序超时」，再决定动作。
2. **恢复动作是 rerun，不是改代码**；顺序必须「先等 droid-review 完成，再 rerun ci-ok」—— 顺序颠倒会让 60 分钟轮询窗口从头计起，必然再次超时。
3. **结构缺陷**：ci-ok 轮询预算必须覆盖 droid-review 最坏（排队+运行）时长。改进方向：加长窗口、或耗尽时对 pending 判 inconclusive（挂起人工/自动重试）而非直接 fail（待跟进，属 ci.yml）。
4. 本次触发器是 ubuntu-latest 排队 46 分钟 —— GitHub-hosted runner 分配延迟会随平台负载波动，60 分钟固定预算不可靠。
5. 本地 feature 分支可能被部署 worktree 占用（本例 `/private/tmp/deploy-sync-workspace`），远程分支删除与本地分支删除解耦处理，勿强拆 worktree。

## Truth Basis

### Source Refs

- 本 session 2026-08-16 03:25–03:53 UTC ci-gateway 事件（PR #731 / feat: webhook 脚本版本化与同步基础设施 m1 地基）
- GitHub Actions run 31921608592（droid-review）、31921609579（ci，ci-ok job 95102516671）、31925045083（main push CI）

### Authority Refs

- AGENTS.md（合并纪律：CI 失败不得继续、禁止 --admin、ci-ok 门禁含 droid-review）
- ~/.factory/skills/ci-gateway/SKILL.md（步骤 3b：droid-review 卡住/超时的处理路径）

### Evidence Refs

- ci-ok job log：Attempt 120/120 pending → exit 1（03:22:14Z）
- droid-review：job startedAt 03:04:53Z（创建 02:18:47Z），37m52s conclusion=success
- rerun 后 ci-ok 5s success；PR #731 mergedAt 2026-08-16T03:46:27Z sha=e7e5f85df4da85a9ccc32ac85fcc72018de2ef7a
- PR comment（阻塞记录）：pull/731#issuecomment-5305524044

### Conflict Status

- resolved
