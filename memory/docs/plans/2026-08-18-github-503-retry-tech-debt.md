# GitHub API 503 瞬时故障无自动重试——技术债清单

> 创建日期：2026-08-18
> 来源：2026-08-17 CI 异步化改造全程观测（session 记录见 memory/log/2026-08-17.md）
> 性质：incoming-raw 待办素材，非 canonical
> 关联：memory/kb/decisions/2026-08-17-mission-async-merge-decoupling.md

## 背景

2026-08-17（GitHub API 大面积 503 持续全天，2026-08-18 仍有间歇复发）实测受影响点：

| 受影响点 | 实例 | 当前兜底 |
|----------|------|---------|
| droid-review 首轮失败 | PR #767：droid-action 权限检查 GET /collaborators 503，1m18s 即挂 | 人工/agent `gh run rerun --failed`；未重跑则 PR 卡住不合并（fail-closed，无带病合并风险） |
| PR 创建失败 | #764/#766/#767 创建时 GraphQL 503，重试 3-4 次才成功，REST API 成功率略高 | 人工重试 |
| auto-merge 瞬时失败 | shared-workflows tarball 下载 429/503，resolve 步骤瞬时 exit 1 | schedule 每 10 分钟兜底扫描（实测有效：#763 被 schedule 收割） |
| 状态查询间歇失败 | gh CLI GraphQL unexpected EOF / TLS handshake timeout | 人工重试 |

异步合并改造后，503 从「拖慢会话」降级为「拖慢合并延迟」——fail-closed 语义保证不会带病合并，但 503 窗口期内 PR 合并延迟显著拉长（#767 因 503 + BEHIND 重挂从 4 min 拉长到 49 min）。

## 技术债清单

### TD-503-01: droid-review 无瞬时故障自动重试 — ✅ 已闭环（PR #777，INFRA-386）

- **现状（修复前）**：droid-action 权限检查/prep 阶段遇 GitHub 503 直接 fail，check run 结论 failure，阻塞 ci-ok 与 auto-merge
- **影响（修复前）**：503 窗口期所有 PR 首轮 review 大概率挂；依赖人工 rerun，与异步化目标（无人值守合并）冲突
- **选型落地**：方案 C 变体（watchdog workflow）——`.github/workflows/droid-review-watchdog.yml`（PR #777，2026-08-18 合并 main，commit 4c7410e）：
  - 触发：`workflow_run`（"Droid Auto Review" completed）——上游 run 已终态才可调 rerun-failed-jobs API（job 内自愈存在时序竞争，架构性不可行）
  - 特征匹配：`permission - 503|Failed to check permissions|HttpError: No server is currently available|unexpected EOF|TLS handshake timeout`，仅 infra 瞬时错误命中
  - 防重试风暴：`run_attempt < 3` 限界（最多自动重试 2 次）
  - 门禁零削弱：失败轮保持 failure 结算（fail-closed），rerun 的那轮才是有效 review；真代码审查发现不匹配特征不触发 rerun
  - 结构测试：VAL-503-001~004（tests/test_ci_config.py::TestDroidReview503SelfHeal）
- **PR/Issue 回链**：实现由 PR #777 交付（body 未含 Fixes 引用，Linear 无法自动闭环）→ 本文档状态闭环（INFRA-386 与 PR #777 为同一诉求：watchdog 检测 503 瞬时模式并 rerun-failed-jobs，droid review 自愈且不绕过门禁）
- **注意**：不得为绕过 503 降低门禁（禁止 skip droid-review 或 --admin）——已遵守

### TD-503-02: gh CLI 调用无统一重试封装 — 🔓 开放（优先级中）

- **现状**：webhook 脚本内 curl 已有 5xx 重试（trigger-ci-droid.sh 的 Sessions API 调用，3 次指数退避），但 gh CLI 调用（PR 创建、checks 查询）无重试；mission/派发会话内 gh 调用也无约定
- **影响**：503 窗口期会话操作反复失败，浪费轮次
- **候选方案**：约定层面——AGENTS.md 或 ci-gateway skill 加「gh 调用遇 503/EOF 统一 sleep+重试」惯例；或提供 `~/.factory/bin/gh-retry` 包装脚本
- **范围界定**：只包装幂等读操作与创建类操作的重试；写操作重试需防重复副作用（PR 创建重试需先查是否已建）
- **部分进展**：scripts/check_fix_has_test.py 的 gh 调用已带瞬时 5xx 有界重试（PR #777 顺带交付）

### TD-503-03: PR 创建 GraphQL→REST 降级路径未固化 — 🔓 开放（优先级低）

- **现状**：2026-08-17 实测 GraphQL 503 时 REST API（repos/.../pulls POST）成功率更高，`gh pr create` 走 GraphQL，失败后手工改用 `gh api` REST 创建成功
- **候选方案**：无需脚本化（503 属外部偶发），仅在本债条目留档：GraphQL 连续 503 ≥2 次时改用 `gh api repos/{repo}/pulls --method POST` 创建，body 格式见 2026-08-17 session 记录

## 明确不做

- 给 GitHub API 故障加告警管道（PostHog 已有 ci_webhook_failure 事件覆盖部分场景，重复建设）
- 修改 droid-review 的 fail-closed 语义（skipped/未运行 = BLOCK 是安全基线）
