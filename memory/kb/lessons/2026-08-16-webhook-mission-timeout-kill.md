> Date: 2026-08-16
> Source: webhook mission 超时绞杀修复 mission b4786165（2026-08-16 全流程：PR #741 合并部署 + 13 僵尸 + 10 空壳收尸）
> Tags: [lesson, webhook, mission, timeout, SIGTERM, zombie, state-machine, trigger-droid, trigger-ci-droid, with_timeout, process-kill]
> Related: [webhook-session-routing, 2026-08-15-ci-webhook-pr-zero-fallback, 2026-08-16-ci-ok-droid-review-timeout-race, 2026-08-15-gateway-concurrent-sessions-worktree-isolation]

## webhook 派发 `droid exec --mission` 的 with_timeout 3600 绞杀导致 mission 状态机冻结与僵尸累积

### 现象

8/14 起 `~/.factory/missions/` 持续累积僵尸 mission 目录：state ∈ {running, orchestrator_turn}，updatedAt 停滞 >6h，ps 无宿主进程。共 13 个 running 僵尸（11 running + 2 orchestrator_turn），全部 ~1.0h 寿命指纹；planning 空壳持续新增。TUI `/missions` 手动启动的 mission 不受影响（主 mission 94520efa 存活 60h+）。

### 根因链

```
with_timeout 3600 包裹 droid exec --mission --auto high
  → [精确 3600s] SIGTERM → 编排器进程死亡
    → mission state.json 冻结于 running/orchestrator_turn（状态机随进程冻结，无终态事件）
    → worker 被 "Parent process disconnected" 连坐杀死，无完成事件
    → 失败重试再拉新 droid exec --mission → 新 planning 空壳
```

关键机制：
1. `with_timeout 3600` 在 trigger-droid.sh（首次派发 + 失败重试两处）和 trigger-ci-droid.sh（fallback 派发一处）中使用
2. SIGTERM 杀死编排器进程后，mission 状态机没有写入终态的机制——state.json 永久冻结
3. trigger-droid.sh 的 planning 自愈循环（L1002 附近）只清 planning 态，不清 running 态，导致 running 僵尸永久累积
4. worker 假死时 runner 只写 `worker_failed` 不触发恢复（实测空等 5.5h 案例）

### 证据指纹

| 指纹 | 证据 |
|------|------|
| 精确 3600s 寿命 | mission `8bbae4df`：createdAt 2026-08-16T10:57:10Z → SIGTERM 11:57:10Z，精确 3600s |
| 13 僵尸 ~1.0h 寿命 | 8/14 起 13 个 mission 卡死（11 running + 2 orchestrator_turn），全部创建后精确 ~1.0h 冻结 |
| 破坏面二分 | TUI 60h mission（94520efa）不受影响 vs webhook mission 必死（精确 3600s SIGTERM） |
| 活体注意 | PID 5942 曾在跑 `droid exec --mission`（部署时在途，≤1h 自然死亡）；PID 10077 是主 mission resume 会话 |

### 修复方案

**降级 webhook 派发为普通 `droid exec`（删 `--mission`）**：

- trigger-droid.sh：首次派发 + 失败重试两处删 `--mission`；ECHO_DROID 干跑镜像字符串同步更新
- trigger-ci-droid.sh：以生产版回灌仓库，删 fallback 派发处 `--mission`，纳入 MANIFEST.sh MANAGED_FILES
- 保留：`--auto high`、tag、幂等判据、pending-ci 路由
- 新增回归测试：`tests/test_webhook_no_mission_dispatch.py` 断言两受管脚本非注释行不含 `--mission`

