# CI/CD 运维手册：GitLab CI 配置与发布自动化

> **环境声明：本手册内容基于特定部署环境（GitLab + GitHub 镜像 + Shell Runner），不适用于所有 memory-core 消费者。** 如果你的环境使用其他 CI/CD 方案（GitHub Actions / Jenkins / Drone 等），请参考你自己的 CI 配置，本手册仅作为 GitLab CI 实现参考。
>
> 最后更新：2026-05-25 | 基于 v0.5.0 发布故障排查实战总结

---

## 一、架构概览

### 单向同步架构

```
开发者 → GitLab (source of truth) → CI Pipeline → GitHub (read-only mirror)
                    ↓
              Tag Pipeline
              ├─ sync-tags-to-github
              ├─ create-release (GitLab Release API)
              └─ github-release (GitHub Release API)
```

**铁律：代码只推 GitLab，GitHub 是只读镜像。**

- GitLab 项目：`infra/memory-core`（`node-REDACTED.ts.net`）
- GitHub 镜像：`hdot123/memory`（`github.com`）
- Runner：`<shell-runner>`（Shell Runner，非 Docker）

### Pipeline Stage 流程

| Stage | Jobs | 触发条件 |
|-------|------|----------|
| test | `test` | 所有 push |
| health_check | `health-check` | 所有 push |
| sync | `sync-to-github` | main 分支 push |
| sync | `sync-tags-to-github` | Tag push |
| release | `create-release` | Tag push |
| release | `github-release` | Tag push（依赖 sync-tags-to-github） |

---

## 二、CI 变量清单

| 变量名 | 用途 | Protected | Masked | 注意事项 |
|--------|------|-----------|--------|----------|
| `GITHUB_TOKEN` | GitHub 推送 + Release API | **必须设为 `false`** | true | Tag Pipeline 不是 protected ref，设为 true 会导致变量不可用 |

### GITHUB_TOKEN 设置方法

1. 生成：GitHub → Settings → Developer settings → Personal access tokens → `repo` scope
2. 存储：GitLab → Project → Settings → CI/CD → Variables
3. **关键配置：`Protected = false`**（否则 Tag pipeline 无法获取变量）

### 为什么 Protected 必须为 false？

GitLab 的 Protected 变量只在 Protected Refs（Protected Branches + Protected Tags）上可用。如果 tag 不在 Protected Tags 列表中，变量值为空。为确保所有 tag 都能发布，设为 `false`。

---

## 三、Shell Runner 注意事项

当前 Runner 是 **Shell Runner**（不是 Docker Runner），这决定了 CI 配置的写法：

| 限制 | 影响 | 解决方案 |
|------|------|----------|
| 无 Docker | 不能用 `image:` 指令 | 所有 job 直接在宿主机执行 |
| 无 `apk` | 不能安装 Alpine 包 | 用 `curl` + API 替代 `gh` CLI |
| 无 `release-cli` | GitLab 18.x 已弃用 | 用 `curl` + GitLab Release API |
| 无 `gh` CLI | 不能用 `gh release create` | 用 `curl` + GitHub Release API |

### create-release：curl 替代 release-cli

```yaml
create-release:
  stage: release
  rules:
    - if: $CI_COMMIT_TAG
  script:
    - VERSION="${CI_COMMIT_TAG#v}"
    - NOTES=$(sed -n "/## \\[${VERSION}\\]/,/## \\[/p" CHANGELOG.md | head -n -1)
    - if [ -z "$NOTES" ]; then NOTES="See CHANGELOG.md for details."; fi
    - |
      PAYLOAD=$(python3 -c "import json,sys; notes=sys.stdin.read(); print(json.dumps({'tag_name':'$CI_COMMIT_TAG','name':'memory-core $CI_COMMIT_TAG','description':notes}))" <<< "$NOTES")
      curl --header "Content-Type: application/json" \
           --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
           --data "$PAYLOAD" \
           "$CI_API_V4_URL/projects/$CI_PROJECT_ID/releases"
  variables:
    GITLAB_TOKEN: "$CI_JOB_TOKEN"
```

### github-release：curl 替代 gh CLI

