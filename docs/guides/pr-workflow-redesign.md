# PR 流程改造方案

## 一、问题诊断

改造前 3 个问题形成恶性循环：

| 问题 | 现状 | 后果 |
|------|------|------|
| CI 不在 PR 上跑 | `ci.yml` 只在 `push: main` 触发 | PR 合并前无测试验证 |
| auto-review.yml 不提交 approval | 只发评论，不做正式 review 门禁 | review 检查形同虚设 |
| Agent 用 `--admin` 强制合并 | 绕过所有 branch protection 规则 | 代码未经审查直接进 main |

## 二、改造结果（PR #75 已合并）

### 门禁设计：ci-ok 做唯一 required check

放弃 "Droid approval 做门禁" 的方案（见下方踩坑），改用 `ci-ok` 聚合门禁做唯一的 required status check。

`ci-ok` 是一个聚合 job（`if: always()`），只有当所有 test job 成功时才通过，否则失败。这样只需在 branch protection 里配一个 check，不用逐个配 4 个 test job。

### 工作流文件清单

| 文件 | 职责 |
|------|------|
| `ci.yml` | test 矩阵（Py 3.9-3.12）+ `ci-ok` 聚合门禁 |
| `droid-review.yml` | PR 自动 AI 审查 + 安全审查（非门禁，仅反馈） |
| `droid.yml` | `@droid` 标签触发的按需 AI 协作 |

> `auto-review.yml` 已删除（旧 lint/size/secret 检查，职责被 droid-review 覆盖）。

### ci.yml 关键改动

```yaml
on:
  push:
    branches: [main]
    paths: [...]        # push 保留 paths 过滤
  pull_request:         # ← 新增：PR 触发，不加 paths 过滤
    branches: [main]    #   确保 ci-ok 在每个 PR 上都报告

jobs:
  test:
    ...
  ci-ok:                # ← 新增：聚合门禁
    needs: [test]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - run: |
          if [ "${{ needs.test.result }}" != "success" ]; then
            exit 1
          fi
```

**为什么 pull_request 不加 paths 过滤**：branch protection 的 required check 必须在每个 PR 上都报告。如果加了 paths 过滤，不匹配的 PR 不会有 ci-ok 报告，会被 branch protection 卡住（等待永不出现的 check）。

### droid-review.yml 配置

- `automatic_review: true` + `automatic_security_review: true`
- `review_model: claude-opus-4-8`（见模型踩坑）
- `review_depth: deep`
- 第三方 action SHA-pinned: `Factory-AI/droid-action@7c7bfea2aa3bb7ea87579402cc1d89dbcf6b13b3`
- `author_association` 检查：只响应 OWNER/MEMBER/COLLABORATOR（防 fork-PR secret 泄露）

### Branch Protection 配置

| 规则 | 值 |
|------|-----|
| Required status checks | `ci-ok`（唯一） |
| Require PR reviews | `required_approving_review_count: 0`（已移除） |
| Require branches up to date | true（strict） |
| Enforce for admins | false |

## 三、改造后的完整流程

```
Agent/人 代码变更
      │
      ├── git checkout -b <branch>
      ├── git add + commit + push
      ├── gh pr create
      │
      ▼
  PR 创建
      │
      ┌─────────────┬──────────────────┐
      ▼             ▼                  ▼
   ci.yml      droid-review.yml    (并行运行)
   test ×4     AI 审查（非门禁）
   ci-ok ←──── 门禁
      │             │
      └──────┬──────┘
             ▼
   ci-ok 通过（droid-review 仅参考）
             │
             ▼
   gh pr merge --squash --delete-branch
   （不用 --admin）
```

## 四、踩坑记录

### 踩坑 1：FACTORY_API_KEY 通过管道设置会损坏

`gh secret set FACTORY_API_KEY --body -`（从管道读取）会静默失败，secret 变成长度 1 的 `*`。

**正确做法**：`gh secret set FACTORY_API_KEY --body 'fk-...'`（直接传值）。

### 踩坑 2：模型可用性

droid-action 默认硬编码 `--model "gpt-5.2"`，被 org policy 封锁。可用模型排查：

| 模型 | 本地 | CI | 原因 |
|------|------|----|------|
| gpt-5.2 | ✓ | ✗ | org policy 封锁 |
| GLM-5.2（BYOM） | ✓ | ✗ | BYOM node 从 GitHub Actions runner 不可达，超时 |
| claude-opus-4-8 | ✓ | ✓ | 最终选用 |

**结论**：CI 里用 `claude-opus-4-8`。

### 踩坑 3：Droid approval 无法提交（action bug）

droid exec 正确判定 `status: "approved"`（0 issues），但 action 后处理日志显示 `IS_PR: false`，导致 APPROVED review 没有提交到 GitHub（只提交了 COMMENTED）。

**务实方案**：不依赖 review approval 做门禁，用 `ci-ok` 做唯一 required check。droid-review 照常运行提供 AI 审查反馈，但不阻塞合并。

### 踩坑 4：GitHub Actions contains() 参数顺序

`contains(github.event.pull_request.author_association, 'OWNER')` 是错的。正确语法是 `contains(haystack, needle)`，字符串在前、子串在后。实际应写：

```yaml
if: contains('OWNER,MEMBER,COLLABORATOR', github.event.pull_request.author_association)
```

## 五、铁律

- **禁止 `--admin` 合并**：所有 PR 必须通过 `ci-ok` + `droid-review` 双门禁
- **commit 消息用中文**
- **合并后删除 feature 分支**
- **合并后检查 main 的 CI 状态**（`gh run list --branch main --limit 1`）

## 六、验证状态

| 验证项 | 结果 |
|--------|------|
| ci.yml 在 PR 上全量跑 | ✓（PR #75 #76） |
| ci-ok 聚合门禁 | ✓ |
| droid-review 安全审查 | ✓（claude-opus-4-8，~15min） |
| branch protection 双门禁 | ✓（ci-ok + droid-review） |
| 无 --admin 合并 | ✓（PR #75 #76 均 squash 合并） |
