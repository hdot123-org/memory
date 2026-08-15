
> Date: 2026-08-11
> Source: Linear-GitHub 双向同步死锁事件（INFRA-248 / INFRA-252，GitHub #579 / #583）
> Tags: [lesson, linear, github, sync, webhook, deadlock, infrastructure]
> Related: [2026-08-12-ci-cd-automation-fixes]

## Linear-GitHub 双向同步死锁：手动关闭 Issue 触发无限循环

### 背景

memory-core 项目使用 Linear 原生 GitHub 集成（ID: 7ee5340b）实现 Linear Issue 与 GitHub Issue 之间的双向状态同步。

同步规则：
- GitHub Issue 关闭 → Linear 自动转为 "Done"（已完成）
- Linear 转为 "Done" → GitHub Issue 自动关闭

### 问题现象

手动关闭 GitHub Issue #579 和 #583（对应 Linear INFRA-248 和 INFRA-252）时，触发双向同步死锁：

1. 手动关闭 GitHub #579
2. 集成检测 → Linear INFRA-248 转为 "Done"（已完成）
3. 集成检测 Linear 变化 → 触发反向同步 → 再次操作 GitHub #579
4. GitHub #579 状态变化 → 触发正向同步 → 再次操作 Linear INFRA-248
5. ……无限循环，每个周期约 10-15 秒

此事件在 2026-08-11 当天造成 3905 次 `linear_webhook_failure` 事件（错误类型：`ref_resolution_failed` 2616 次，`gate_a_blocked` 1250 次）。

多次尝试打破循环均失败：
- 锁定 GitHub Issue → 集成拥有 admin 权限，绕过锁定
- 禁用 Evolution Scan workflow → Linear 仍被回退为 "In Progress"
- 将 Linear 状态改为 "Done" → 触发双向同步

### 根因

Linear 的 "Done"（已完成）状态是**双向同步触发器**：
- Linear "Done" → GitHub 应关闭
- GitHub 关闭 → Linear 应为 "Done"

双方都认为对方需要更新，互相触发无限循环。集成缺少幂等性检查：当双方均已处于终态时，应停止同步，而非反复"纠正"已经一致的状态。

### 解决方案 / 绕行方法

将 Linear 状态改为 **"Cancelled"（已取消）** 而非 "Done" 可打破循环：

- Linear "Cancelled" → GitHub 关闭（单向，无反向触发）
- GitHub 不会将 "Cancelled" 同步回 Linear

因为 "Cancelled" 在 GitHub 侧没有对应状态（GitHub 只有 open/closed），集成将其视为终态信号，不执行反向同步。循环停止。

### 预防措施

1. **避免手动关闭 GitHub Issue** —— 让 PR merge 的 `Fixes INFRA-xxx` 引用通过单向管道自动关闭 Issue
2. **如需手动关闭** —— 使用 Linear "Cancelled" 状态而非 "Done"，避免触发双向同步
3. **Webhook debounce** —— 可在 n8n pipeline 中加入 debounce：同一 Issue 在 60 秒内触发超过 N 次则自动阻断

### 关键洞察

死锁根因是手动操作打破了集成预期的流程。集成预期：PR merge → `Fixes INFRA-xxx` → 单向自动关闭。手动操作创建了集成双向同步规则无法幂等处理的意外状态转换。

---

## 2026-08-14 复发：#648 close/reopen 振荡事故

### 事故概述

2026-08-14 UTC 18:12:15 – 18:55:38，Issue **#648** 经历 14+ 轮 close/reopen 振荡，累计 **51 个 events、26 条 comments**（25 条「已不再出现」自动关评论 + 1 条 linear-code linkback 评论）。close→reopen 间隔仅 7–9 秒。

### 振荡数据

| 指标 | 数值 |
|------|------|
| 总 events | 51 |
| 总 comments | 26（25 假自动关 + 1 linkback） |
| close/reopen 轮次 | 14+ 轮 |
| 单轮间隔 | 7–9 秒 |
| 风暴期额外事件 | INFRA-292 派发会话（17:51:28–19:52:25 超时），以 hdot123 OAuth 身份用 scanner 模板文案反复直接关单 |

### 根因链

```
审计工具 partial-output（同一代码 findings 104→88→78 漂移）
  → #648 的 finding 假缺席 → auto_close 误判"已解决"
  → linkback 正则失配 fail-open（期望 ID 在注释内，实际在锚文本）放行
  → GitHub close → Linear 同步 Done → GATE A "Done 无 droid session" revert
  → Linear 集成 reopen GitHub（当时双向同步）→ 循环 14+ 轮/51 events
风暴期加密突发：自动派发的 INFRA-292 droid 会话
  以 hdot123 OAuth 身份用 scanner 模板文案反复直接关单
```