**已验证的审查闭环要点**：
1. **幂等不依赖 mission**：trigger-droid.sh 对 missions 目录唯一引用是 planning 自愈循环，幂等=PR/Linear 评论检查
2. **`--auto` 与 `--mission` 解耦**：`droid exec --help` 实证；error-gateway 一直 `exec --auto high` 无 mission
3. **漂移=未合并 PR**：生产脚本 == main 版本；仓库工作区多出内容来自未合并 PR（漂移方向：仓库→生产，非反向）
4. **pending-ci 按 PR 分文件**：`pending-ci-<PR>.json` 互不覆盖，无单文件竞态
5. **合法终态无 failed 只有 cancelled**：实测合法终态集合 {completed, cancelled, paused, awaiting_input}，无 "failed" 态；僵尸清理用 cancelled

**实施结果**：PR #741 合并（merge commit 1cdad06，2026-08-16T14:15:33Z）；sync 部署三文件 PASS；md5 双端一致；13 僵尸 + 10 空壳已处置。

### 关键教训

1. **进程级超时 + 状态机 = 僵尸制造机**：with_timeout SIGTERM 只杀进程，不写终态。任何「状态机随进程」的设计都必须在超时路径上提供终态写入机制，否则超时=永久冻结。
2. **TUI vs webhook 不对称**：TUI 编排器是常驻交互会话（无超时），webhook 编排器被 with_timeout 包裹。同一命令在不同调用上下文下寿命预期完全不同。
3. **自愈循环的盲点**：trigger-droid.sh planning 自愈只清 planning 不清 running，导致最严重的僵尸形态（running）完全无自愈机制。
4. **降级比修复更稳**：修复 with_timeout 的 SIGTERM→终态 路径需要改编排器（平台侧），降级派发为普通 exec 是仓库侧可独立完成的止血。
5. **生产与仓库的双向漂移**：trigger-droid.sh 生产 == main（漂移=未合并 PR 独有内容在仓库侧）；trigger-ci-droid.sh 只在生产不在仓库（需回灌）。判断方向后决定动作。

### Follow-up（本 mission 不做）

- with_timeout TERM→KILL 升级（当前 TERM 后进程可能 linger）
- 重试幂等强化（当前 crash 后仅重试 1 次，幂等检查在 skill 层）
- 每日僵尸巡检 cron（当前靠人工或 mission 触发）
- trigger-droid.sh planning 自愈循环的"活宿主误删"bug
- 平台侧 worker_failed 无恢复、编排器回合制唤醒缺口

## Truth Basis

### Source Refs

- 本 mission b4786165-0afb-4aac-87e5-b9e21c79ddc9 全流程（2026-08-16）
- mission architecture.md（根因链与目标架构）
- memory/kb/lessons/2026-08-15-ci-webhook-pr-zero-fallback.md（关联 webhook 链路教训）

### Authority Refs

- AGENTS.md（合并纪律：禁 --admin、CI 失败不得继续；webhook 子系统路由）
- memory/kb/global/memory-system.md（记忆系统规则与 Truth Basis 概念）

### Evidence Refs

- PR #741：merge commit 1cdad06（2026-08-16T14:15:33Z），CI 全绿后 auto-merge 合并
- 僵尸指纹：mission 8bbae4df createdAt 10:57:10Z → SIGTERM 11:57:10Z（精确 3600s）
- 13 僵尸基线：running 11（025d801a, 26731fd1, 2e562e64, 4cff1272, 5eee43a6, 6527c9fe, 7c12ee7e, 85e0afb1, dee49cc5, e1928105, f4ff89bd）+ orchestrator_turn 2（8f3b655b, 3af4feb0）
- 10 planning 空壳：8bbae4df, df44bceb, c259284d, 2a93da60, 3452594b, 6600cbce, b7584c6f, b555910c + 2 新增
- 生产验证：md5 双端一致（trigger-droid.sh 2b0be8a1 / trigger-ci-droid.sh 0df6b02f）、bash -n 通过、ECHO_DROID 干跑无 --mission
- tests/test_webhook_no_mission_dispatch.py：4 用例先红后绿

### Conflict Status

- resolved
