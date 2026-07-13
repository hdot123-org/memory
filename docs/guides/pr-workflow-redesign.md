# GitHub PR 流程标准规范

> 本文件是本仓库所有 PR 与 CI 操作的权威规范。人（human）和 Agent 都必须遵守。

## 一、核心原则

1. **GitHub 为主仓库**：所有开发、审查、CI 在 GitHub 上完成
2. **双门禁**：每个 PR 必须通过 `ci-ok`（功能正确性）+ `droid-review`（AI 安全审查）才能合并
3. **禁止 `--admin`**：不允许用管理员权限绕过门禁强制合并
4. **本地与云端分离**：CI 在 GitHub 云服务器执行，不依赖本地电脑在线

## 二、完整 PR 生命周期

### 标准操作流程（SOP）

```bash
# 1. 从最新 main 创建 feature 分支
git checkout main
git pull origin main
git checkout -b <type>/<short-description>

# 2. 修改代码 → 暂存 → 审查 diff（检查无密钥）
git add <files>
git diff --cached

# 3. 提交（commit 消息必须用中文）
git commit -m "<type>: 简要描述"

# 4. 推送并创建 PR
git push -u origin <branch>
gh pr create --base main --title "<type>: 简要描述" --body "改动说明"

# 5. 设置自动合并（双门禁通过后自动 squash 合并 + 删分支）
gh pr merge <PR编号> --squash --delete-branch --auto

# 6. 同步本地 main（自动合并完成后）
git checkout main
git pull origin main
```

> `--auto` 模式：门禁（ci-ok + droid-review）一通过就自动合并。设好后本地可关机，合并由 GitHub 云端完成。

### 分支命名规范

```
<type>/<short-description>
```

| type | 含义 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat/add-export` |
| `fix` | 修复 bug | `fix/null-pointer` |
| `ci` | CI/工作流变更 | `ci/grok-model` |
| `docs` | 文档变更 | `docs/update-guide` |
| `refactor` | 重构 | `refactor/extract-module` |
| `test` | 测试补充 | `test/cover-boundary` |

### Commit 消息规范

- **必须用中文**
- 格式：`<type>: 中文描述`
- 示例：`fix: 修复 discover_project_root 根目录解析错误`

## 三、CI 架构

### 执行环境

```
本地电脑                      GitHub 云端
┌──────────────┐             ┌──────────────────────────┐
│ 写代码        │  git push   │  GitHub Actions Runner    │
│ commit       │ ──────────► │  （GitHub 服务器）         │
│ push         │             │                          │
│              │             │  • test 矩阵 (Py 3.9-3.12)│
│              │ ◄────────── │  • ci-ok 聚合门禁         │
│              │  合并结果    │  • droid-review AI 审查   │
│              │             │    （调 grok-4.5 云端）    │
└──────────────┘             └──────────────────────────┘
```

- **push 后本地电脑可关机**，CI 在 GitHub 服务器上独立运行
- CI 调用的 AI 模型（grok-4.5）是 Factory 托管的**云端模型**，GitHub 服务器可直接访问
- 之前 GLM-5.2 不可用就是因为它是本地私有节点上的模型，GitHub 服务器访问不到

### 工作流文件清单

| 文件 | 触发方式 | 职责 | 是否门禁 |
|------|---------|------|---------|
| `ci.yml` | push:main + 所有 PR | test 矩阵 + 依赖安全扫描 + ci-ok 聚合 | **ci-ok 是门禁** |
| `droid-review.yml` | PR 创建/更新 | AI 代码审查 + 安全审查 | **是门禁** |
| `droid.yml` | 手动写 `@droid` | 按需 AI 协作（改代码、查问题） | 否 |

### ci.yml 设计要点

```yaml
on:
  push:
    branches: [main]
    paths: [...]        # push 保留 paths 过滤（非匹配不触发回归）
  pull_request:
    branches: [main]    # ← PR 不加 paths 过滤！
