# mission 会话与 CI/合并流程解耦（异步合并纪律）

## 状态
accepted

## 日期
2026-08-17

## 背景

mission 开发任务被 CI/CE 流程串行阻塞：会话创建 PR 后惯例性等待 CI 完成（注入消息到达）再执行合并，然后才切下一任务。2026-08-17 审计实测：

- 单次 CI 全程 10~27 min，其中 droid-review 占 ~75%（3.3~27.2 min 波动）
- CI 转绿到合并完成仅 4~40 秒（通知链+合并反应已是最优）
- 每 mission 任务被强加 10~27 min 等待，瓶颈不在基础设施，在「会话在合并关键路径上」

仓库已有 auto-merge.yml（2026-08-12 决策：workflow_run + schedule 双触发，DISPATCH_TOKEN，全绿自动 squash + 删分支），机制可靠且与 branch protection（enforce_admins、ci-ok 含 droid-review）共同构成完整门禁。会话在场等待对门禁没有任何增量价值。

## 决策

**mission 会话彻底退出合并关键路径。**

1. 创建 PR + `write-pending-ci.sh` 注册路由后，立即切下一任务，不等注入消息
2. 合并完全交给 auto-merge workflow（全绿自动 squash）
3. 注入消息到达时由 ci-gateway skill 幂等处理：PR 已合并（MERGED）→ 直接执行合并后三件事；CI 失败 → 回到该 PR 修复，修复 push 后 auto-merge 自动重试
4. 禁止会话内 `gh pr merge --watch` 或轮询 checks

### 方案对比

| 维度 | 旧惯例 | 新纪律 |
|------|--------|--------|
| 会话等待 | 10~27 min/任务（串行等注入+合并） | 0（立即切任务） |
| 合并执行者 | 会话（收到注入后手动 merge） | auto-merge workflow |
| 门禁 | branch protection + ci-ok | 不变（零削弱） |
| CI 失败路径 | 注入 status=failed → 会话修复 | 不变（auto-merge 保持待命） |
| 吞吐 | ~1 任务/15-25 min | 接近连续开发 |

### 明确否决的替代方案

- **`gh pr merge --auto`**：与 auto-merge.yml 双机制冗余，徒增状态空间
- **Merge Queue**：仓库未启用，现有 workflow 无 `on: merge_group` 触发器，开了会卡 required check；瓶颈是单 PR 延迟非合并吞吐
- **提前 notify / 绕过 droid-review**：违反铁律（ci-ok 门禁含 droid-review，禁止 --admin）

## 理由

1. **门禁零削弱** — auto-merge 只在全部 check run 完成且无失败时合并（shared-workflows/auto-merge action 逻辑），与 branch protection 叠加
2. **机制已存在且已验证** — #763 当天经 auto-merge workflow 自动合并（两次瞬时失败后由 schedule 兜底收敛），无需新建基础设施
3. **失败路径不回归** — CI 红时 auto-merge 跳过，注入 status=failed 照常触发修复流程

## 影响

- mission 任务吞吐从 ~1 个/15-25 min 提升到接近连续开发
- ci-gateway skill 需补「PR 已 MERGED」幂等分支（配套全局文件修改）
- AGENTS.md 新增「mission 异步合并纪律」章节作为行为契约
- 配套：ci.yml concurrency 取消守卫（PR #764）消除快速迭代的 runner 堆叠

## Truth Basis

### Source Refs

- memory/kb/decisions/2026-08-12-auto-merge-trigger-strategy.md
- .github/workflows/auto-merge.yml

### Authority Refs

- project-map/INDEX.md

### Evidence Refs

- tests/test_ci_config.py
- scripts/check_droid_review.sh

### Conflict Status

- resolved
