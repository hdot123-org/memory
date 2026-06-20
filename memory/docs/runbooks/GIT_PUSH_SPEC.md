# Git Push 规范

> **环境声明：本规范基于特定部署环境（GitLab 为 source of truth + GitHub 只读镜像），不适用于所有 memory-core 消费者。** 你的项目可以使用任何 Git 托管平台。以下流程仅描述本环境的 GitLab → GitHub 单向同步模型。

## 铁律：GitLab → GitHub 单向同步

### 基本原则

1. **代码只推 GitLab** — Agent/人/CI 都只 push 到 GitLab，创建 MR
1a. **禁止直接推送到 main** — main 分支已设为 "No one can push"（GitLab 平台级保护），任何人都必须走 feature 分支 + MR 流程
1b. **所有推送必须创建 MR** — 脚本默认自动创建 MR，合并后自动删除源分支。仅 WIP 场景可用 `--no-mr` 跳过
2. **必须使用 API 推送** — 所有推送必须通过 `scripts/gitlab_api_push.py`，**禁止手动 git add/commit/push**
3. **CI 门禁** — test + health-check 通过后才可合并到 main
4. **GitHub 是只读镜像** — 只有 GitLab CI 的 sync-to-github job 可以推 GitHub
5. **禁止直推 GitHub** — 任何 `git push origin main` 都是违规，会破坏单源真相
6. **违规恢复** — 如果意外直推 GitHub，回退 GitHub commit，重新走 GitLab 流程

### 推送工具

使用 `scripts/gitlab_api_push.py` 通过 GitLab Commits API 推送文件，绕过本地 git hook。

```bash
# 标准用法 — 自动创建分支、自动创建 MR
python3 scripts/gitlab_api_push.py \
  --branch "fix/my-feature" \
  --message "feat(scope): description" \
  --file path/to/file1.md \
  --file path/to/file2.md

# WIP 场景 — 推送但不创建 MR
python3 scripts/gitlab_api_push.py \
  --branch "fix/my-feature" \
  --message "WIP: 工作中" \
  --file path/to/file1.md \
  --no-mr
```

| 参数 | 说明 |
|------|------|
| `--branch` | 目标分支（**禁止 main/master**） |
| `--message` | commit 消息 |
| `--file` | 要推送的文件（可多次） |
| `--delete` | 要删除的文件（可多次） |
| `--auto-branch` | 自动创建分支（**推送文件时默认启用**） |
| `--no-mr` | 跳过自动创建 MR（仅 WIP 场景使用） |
| `--create-mr` | 显式创建 MR（不推文件时使用） |
| `--target-branch` | MR 目标分支（默认 main） |
| `--mr-title` | MR 标题（默认用 commit message） |
| `--mr-description` | MR 描述 |

### 项目路径

| 项目 | 路径 |
|------|------|
| memory-core | `infra/memory-core` |
| workbot | `aedu/workbot` |

### Token

工具自动从环境变量发现 token：
1. `GITLAB_ADMIN_TOKEN`（admin 权限，用于 `infra/memory-core`）
2. `CE_GITLAB_TOKEN`（project bot，用于 `aedu/workbot`）

### 禁止操作

| 操作 | 原因 |
|------|------|
| `git add` / `git commit` | 被 Execute hook 拦截 |
| `git push` | 被 Execute hook 拦截 |
| `git push origin main` | 破坏单源真相 |
| `git push origin --force` | 覆盖 GitHub 历史 |
| 直接在 GitHub 修改文件 | 不同步单源 |
| 在 GitHub 创建 MR/PR | 绕过 CI 门禁 |
| `--branch main` 或 `--branch master` | main 分支已保护，脚本层面拒绝 + 平台层面 403 |
| 推送文件但不创建 MR（无 --no-mr） | 脚本默认自动创建 MR，确保所有代码走 MR 审查 |

### 分支生命周期（自动）

```
推送文件到 feature 分支（--auto-branch 默认启用）
        ↓
  自动创建 MR（force_remove_source_branch=True）
        ↓
  CI pipeline（test + health-check）
        ↓
  MR 合并到 main（Maintainer 审批）
        ↓
  源分支自动删除（GitLab 设置）
        ↓
  sync-to-github job → GitHub main
```

规则：
- 推送文件时 `--auto-branch` 和 MR 创建都是**默认行为**，不需要手动指定
- MR 合并后源分支**自动删除**，不会累积
- GitHub 侧也开启了 `delete_branch_on_merge`，Dependabot PR 合并后也会自动清理
- 只有 WIP 场景使用 `--no-mr` 跳过 MR 创建

### CI Sync 机制

```
GitLab main merge (MR 合并)
        ↓
  pipeline (test + health-check)
        ↓
  sync-to-github job
        ↓
  git push origin main (GitHub)
```

如果 sync-to-github 失败：
1. 检查 CI/CD Variables 中的 GITHUB_TOKEN 是否过期
2. 手动重试 job（GitLab Web UI > Retry）
3. 不要手动推送到 GitHub
