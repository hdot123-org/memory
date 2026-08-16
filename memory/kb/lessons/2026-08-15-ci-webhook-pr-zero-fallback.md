> Date: 2026-08-15
> Source: ci-gateway CI 完成通知「PR #0」异常（本 session 2026-08-15 19:38 处理完毕；真实 PR #707 / INFRA-331）
> Tags: [lesson, webhook, ci-gateway, n8n, pr-number, fallback, auto-merge, gh-pr-checks]
> Related: [webhook-session-routing]

## CI webhook「PR #0」fallback 异常：通知文本不可信，合并决策只认现场核验

### 现象

ci-gateway session 收到的 CI 完成通知注入消息为：

> CI 完成通知：PR #0 状态为 success。如果 CI 通过请检查并合并此 PR。

GitHub PR 编号从 #1 开始，PR #0 是无效编号。同日该异常至少出现 3 次（daily report Session 2 / Session 315 / 本 session），是复发型故障而非偶发。

### 根因链

1. n8n webhook 侧 PR 编号字段缺失或解析失败，**以 0 作为默认值**传给 `trigger-ci-droid.sh`
2. 脚本对 PR_NUMBER=0 查找 `pending-ci-0.json`，文件不存在
3. 走 fallback 注入路径，消息模板直接拼出 "PR #0"

即：该通知中的 PR 编号与「状态为 success」都是 fallback 产物，不携带真实信息。

### 真实 PR 定位方法（本次验证有效）

按优先级：

1. `ls -t ~/.factory/webhook/locks/ci-complete-*.lock | head -3` — 最新 lock 文件名尾部的数字即真实 PR 编号。本次为 `ci-complete-f511031f-...-707.lock` → PR #707（INFRA-331）
2. `gh pr list --state open` — 若只有唯一 open PR，直接交叉验证
3. `pending-ci*.json` 状态文件 — 本次不存在（PR #704/#706 之前已闭环清理），不能依赖它作为唯一信号源

### 关键教训

1. **通知内嵌的「状态为 success」不可信**。本次通知到达时 PR #707 实际有 4 个 check 仍 IN_PROGRESS（test (3.12)、droid-review、Coverage Audit、Hook Lifecycle Integration Tests），约 6 分钟后才全绿。若按通知直接合并，会在未过门禁时动手。
2. **通知只是触发信号，一律以 `gh pr checks <PR>` 现场核验为准**。
3. **本仓库已部署 auto-merge 流水线**：合并由仓库 "Auto-merge PR" workflow job 在 ci-ok/qa-ok 全过后自动完成（含 --delete-branch）。ci-gateway session 的职责是「核验 + 兜底 + 合并后三件事」（确认分支已删除、main CI 绿、本地 main 同步），而非必然手动执行 merge。
4. PR #0 这类 sentinel 值出现时，先按上述方法定位真实 PR（lock 文件名是最快路径），再决定动作；不要对 #0 本身做任何 gh 操作。

### 预防/后续

- n8n webhook 侧应对 PR 编号缺失显式报错或携带可定位字段，而不是默认 0（待跟进，属 webhook 上游）
- 收到 CI 完成通知的标准动作序列：定位真实 PR → `gh pr checks <PR>` 现场核验 → 若 auto-merge 已接管则只做合并后三件事

## Truth Basis

### Source Refs

- 本 session 2026-08-15 19:38 ci-gateway 事件（编排器任务描述提供的 truth basis）
- memory/log/2026-08-15.md Session 2（28d59099）、Session 315（f508f32f）— 同日「PR #0」通知复发记录

### Authority Refs

- AGENTS.md（CI 完成后 Webhook 路由、合并纪律：任何 check 失败不得绕过合并）
- ~/.factory/AGENTS.md（Webhook 子系统：trigger-ci-droid.sh / write-pending-ci.sh 职责）
- memory/kb/lessons/webhook-session-routing.md（同链路另一失效模式：session_id 路由失效）

### Evidence Refs

- ~/.factory/webhook/locks/ci-complete-f511031f-...-707.lock（lock 文件名尾部含真实 PR 编号 707）
- gh pr checks 707 现场 output：4 checks IN_PROGRESS → 约 6 分钟后全绿
- git log：本地 main 已同步至 984ce51（PR #707 / INFRA-331 对应 commit）

### Conflict Status

- resolved
