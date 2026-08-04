# Release Runbook

本指南是 memory-core 的完整发版操作手册。

## 目录

1. [自动发版流程（release-please）](#1-自动发版流程release-please)
2. [手动版本同步清单（紧急发版）](#2-手动版本同步清单紧急发版)
3. [回滚流程](#3-回滚流程)
4. [下游通知机制](#4-下游通知机制)
5. [Hotfix 发版流程](#5-hotfix-发版流程)
6. [故障排查](#6-故障排查)

---

## 1. 自动发版流程（release-please）

### 工作原理

memory-core 使用 [release-please](https://github.com/googleapis/release-please) 自动化版本管理。流程如下：

```
开发者提交 PR (conventional commit)
        ↓
   合并到 main
        ↓
release-please 自动创建/更新 Release PR
   (含版本号变更 + CHANGELOG)
        ↓
   合并 Release PR
        ↓
自动创建 tag + GitHub Release + 构建 wheel
```

### 触发条件

- **触发器**：push 到 `main` 分支
- **工作流**：`.github/workflows/release-please.yml`
- **Commit 规范**：必须使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式

### Commit 消息规范

| 前缀 | 版本影响 | 示例 |
|------|---------|------|
| `feat:` | minor (+0.0.1 → +0.1.0) | `feat: 添加 memory-doctor 命令` |
| `fix:` | patch (+0.0.1) | `fix: 修复 ownership 分类器绝对路径问题` |
| `feat!:` / `fix!:` | major (+1.0.0) | `feat!: 重构 hook 输出格式` |
| `chore:` / `docs:` / `test:` / `refactor:` | 不触发版本 | `chore: 更新依赖` |

> **注意**：commit 消息必须使用中文（项目铁律）。

### Release PR 内容

release-please 自动维护一个 "Release PR"，包含：
- `pyproject.toml` 版本号更新
- `memory_core/constants.py` 版本号更新
- `README.md` 版本引用更新（通过 `extra-files` 配置）
- `CHANGELOG.md` 新版本条目

当有新的 conventional commit 合并到 main 时，Release PR 会自动更新。

### 发版步骤

1. **提交代码**：使用 conventional commit 格式，走 PR 双门禁合并到 main
2. **等待 Release PR**：release-please 自动创建/更新 Release PR
3. **合并 Release PR**：确认 CHANGELOG 和版本号正确后，合并 Release PR
4. **自动完成**：tag + GitHub Release + wheel 构建自动完成

### 发版后验证

```bash
# 确认 tag 已创建
git tag -l "v0.9.*"

# 确认 GitHub Release 已创建
gh release list --limit 3

# 确认 wheel 已上传
gh release view v0.9.x --json assets

# 确认 release workflow 成功
gh run list --workflow=release-and-dispatch.yml --limit 1
```

---

## 2. 手动版本同步清单（紧急发版）

**仅在 release-please 故障时使用**。正常情况下不要手动发版。

### 前置检查

- [ ] 确认 release-please 确实无法工作（检查 GitHub Actions 日志）
- [ ] 确认所有测试通过：`python -m pytest tests/ -q`
- [ ] 确认 ruff lint 通过：`ruff check .`

### 版本号同步清单

版本号必须出现在以下所有位置，且完全一致：

| 位置 | 字段 |
|------|------|
| `pyproject.toml` | `[project].version` |
| `memory_core/constants.py` | `CURRENT_MEMORY_VERSION` |
| `README.md` | `Current documented release` 行 + 所有 install 命令中的 `@vX.Y.Z` |
| `.release-please-manifest.json` | `{"\u002e": "X.Y.Z"}`（path-keyed，`\u002e` 即根路径 `.`） |
| `CHANGELOG.md` | 最新 `## [X.Y.Z]` 条目 |

**测试文件**：所有测试通过 `from memory_core.constants import CURRENT_MEMORY_VERSION` 动态读取版本号，无需手动更新。

### 手动发版步骤

```bash
# 1. 同步版本号到所有位置（见上方清单）
# 2. 提交版本号变更（走 PR 双门禁合并到 main）
git checkout main && git pull origin main

# 3. 打 tag（tag 必须以 v 开头，与 pyproject 版本一致）
git tag vX.Y.Z
git push origin vX.Y.Z      # 自动触发 release-and-dispatch.yml

# 4. release workflow 自动执行：test → build → GitHub Release
# 5. 验证
gh release view vX.Y.Z
gh run list --workflow=release-and-dispatch.yml --limit 1
```

### 手动补发（tag 已存在但 release 未生成）

```bash
gh workflow run release-and-dispatch.yml \
  -f release_tag=vX.Y.Z \
  -f dispatch_targets="owner/repo1,owner/repo2"
```

---

## 3. 回滚流程

### 使用回滚脚本（推荐）

```bash
# 回滚到指定版本
scripts/release_rollback.sh v0.9.x
```

脚本会自动：
- 删除 GitHub Release
- 删除 git tag（本地 + remote）
- 回滚 `.release-please-manifest.json` 到上一版本

### 手动回滚

```bash
# 1. 删除 GitHub Release
gh release delete v0.9.x --yes

# 2. 删除 remote tag
git push origin :refs/tags/v0.9.x

# 3. 删除本地 tag
git tag -d v0.9.x

# 4. 回滚 .release-please-manifest.json 到上一版本
# （手动编辑或从 git history 恢复）
```

### 回滚后恢复

回滚后，下次合并 conventional commit 到 main 时，release-please 会自动创建新的 Release PR。

---

## 4. 下游通知机制

### 触发方式

`release-and-dispatch.yml` 负责下游通知，支持两种触发方式：

| 触发方式 | 说明 |
|---------|------|
| `push: tags: [v*]` | release-please 创建 tag 时自动触发 |
| `workflow_dispatch` | 手动触发（如需指定 `dispatch_targets`） |

release-please 合并 Release PR 后自动创建 tag，`release-and-dispatch.yml` 监听 `push: tags: [v*]` 自动运行 release pipeline。当需要指定下游仓库列表或 tag 触发未生效时，使用 `workflow_dispatch` 手动触发。

> **注意**：`release-please.yml` 只负责运行 release-please-action（创建 tag + GitHub Release），不包含下游通知逻辑。下游通知由 `release-and-dispatch.yml` 完成。

### 手动通知

当自动通知未触发或需要补充通知时，使用 `workflow_dispatch`：

```bash
gh workflow run release-and-dispatch.yml \
  -f release_tag=v0.9.6 \
  -f dispatch_targets="hdot123/legal-core,hdot123/ingestion-registry" \
  -f dispatch_event_type="memory_release_published"
```

**参数说明**：
- `release_tag`：必填，版本号（如 `v0.9.6`）
- `dispatch_targets`：可选，逗号分隔的 `owner/repo` 列表
- `dispatch_event_type`：可选，默认 `memory_release_published`

### 下游消费项目

当前已配置的下游项目：
- `hdot123/legal-core`
- `hdot123/ingestion-registry`

消费项目收到 `repository_dispatch` 事件后，应自动更新 memory-core 依赖版本。

---

## 5. Hotfix 发版流程

### 场景

需要紧急修复生产环境 bug，不走常规 release-please 流程。

### 步骤

1. **创建 hotfix 分支**：
   ```bash
   git checkout -b hotfix/critical-bug-fix main
   ```

2. **修复 bug**：提交修复（使用 `fix:` 前缀）

3. **提交 PR**：走标准 PR 双门禁流程合并到 main

4. **等待 release-please**：release-please 会自动创建 Release PR（patch 版本）

5. **合并 Release PR**：确认后合并，自动完成发版

### 跳过 release-please（极端情况）

如果 release-please 完全不可用，使用手动发版流程（见第 2 节），但需要：
- 手动 bump 版本号到所有位置
- 手动打 tag 并 push
- 手动触发 `release-and-dispatch.yml`

> **警告**：手动发版后，下次 release-please 运行时可能会冲突。需要手动同步 `.release-please-manifest.json`。

---

## 6. 故障排查

### release-please workflow 失败

**症状**：合并 Release PR 后，tag 和 release 未自动创建。

**排查步骤**：

```bash
# 1. 检查 release-please workflow 日志
gh run list --workflow=release-please.yml --limit 5

# 2. 查看失败 job 的详细日志
gh run view <run-id> --log

# 3. 常见原因：
#    - permissions 不足（需要 contents: write, pull-requests: write）
#    - release-please-config.json 格式错误
#    - .release-please-manifest.json 版本号与 pyproject.toml 不一致
```

**修复方法**：
- 修复 config 文件后，重新 push 到 main 触发 workflow
- 或手动触发：`gh workflow run release-please.yml`

### Tag 版本与 pyproject.toml 不一致

**症状**：`release-and-dispatch.yml` 的 "Verify tag matches pyproject.toml version" 步骤失败。

**排查步骤**：

```bash
# 1. 检查 tag 版本
git tag -l "v*" | tail -5

# 2. 检查 pyproject.toml 版本
grep '^version = ' pyproject.toml

# 3. 检查 constants.py 版本
grep 'CURRENT_MEMORY_VERSION' memory_core/constants.py
```

**修复方法**：
- 删除错误的 tag：`git push origin :refs/tags/vX.Y.Z`
- 同步版本号到所有位置（见第 2 节清单）
- 重新打 tag 并 push

### Artifact 上传失败

**症状**：GitHub Release 已创建，但 `dist/*` 文件未上传。

**排查步骤**：

```bash
# 1. 检查 release workflow 日志
gh run list --workflow=release-and-dispatch.yml --limit 5
gh run view <run-id> --log

# 2. 常见原因：
#    - softprops/action-gh-release 权限不足
#    - dist/ 目录为空（构建失败）
#    - tag_name 与 release 不匹配
```

**修复方法**：
- 手动上传：`gh release upload vX.Y.Z dist/*`
- 或重新触发 workflow：`gh workflow run release-and-dispatch.yml -f release_tag=vX.Y.Z`

### 下游通知未触发

**症状**：Release 已创建，但下游项目未收到 `repository_dispatch` 事件。

**排查步骤**：

```bash
# 1. 检查 DISPATCH_TOKEN secret 是否配置
gh secret list | grep DISPATCH_TOKEN

# 2. 检查 workflow 日志中 dispatch 步骤
gh run view <run-id> --log | grep -A 10 "Dispatch downstream"

# 3. 常见原因：
#    - DISPATCH_TOKEN 未配置或过期
#    - dispatch_targets 为空
#    - 下游仓库权限不足
```

**修复方法**：
- 手动触发通知（见第 4 节）
- 更新 DISPATCH_TOKEN：`gh secret set DISPATCH_TOKEN --body '...'`

### Release PR 冲突

**症状**：release-please 创建的 Release PR 与 main 分支有冲突，无法合并。

**修复方法**：

```bash
# 1. 关闭当前 Release PR
gh pr close <pr-number>

# 2. 删除 release-please 创建的分支
git push origin :refs/heads/release-please-*

# 3. 重新触发 release-please
gh workflow run release-please.yml
```

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `.github/workflows/release-please.yml` | 自动发版工作流 |
| `.github/workflows/release-and-dispatch.yml` | 手动发版 + 下游通知 |
| `release-please-config.json` | release-please 配置 |
| `.release-please-manifest.json` | 当前版本清单 |
| `scripts/release_rollback.sh` | 回滚脚本 |
| `scripts/repo_health_check.sh` | 版本一致性检查 |
| `CONTRIBUTING.md` | 发版流程概述 |
| `docs/guides/release-guide.md` | 发版指南（简化版） |

---

## 快速参考

### 正常发版

```bash
# 1. 提交 conventional commit，合并到 main
# 2. 等待 release-please 创建 Release PR
# 3. 合并 Release PR
# 4. 自动完成
```

### 紧急发版（release-please 故障）

```bash
# 1. 手动同步版本号（见第 2 节清单）
# 2. git tag vX.Y.Z && git push origin vX.Y.Z
# 3. 验证：gh release view vX.Y.Z
```

### 回滚

```bash
scripts/release_rollback.sh v0.9.x
```

### 下游通知

```bash
gh workflow run release-and-dispatch.yml \
  -f release_tag=v0.9.6 \
  -f dispatch_targets="hdot123/legal-core,hdot123/ingestion-registry"
```