```yaml
github-release:
  stage: release
  needs: [sync-tags-to-github]
  rules:
    - if: $CI_COMMIT_TAG
  script:
    - VERSION="${CI_COMMIT_TAG#v}"
    - NOTES=$(sed -n "/## \\[${VERSION}\\]/,/## \\[/p" CHANGELOG.md | head -n -1)
    - if [ -z "$NOTES" ]; then NOTES="See CHANGELOG.md for details."; fi
    - |
      PAYLOAD=$(python3 -c "import json,sys; notes=sys.stdin.read(); print(json.dumps({'tag_name':'$CI_COMMIT_TAG','target_commitish':'main','name':'memory-core $CI_COMMIT_TAG','body':notes,'draft':False,'prerelease':False}))" <<< "$NOTES")
      curl --header "Authorization: token $GITHUB_TOKEN" \
           --header "Content-Type: application/json" \
           --data "$PAYLOAD" \
           "https://api.github.com/repos/hdot123/memory/releases"
```

---

## 三.5、CI 配置自检机制

`scripts/ci_health_check.sh` 包含三层自动防护，在 `health-check` stage 中运行：

| 检查项 | 检查方式 | 失败行为 |
|--------|---------|----------|
| `.gitlab-ci.yml` 非空 | `[ ! -s .gitlab-ci.yml ]` | exit 1（阻断 pipeline） |
| YAML 语法有效 | `python3 yaml.safe_load()` | exit 1（阻断 pipeline） |
| 必要 stage 存在 | 检查 test/health_check/sync | exit 1（阻断 pipeline） |

同时，`infra/ci-templates/ci-config-check.yml` 共享模板在 `.pre` stage 更早拦截。

**防护链**：`.pre`(共享模板自检) → `test`(ruff+boundary+pytest) → `health-check`(内存系统+污染检测+CI配置自检) → `sync`(推送镜像)

---

## 四、发布流程

### 标准发布步骤

```bash
# 1. 确保 CHANGELOG.md 已更新版本条目
# 2. 提交并推送到 GitLab main
git push gitlab main

# 3. 创建 tag 并推送
git tag v0.X.0
git push gitlab v0.X.0

# 4. 等待 Tag Pipeline 完成（约 2-3 分钟）
# 5. 验证 GitHub Release 已创建
gh release list | head -3
```

### Tag 更新（紧急修复）

如果 tag 指向的 commit 上的 CI 配置有问题，需要移动 tag：

```bash
# 1. 确认 Protected Tags 不会阻止删除
# 如果有 v* protected pattern，先在 GitLab → Settings → Repository → Protected Tags 中临时移除

# 2. 删除并重建 tag
git tag -d v0.X.0
git tag v0.X.0 <new-commit>
git push gitlab :refs/tags/v0.X.0  # 删除远程
git push gitlab v0.X.0             # 推送新 tag

# 3. GitHub 上的旧 tag 也需要同步更新
git push origin :refs/tags/v0.X.0
git push origin v0.X.0

# 4. 恢复 Protected Tags（如果有）
```

---

## 五、故障排查手册

### 故障 1：`.gitlab-ci.yml` 被意外清空

**症状**：Pipeline 不触发，或触发后无 job。

**排查**：
```bash
git show gitlab/main:.gitlab-ci.yml | wc -l
# 如果输出 0，说明文件被清空
```

**修复**：从历史 commit 恢复，通过 MR 合并。

**预防**：MR merge 前检查 diff 中是否包含 `.gitlab-ci.yml` 的异常变更。

---

### 故障 2：Tag Pipeline 中 `GITHUB_TOKEN` 为空

**症状**：`sync-tags-to-github` 报 `Authentication failed`，日志中 URL 显示为 `**********/hdot123/memory.git`。

**排查**：
```bash
curl -s --header "PRIVATE-TOKEN: $TOKEN" \
  "$GITLAB_HOST/api/v4/projects/$PID/variables/GITHUB_TOKEN" | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('protected'))"
```

**修复**：
```bash
curl -s --request PUT --header "PRIVATE-TOKEN: $TOKEN" \
  --header "Content-Type: application/json" \
  --data '{"protected": false}' \
  "$GITLAB_HOST/api/v4/projects/$PID/variables/GITHUB_TOKEN"
```

---

### 故障 3：Release Job 报 `command not found`

**症状**：`release-cli: command not found` 或 `apk: command not found`。

**原因**：CI 配置使用了 Docker image 指令，但 Runner 是 Shell Runner。

**修复**：改用 `curl` + API 方式（见第三节）。