```

**关键规则**：`pull_request` **不做 paths 过滤**。因为 branch protection 的 required check 必须在每个 PR 上都报告。如果加了 paths 过滤，纯文档 PR 等不匹配的 PR 不会有 ci-ok 报告，会被 branch protection 永久卡住（等待永不出现的 check）。

```yaml
ci-ok:
  needs: [test, advisory-security, advisory-telemetry-audit]
  if: always()
  steps:
    - run: |
        if [ "${{ needs.test.result }}" != "success" ]; then exit 1; fi
        if [ "${{ needs.advisory-security.result }}" != "success" ]; then exit 1; fi
        if [ "${{ needs.advisory-telemetry-audit.result }}" != "success" ]; then exit 1; fi
```

`ci-ok` 是**聚合门禁**：聚合 test 矩阵 + 依赖安全扫描 + 遥测审计。改动 job 列表时无需同步调整 protection 配置。

> **advisory 安全扫描必须真正生效**：不要给被 ci-ok 聚合的 job 加 `continue-on-error: true`，否则它失败也不报红，门禁无法感知。

## 四、Branch Protection 规则（main）

| 规则 | 值 | 说明 |
|------|-----|------|
| Required status checks | `ci-ok` + `droid-review` | 双门禁 |
| Require branches up to date | true（strict） | 合并前必须基于最新 main |
| Require PR reviews | 0（已移除） | 不依赖人工 approve |
| Enforce for admins | false | 保留 `--admin` 作紧急通道（**正常流程禁止使用**） |

> **不要把 `droid` 或 `test` 等加为 required check**：`droid` 只在 `@droid` 触发时跑（普通 PR 显示 skipping），设为 required 会导致永久阻塞。`test` 由 `ci-ok` 聚合，无需单独 required。

## 五、AI 模型配置

| 场景 | 模型 | 位置 |
|------|------|------|
| droid-review（CI 门禁） | grok-4.5 | Factory 云端（GitHub 可达） |
| @droid（CI 按需协作） | grok-4.5 | Factory 云端 |
| 本地 Droid CLI | GLM-5.2（BYOM） | 本地私有节点（仅本地可达） |

**为什么 CI 不用 GLM-5.2**：GLM-5.2 是 BYOM（自建模型节点），GitHub Actions runner 在公网无法访问私有节点，会超时。Factory 内置模型（grok-4.5）是云端托管，GitHub 服务器可直接调用。

### droid-action 模型设置陷阱（重要）

droid-action 的 `action.yml` **没有 `model` 输入参数**。写 `model: "grok-4.5"` 会被忽略，exec 回退默认 gpt-5.2 被 org policy 封锁。

droid-action 内部有**两个 pass**，各自独立读取模型配置：

| Pass | 用途 | 控制参数 |
|------|------|---------|
| exec pass | 执行 @droid 指令 | `droid_args: "--model grok-4.5"` |
| validator/review pass | PR 审查验证 | `review_model: "grok-4.5"` |

droid.yml 必须同时设置两路（只设一路会导致另一路回退 gpt-5.2 被封）：
```yaml
with:
  droid_args: "--model grok-4.5"   # exec pass
  review_model: "grok-4.5"          # validator pass
