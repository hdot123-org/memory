> Date: 2026-08-15
> Source: ci-gateway session，PR #727（INFRA-345）/ PR #726（INFRA-340 follow-up），2026-08-15
> Tags: [lesson, ci-gateway, scanner, auto-merge, pr-race, superseded, dedup]
> Related: [2026-08-15-ci-webhook-pr-zero-fallback]

## scanner 去重 PR 竞态：CI 全绿仍不可合并时，先判 superseded 再决定关单

### 现象

CI 完成通知为 "PR #0"（n8n fallback，同日复发故障，参见 `2026-08-15-ci-webhook-pr-zero-fallback.md`），真实 PR 编号需从 `~/.factory/webhook/locks/pending-ci-*.json` / `ci-complete-*.lock` 文件名或 `gh pr list` 恢复。恢复出真实 PR 为 #727 后，`gh pr checks 727` 显示所有 check 全绿，但 `gh pr merge` 报错 head branch not up to date，分支保护拒绝合并。

### 根因

scanner 对同一份代码（`tests/test_typed_silent_swallow_fixes.py` 中的 `test_binds_exception` 系列重复块）并行生成了两个独立去重 PR：

- #726（`clr/719-typed-silent-silent-dedup`，INFRA-340 follow-up）
- #727（`factory/infra-345-dedup-test-binds-exception`，INFRA-345）

两者都针对完全相同的两个方法（`TestGatewaySyncStatusWrite.test_binds_exception`、`TestGatewayPayloadParse.test_binds_exception`）做去重，且都引入了语义等价但命名不同的 helper 参数（`expected_except` vs `exception_sig`）。#726 在 #727 的 CI 运行期间先经 Auto Merge 管道合入 main（`e6788ec`，2026-08-15T15:36:07Z），导致 #727 相对 main 产生真实内容冲突（同一位置被两个不同签名的重写覆盖）。

Auto Merge 工作流本身没有处理「CI 运行期间 head 落后于 main」的能力：它只记录 `Merge command failed` 便放弃，不会自动 `update-branch` 重试，因此 #727 停留在「check 全绿但无法合并」的悬空状态，只能靠 ci-gateway session 人工核验后处置。

### 处置

1. 判定是否 FULLY SUPERSEDED：逐行对比 main（已含 #726 的改动）与 #727 分支的有效 diff。结论——除参数名 / docstring / 断言措辞等外观差异外，#727 相对 main 的语义增量为零（相同 needle、相同异常签名、相同 window=300）。
2. 中文 comment 说明结论 + 竞态成因 + INFRA-345 处置口径（不动 Linear，GitHub issue 留给 scanner 下次扫描的 `auto_close_resolved()`）。
3. `gh pr close 727 --delete-branch`。全程未 merge、未 `--admin`、未 rebase、未触碰 Linear。
4. 分支 `factory/infra-345-dedup-test-binds-exception`（commit `088b364`，已充分分析确认为 superseded）远程/本地均随 close 一并清除，无需额外 `git branch -D`。

### 判定方法（可复用）

1. **恢复真实 PR 编号**：`ci-complete-*.lock` / `pending-ci-*.json` 文件名尾部数字最快；无 lock 时退回 `gh pr list --state open` 唯一匹配交叉验证。
2. **以现场核验为准**：`gh pr checks <PR>`，不信任通知文本中的状态描述。
3. **合并冲突先本地诊断**：`git merge origin/main --no-edit` 于本地临时验证冲突范围，必要时 `git merge --abort`；**严禁带冲突内容推送**。
4. **逐行对比有效 diff 判断是否 superseded**：只有当 PR 分支相对最新 main 的差异被证明是外观性（命名/措辞）而非语义性（逻辑/断言目标/覆盖范围）时，才能判定为 superseded 并关单；否则应视为需要 rebase 或重新提交的真实冲突，不能直接关闭。

### 预防/后续

- scanner 侧对同一份源文件应避免并行拆出多个目标重叠的去重 PR，建议按文件粒度串行发起或合并 finding 后一次性提交。
- Auto Merge 管道应补充「CI 期间落后于 main」场景的 `update-branch` / 重试能力，而不是失败即放弃、把悬空 PR 留给人工核验。
- main 上 `tests/test_typed_silent_swallow_fixes.py` 仍有 6 处内联 `test_binds_exception`（其中 L153/L198/L216 三处字节级相同）为新范围重复，应由 scanner 出新 finding 处理，沿用 main 现有 `expected_except` helper 签名，不要复活 #727 中的 `exception_sig` 分歧命名。

## Truth Basis

### Source Refs

- 编排器任务描述提供的 truth basis（PR #727/#726 对比结论、竞态时间线）
- ci-gateway session 2026-08-15，本次执行的 `gh pr view/comment/close` 现场输出

### Authority Refs

- AGENTS.md（合并纪律：禁止 `--admin`；Issue 流转约定：GitHub issue 由 scanner `auto_close_resolved()` 自动闭环，Linear 状态流转交给 GitHub↔Linear 自动化）
- ~/.factory/AGENTS.md（CI 失败处理：禁止绕过合并；派发会话关单规矩：走 PR + close/Fixes 闭环，不直接改状态）
- memory/kb/lessons/2026-08-15-ci-webhook-pr-zero-fallback.md（同日 PR #0 fallback 故障，真实 PR 恢复方法一致复用）

### Evidence Refs

- `gh pr view 727 --json state,headRefName,baseRefName` → OPEN / `factory/infra-345-dedup-test-binds-exception` → `main`
- PR #726 mergedAt 2026-08-15T15:36:07Z，main commit `e6788ec`
- PR #727 关单 comment：https://github.com/hdot123/memory/pull/727#issuecomment-5303003603
- `gh pr close 727 --delete-branch` 成功；`git ls-remote --heads origin factory/infra-345-dedup-test-binds-exception` 为空；本地分支同步已不存在
- `gh run list --branch main --limit 1` → Auto Merge workflow, completed/success（2026-08-15T15:51:13Z）

### Conflict Status

- resolved