---

### 故障 4：Tag Push 被 `already exists` 拒绝

**症状**：`sync-tags-to-github` 报 `! [rejected] v0.X.0 -> v0.X.0 (already exists)`。

**原因**：GitHub 上已有同名 tag（之前同步的），新 tag 指向不同 commit。

**修复**：
```bash
git push origin :refs/tags/v0.X.0  # 先删 GitHub 上的
git push origin v0.X.0             # 重新推送
```

---

### 故障 5：Protected Tag 阻止删除/更新

**症状**：`GitLab: You can only delete protected tags using the web interface`。

**修复**：
```bash
# 临时取消保护
curl -s --request DELETE --header "PRIVATE-TOKEN: $TOKEN" \
  "$GITLAB_HOST/api/v4/projects/$PID/protected_tags/v%2A"

# 操作完成后重新保护
curl -s --request POST --header "PRIVATE-TOKEN: $TOKEN" \
  --header "Content-Type: application/json" \
  --data '{"name": "v*", "create_access_level": 40}' \
  "$GITLAB_HOST/api/v4/projects/$PID/protected_tags"
```

---

### 故障 6：Cloudflare 代理阻断 API POST

**症状**：GitLab API GET 请求正常，POST/PUT 返回 `400 The plain HTTP request was sent to HTTPS port`。

**原因**：Cloudflare 将 HTTP 请求重定向到 HTTPS，Python 的 TLS 握手失败。

**解决**：使用 `git push` 代替 API POST/PUT 调用，或通过 GitLab Web UI 操作。

---

### 故障 7：CI runner 预装 pytest 版本与项目不兼容

**症状：**
- `pip show pytest` 报错 `WARNING: Package(s) not found: pytest` 或 `RECORD` 文件缺失
- pytest 执行失败，Pipeline 阻断
- 日志显示 runner 预装了 pytest 9.0.3，但与项目 pytest 8.x 配置冲突

**根因：**
1. runner 预装的 pytest 通过系统包管理器安装，缺少 pip `RECORD` 元数据文件
2. 旧版 `.pyc` 缓存污染叠加，导致 import 错误
3. 详见决策文档 [D-002: pytest 版本策略与 CI 缓存治理](../decisions/d-002-ci-pytest-strategy.md)

**解决方案：**

1. **锁定 pytest 版本范围**（在 `setup.cfg` / `pyproject.toml` 中）：
   ```
   pytest>=8.0,<9.0
   ```

2. **在 CI before_script 中清理缓存**：
   ```yaml
   before_script:
     - find . -type f -name "*.pyc" -delete
     - find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
   ```

3. **设置环境变量禁止写入字节码**：
   ```yaml
   variables:
     PYTHONDONTWRITEBYTECODE: "1"
   ```

4. **使用 `--no-cache-dir` 安装**：
   ```yaml
   script:
     - pip install --no-cache-dir -e .
   ```

**关联 Issue：** INFRA-5（memory-core v0.6.0 升级，Pipeline #392 失败触发）

---

## 六、GitLab API 速查

```bash
GITLAB_HOST="http://node-REDACTED.ts.net"
PID=4
TOKEN=$(git remote get-url gitlab | sed 's|http://||' | cut -d'@' -f1 | cut -d':' -f2)

# Pipeline 列表
curl -s --header "PRIVATE-TOKEN: $TOKEN" "$GITLAB_HOST/api/v4/projects/$PID/pipelines?per_page=5"

# Pipeline Jobs
curl -s --header "PRIVATE-TOKEN: $TOKEN" "$GITLAB_HOST/api/v4/projects/$PID/pipelines/<ID>/jobs"

# Job 日志
curl -s --header "PRIVATE-TOKEN: $TOKEN" "$GITLAB_HOST/api/v4/projects/$PID/jobs/<ID>/trace" | tail -20

# 重试 Pipeline
curl -s --request POST --header "PRIVATE-TOKEN: $TOKEN" "$GITLAB_HOST/api/v4/projects/$PID/pipelines/<ID>/retry"

# CI 变量
curl -s --header "PRIVATE-TOKEN: $TOKEN" "$GITLAB_HOST/api/v4/projects/$PID/variables"
```

---

## 七、经验教训