```

## 六、@droid 按需协作

在以下任意位置输入 `@droid <指令>` 即可触发 AI 协作：

| 在哪写 | 场景 |
|--------|------|
| PR 评论 | `@droid 给这个函数加测试` |
| PR 代码行 review 评论 | `@droid 这里改成异步` |
| PR 标题/正文 | 创建时触发 |
| Issue 评论 | `@droid 复现这个 bug` |
| 新建 Issue（标题/正文含 @droid） | 开新任务 |

**安全限制**：只有 OWNER / MEMBER / COLLABORATOR 能触发（陌生人或 fork PR 写 `@droid` 无效）。

## 七、操作纪律

### PR 合并后三件事

1. **删除 feature 分支** — squash merge 的 `--delete-branch` 自动完成
2. **检查 CI 状态** — `gh run list --branch main --limit 1`，确认 main 的 CI 通过
3. **同步本地** — `git checkout main && git pull origin main`

### 禁止事项

| 禁止 | 原因 |
|------|------|
| `gh pr merge --admin` | 绕过双门禁，代码未经审查进 main |
| 直接 push main | main 受保护，必须走 feature 分支 + PR |
| `--force` push 到 main | 破坏历史 |
| 提交 API key/token/密码 | 公开仓库，立即泄露 |

### Commit 前安全检查

```bash
git diff --cached | grep -iE '(password|secret|api_key|token|fk-).*=' 
# 有匹配则停止提交，移除敏感信息
```

### CI 失败处理

- CI 失败不得继续，必须修复后才能合并
- 禁止 force push 绕过 CI
- 持续失败时回滚或修复，不绕过

## 八、droid-review 失败/卡住怎么办

droid-review 作为门禁，若因模型超时或临时故障失败：

```bash
# 重跑该 workflow
gh run rerun <run-id> --repo hdot123/memory --failed

# 或在 PR 页面点 "Re-run failed jobs"
```

`enforce_admins: false` 保留了 `--admin` 作**仅限紧急情况**的通道，正常流程禁止使用。

## 九、踩坑记录（操作参考）

### 踩坑 1：FACTORY_API_KEY 管道设置会损坏

`gh secret set FACTORY_API_KEY --body -`（管道读取）会静默失败，secret 变成长度 1 的 `*`，导致 CI 报 "Authentication failed"。

**正确**：`gh secret set FACTORY_API_KEY --body 'fk-...'`（直接传值）。

### 踩坑 2：模型 org policy 封锁

droid-action 默认硬编码 `--model "gpt-5.2"`，被 org policy 封锁，CI 报错。需显式指定可用模型。

| 模型 | 本地 | CI | 原因 |
|------|------|----|------|
| gpt-5.2 | ✓ | ✗ | org policy 封锁 |
| GLM-5.2（BYOM） | ✓ | ✗ | GitHub runner 不可达私有节点 |
| claude-opus-4-8 | ✓ | ✓ | 可用 |
| grok-4.5 | ✓ | ✓ | **当前选用** |

### 踩坑 3：GitHub Actions contains() 参数顺序

`contains(github.event.pull_request.author_association, 'OWNER')` 是错的。正确语法 `contains(haystack, needle)`：

```yaml
if: contains('OWNER,MEMBER,COLLABORATOR', github.event.pull_request.author_association)
```

### 踩坑 4：stale required check 导致永久 BLOCKED

删除 `auto-review.yml` 后，branch protection 里残留的 `review` check 永远不会报告，导致所有 PR 永久 BLOCKED。**删除 workflow 前必须先从 branch protection 移除对应 required check**。

可用 GraphQL 更新（REST `/branches/main/protection` 可能被 hook 拦截）：

```bash
gh api graphql -f query='mutation {
  updateBranchProtectionRule(input: {
    branchProtectionRuleId: "<RULE_ID>"
    requiresStatusChecks: true
    requiresStrictStatusChecks: true
    requiredStatusCheckContexts: ["ci-ok", "droid-review"]
  }) { branchProtectionRule { requiredStatusCheckContexts } }
}'
```

## 十、验证状态

| 验证项 | 结果 | PR |
|--------|------|----|
| ci.yml 在 PR 上全量跑 | ✓ | #75 |
| ci-ok 聚合门禁 | ✓ | #75 #76 #77 |
| droid-review 安全审查 | ✓ | #75（首次） |
| branch protection 双门禁（ci-ok + droid-review） | ✓ | #76 起生效 |
| grok-4.5 CI 可用 | ✓ | #78 |
| 无 --admin 合并 | ✓ | #75 #76 #77 #78 |