关键断点：
- **P0-A**：输出骤降防护（104→78 型骤降应拦截）
- **P0-1**：linkback 两级提取 fail-closed（正则匹配不到 ID 时应拒关而非放行）
- **GATE A**：Done 无 droid session → revert → Linear 集成 reopen（形成闭环）

### 旁路覆盖关系表

三个旁路按时间顺序与覆盖范围：

| 旁路 | 适用场景 | 覆盖范围 | 定位 |
|------|---------|---------|------|
| **Cancelled 状态** | 应急打破死锁 | 单次手动操作 | 临时止血：Linear "Cancelled" 不触发反向同步，可立即停止振荡 |
| **merged-PR override** | 有已合并 PR 的 Done 转换 | GATE A 放行条件之一 | 场景覆盖：已有 merged PR 证明修复已落地，Done 合理，GATE A 不 revert |
| **单向化（GitHub→Linear）** | 拓扑根治 | 全局架构级 | 根本解决：禁用 Linear→GitHub 反向同步，死锁拓扑不复存在 |

覆盖关系：
- Cancelled 是**应急手段**：在双向同步架构下，唯一能立即打破死锁的操作
- merged-PR override 是**场景补全**：在 GATE A 层面为合理的 Done 转换开绿灯，避免误 revert
- 单向化是**拓扑根治**：从根本上消除双向同步触发的死锁可能性，使前两个旁路成为纵深防御

### 单向化决策

**决策**：2026-08-15，用户将 Linear GitHub 集成从双向同步改为**单向同步**（GitHub→Linear only）。

**依据**：Linear 官方文档 [linear.app/docs/github](https://linear.app/docs/github#configure-github-issues-sync) 明确支持单向同步配置。单向同步下：
- GitHub close → Linear Done（正向，保留）
- Linear 状态变化 → 不再回写 GitHub（反向，禁用）

**效果**：
- 死锁拓扑消灭：GATE A revert 不再触发 Linear 集成 reopen GitHub
- Cancelled 旁路降级为纵深防御（单向架构下不再需要应急打破死锁）
- merged-PR override 保留为场景补全（放行合理的 Done 转换）

### 后续修复（已落地）

- **PR #668**：去重修复（#648/#652/INFRA-292 全闭环）
- **PR #670**：P0-A 输出骤降防护 + P0-1 linkback 两级提取 fail-closed
- **用户操作**：Linear 集成改单向同步

### 教训沉淀

1. **自动派发的会话禁止直接关闭 GitHub issue**，必须走 PR + `Fixes` 引用闭环（见仓库 AGENTS.md「Issue 流转约定」节）
2. **检测器输出不稳定不是本次根因**，降级为背景加固项（Q1 裁决）
3. **GATE A 是环路中唯一必经且在我方控制下的节点**，P0-3 是其止血点
4. **linkback fail-open 是信任链第一环断裂点**，P0-1 fail-closed 收窄是纵深防御

## Truth Basis

### Source Refs

- 2026-08-11 `linear_webhook_failure` 事件统计（3905 次：`ref_resolution_failed` 2616 次，`gate_a_blocked` 1250 次）
- GitHub Issue #579 / #583 关闭操作记录
- Linear INFRA-248 / INFRA-252 状态变更记录
- 2026-08-14 #648 issue events（51 events, 26 comments）
- 2026-08-14 GATE A 日志序列（trigger-INFRA-292-*.log，覆盖全部 9 轮）
- 2026-08-15 GLM-5.3 终裁报告（research/scanner-oscillation/adjudication-glm53.md）

### Authority Refs

- project-map/INDEX.md
- memory/kb/global/memory-system.md
- AGENTS.md（Issue 流转约定：PR `Fixes INFRA-xxx` 单向自动闭环机制）
- Linear 官方文档：[linear.app/docs/github](https://linear.app/docs/github#configure-github-issues-sync)

### Evidence Refs

- Linear GitHub 集成配置（ID: 7ee5340b）
- n8n webhook pipeline 日志
- GitHub Actions run 日志（18:50:59 真实 tick：104 findings、含 #648 finding、无 close 动作）
- `~/.factory/webhook/logs/trigger-INFRA-292-*.log` 序列

### Conflict Status

- resolved