| # | 教训 | 预防措施 |
|---|------|----------|
| 1 | MR merge 可能意外清空文件 | MR 合并前检查 `.gitlab-ci.yml` diff |
| 2 | Protected 变量对非 Protected Tag 不可用 | `GITHUB_TOKEN` 设为 `protected: false` |
| 3 | Shell Runner 不支持 Docker image/apt/apk | CI 配置只用 curl + python3 + bash |
| 4 | Tag 重复 push 到 GitHub 会被 reject | 更新 tag 时先删 GitHub 旧 tag |
| 5 | Cloudflare 代理对 POST 请求不友好 | 用 git push 替代 API POST |
| 6 | GitLab 18.x 弃用 release-cli | 用 GitLab Release API + curl |
| 7 | runner 预装 pytest 版本冲突 | 锁定版本范围 + 清理缓存 + `PYTHONDONTWRITEBYTECODE` |

---

## 八、GitHub 同步故障排查（2026-05-27 更新）

### 常见问题

#### 问题 1：`remote: fatal: did not receive expected object`

**症状：** sync-to-github 失败，日志显示 `remote unpack failed: index-pack failed`

**根因：** GitLab CI 默认 `GIT_DEPTH: 20`（浅克隆），push 时缺少祖先 commit 对象。

**修复：** 在 github-sync.yml 中设置 `GIT_DEPTH: "0"` 禁用浅克隆。

#### 问题 2：`remote: error: GH013: Repository rule violations`

**症状：** sync-to-github 失败，日志显示 `refusing to allow a Personal Access Token to create or update workflow ... without workflow scope`

**根因：** GitHub PAT 缺少 `workflow` scope。当 `.github/workflows/*` 文件是**新建**时，GitHub 要求 token 显式有 workflow 权限。更新已有文件则只需 `repo` scope。

**修复：**
1. 生成新 PAT：GitHub → Settings → Developer settings → Personal access tokens → 勾选 `repo` + `workflow`
2. 更新 GitLab CI 变量 `GITHUB_TOKEN`

#### 问题 3：`remote: Repository not found`

**症状：** sync-to-github 失败，URL 显示 `https://github.com//.git/`（空 owner/repo）

**根因：** github-sync.yml v2 使用通用变量 `$GITHUB_REPO_OWNER` 和 `$GITHUB_REPO_NAME`，但项目 CI 变量未配置。

**修复：** 在 GitLab CI/CD Variables 中添加：
- `GITHUB_REPO_OWNER` = `hdot123`
- `GITHUB_REPO_NAME` = `memory`

### 完整修复记录

| 日期 | 问题 | 修复措施 |
|------|------|----------|
| 2026-05-27 | `did not receive expected object` | github-sync.yml 添加 `GIT_DEPTH: "0"` |
| 2026-05-27 | `GH013: workflow scope` | 新 PAT 包含 `repo` + `workflow` |
| 2026-05-27 | `Repository not found` | 添加 `GITHUB_REPO_OWNER` / `GITHUB_REPO_NAME` CI 变量 |
| 2026-05-27 | 模板 v2 通用化 | github-sync.yml 改为变量化 URL，支持多项目复用 |

### github-sync.yml v2 变量说明

新版模板使用通用变量，所有项目只需 include 即可：

```yaml
include:
  - project: 'infra/ci-templates'
    file: 'github-sync.yml'
```

**必需 CI 变量：**

| 变量 | 示例值 | 说明 |
|------|--------|------|
| `GITHUB_TOKEN` | `ghp_xxxx...` | GitHub PAT（repo + workflow scope） |
| `GITHUB_REPO_OWNER` | `hdot123` | GitHub 用户名/组织 |
| `GITHUB_REPO_NAME` | `memory` | GitHub 仓库名 |

**可选 CI 变量：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GITHUB_REPO_BRANCH` | `main` | 同步目标分支 |

### CI 变量清单（更新版）

| 变量名 | 用途 | Protected | Masked | 注意事项 |
|--------|------|-----------|--------|----------|
| `GITHUB_TOKEN` | GitHub 推送 | **false** | true | 需 repo + workflow scope |
| `GITHUB_REPO_OWNER` | GitHub 用户名 | false | false | 如 hdot123 |
| `GITHUB_REPO_NAME` | GitHub 仓库名 | false | false | 如 memory |
| `GITHUB_REPO_BRANCH` | 目标分支 | false | false | 默认 main |
