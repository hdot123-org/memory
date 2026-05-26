# Git Push 规范

## 铁律：GitLab → GitHub 单向同步

### 基本原则

1. **代码只推 GitLab** — Agent/人/CI 都只 push 到 GitLab，创建 MR
2. **CI 门禁** — test + health-check 通过后才可合并到 main
3. **GitHub 是只读镜像** — 只有 GitLab CI 的 sync-to-github job 可以推 GitHub
4. **禁止直推 GitHub** — 任何 `git push origin main` 都是违规，会破坏单源真相
5. **违规恢复** — 如果意外直推 GitHub，回退 GitHub commit，重新走 GitLab 流程

### 工作流程

```bash
# 1. 创建特性分支
git checkout -b feat/my-feature

# 2. 提交变更（遵守 conventional commits）
git commit -m "feat(scope): description"

# 3. 推送到 GitLab
git push gitlab feat/my-feature

# 4. 创建 MR（GitLab Web 或 API）
# MR target: main

# 5. CI 通过后合并
# sync-to-github 自动同步到 GitHub
```

### Remote 配置

| Remote | URL | 用途 |
|--------|-----|------|
| `gitlab` | `http://node-REDACTED.ts.net/infra/memory-core.git` | 唯一可推送的 remote |
| `origin` | `https://github.com/hdot123/memory.git` | 只读镜像，禁止 push |

### 分支策略

| 分支 | 保护规则 | 说明 |
|------|---------|------|
| `main` | MR + CI 门禁 | 稳定分支 |
| `fix/*` | 无保护 | Bug 修复 |
| `feat/*` | 无保护 | 新功能 |
| `refactor/*` | 无保护 | 重构 |
| `v*.*.*` | tag | 发布标签 |

### CI Sync 机制

```
GitLab main merge
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

### 禁止操作

| 操作 | 原因 |
|------|------|
| `git push origin main` | 破坏单源真相 |
| `git push origin --force` | 覆盖 GitHub 历史 |
| 直接在 GitHub 修改文件 | 不同步单源 |
| 在 GitHub 创建 MR/PR | 绕过 CI 门禁 |
