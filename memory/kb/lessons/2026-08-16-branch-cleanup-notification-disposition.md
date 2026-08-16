> Date: 2026-08-16
> Source: INFRA-330 branch-cleanup 通知处置（镜像 hdot123/memory#700）
> Tags: [lesson, linear, github, linear-gateway, branch-cleanup, notification, idempotency]
> Related: [2026-08-14-linear-gateway-idempotent-reuse]

## branch-cleanup 通知类 Linear issue 处置：只评论、不改状态、不关镜像

### 场景

Linear gateway 门铃派发 branch-cleanup workflow 的自动通知 issue（如 INFRA-330 "Branch cleanup: 1 deleted (2026-08-15 10:17 UTC)"，标签 automation/branch-cleanup），镜像为 GitHub issue（hdot123/memory#700）。此类 issue 是纯通知：报告孤立分支（本次为 `feat/suppress-expiry`）已被每日清理 workflow 删除，无代码变更需求，无可修复对象。

### 正确处置（reject 路径，本次按先例验证）

1. **定性为非代码任务**：通知类 issue 不进代码修复流程
2. **幂等检查**：回写前先查 Linear 评论列表，确认无既有说明评论——INFRA-269 曾出现两条几乎相同的 Droid 评论（重复评论事故）
3. **仅回写中文说明评论**：说明这是 branch-cleanup 自动通知、分支已清理、无需动作
4. **不创建 PR、无代码变更、无分支操作**
5. **不改 Linear 状态**：状态流转交给 GitHub ↔ Linear 自动化或人工
6. **不直接关闭 GitHub 镜像**：关单铁律——派发会话禁止直接关 GitHub issue，只能走 PR + Fixes 引用或 scanner 合法 `auto_close_resolved()`

### 为什么不能"顺手闭环"

- **无可修复对象**：不存在可以通过 PR 修复的东西，`Fixes` 闭环路径根本不适用
- **GATE A 会强制回退**：`trigger-droid.sh` 行 398-528 只拦截 completed 转换，对无 Droid session 佐证的 Done 强制回退到进行中（canceled 明确放行，代码注释："取消是正常操作……不需要 Droid session 记录"）。直接把无 PR 的通知类 issue 设 Done 只会触发回退循环
- **compensation-layer 不覆盖此类 issue**：`~/.factory/webhook/scripts/reconcile-evolution.sh` §4b 的 Linear GraphQL 查询硬编码 `labels containsIgnoreCase "evolution-found"`，branch-cleanup 类通知（automation/branch-cleanup 标签）永远不在扫描范围内——把此类 Linear issue 置终态也不会触发镜像关闭

### 已知缺陷（本次调查发现）

compensation-layer 用 `gh issue list --search <Linear ref>` 全文检索定位镜像 issue：

- **#724 误关闭案例**：#724 正文含分支名 `refactor/INFRA-333-dedup-test-block`，被误当作 INFRA-333 的镜像而错误关闭（reconcile 日志 2026-08-15 23:45:14 可证；#724 的真实镜像是 INFRA-346）
- **建议修复方向**：改为读取 linear-linkback 评论定位镜像，替代全文检索

### 遗留缺口

- GitHub #700、#730（"1 protected" 2026-08-15 20:17 UTC）均 OPEN
- 此类通知的镜像 issue 关闭目前仅有人工先例：INFRA-269（镜像 #614）由 Droid 评论说明 + 不改状态，#614 由人工 self-assign 后手动 close，Linear 经 GitHub 原生集成同步为已完成（时间对齐 <1s）
- 无自动化关闭路径，待机制补齐

## Truth Basis

### Source Refs

- 2026-08-16 session 的 Linear GraphQL 查询（INFRA-330 / INFRA-269 详情与评论）
- gh API 查询（hdot123/memory #614、#700、#724、#730 状态与正文）
- `~/.factory/webhook/scripts/reconcile-evolution.sh` §4b 源码（标签过滤 + 全文检索逻辑）
- `trigger-droid.sh` 行 398-528（GATE A 状态转换拦截逻辑）
- reconcile 日志 2026-08-15 23:45:14（#724 误关闭证据）

### Authority Refs

- AGENTS.md（Issue 流转约定 / 派发会话关单规矩铁律）
- ~/.factory/skills/linear-gateway/SKILL.md（reject 路径与幂等规则）

### Evidence Refs

- INFRA-330 处置 session 的中文评论回写（由并行 worker 执行，2026-08-16）
- 先例链路：INFRA-269 / #614 人工关闭，Linear 状态同步时间对齐 <1s

### Conflict Status

- resolved
