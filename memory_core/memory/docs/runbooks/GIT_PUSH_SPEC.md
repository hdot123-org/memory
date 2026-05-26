# Git Push 规范

## 铁律：GitLab → GitHub 单向同步

### 基本原则

1. **代码只推 GitLab** — Agent/人/CI 都只 push 到 GitLab，创建 MR
2. **必须使用 API 推送** — 所有推送必须通过 `scripts/gitlab_api_push.py`，**禁止手动 git add/commit/push**
3. **CI 门禁** — test + health-check 通过后才可合并到 main
4. **GitHub 是只读镜像** — 只有 GitLab CI 的 sync-to-github job 可以推 GitHub
5. **禁止直推 GitHub** — 任何 `git push origin main` 都是违规，会破坏单源真相
6. **违规恢复** — 如果意外直推 GitHub，回退 GitHub commit，重新走 GitLab 流程

### 推送工具

使用 `scripts/gitlab_api_push.py` 通过 GitLab Commits API 推送文件，绕过本地 git hook。

```bash
python3 scripts/gitlab_api_push.py \
  --project "infra/memory-core" \
  --branch "fix/my-feature" \
  --message "feat(scope): description" \
  --file path/to/file1.md \
  --file path/to/file2.md \
  --create-mr \
  --target-branch main
```

| 参数 | 说明 |
|------|------|
| `--project` | GitLab 项目路径（可选，自动检测） |
| `--branch` | 目标分支 |
| `--message` | commit 消息 |
| `--file` | 要推送的文件（可多次） |
| `--create-mr` | 创建 MR |
| `--target-branch` | MR 目标分支（默认 main） |
| `--auto-branch` | 自动创建分支 |

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
