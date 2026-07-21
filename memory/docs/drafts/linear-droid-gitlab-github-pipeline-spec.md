# 技术规格书：Linear → Droid → GitLab → GitHub 全链路

> 草稿版本 | 最后更新：2026-06-02
> 状态：待测试验证
> **注意：测试跑通后需迁移到 `memory/docs/design/` 正式归档，并删除本文件。**

## 1. 架构总览

```
Linear Issue → n8n(过滤+转发) → Mac webhook:5555 → trigger-droid.sh → droid exec CLI
    → 代码变更 → gitlab_api_push.py → GitLab MR → CI Pipeline
    → merge main → sync-to-github → GitHub 镜像
    ↘ Linear comment 回写（执行结果 + MR 链接）
```

**核心原则**：Linear 发通知，n8n 只转发唤醒，Droid 自治执行，GitLab 驱动状态流转。

---

## 2. 环节 1：Linear Webhook

| 属性 | 值 |
|------|-----|
| 目标 URL | `https://webhook.exa.edu.kg/webhook/linear-factory`（Cloudflare Tunnel） |
| 监听事件 | Issue (create/update), Comment (create) |
| 作用域 | `allPublicTeams: true` |
| 签名 Secret | 1Password `sever` vault，条目 `elgcm2nzfza2hjb3yffpkijj7y` |

**Webhook payload 关键字段：**

```json
{
  "action": "create",
  "type": "Issue",
  "data": {
    "id": "<uuid>",
    "identifier": "INFRA-5",
    "title": "...",
    "team": { "key": "INFRA" }
  }
}
```

---

## 3. 环节 2：n8n 工作流

| 属性 | 值 |
|------|-----|
| 部署位置 | node-22 (Tailscale `100.100.1.22:5678`) |
| Workflow ID | `zV3mKyKEI04AanmI` |
| 节点链 | Webhook → Filter → Extract Fields → Guard → 转发到 Mac webhook:5555 |

**Extract Fields 提取的字段：**

| 字段 | 来源 |
|------|------|
| `issueRef` | `data.identifier` 或 `data.issue.identifier` |
| `issueUuid` | `data.id` 或 `data.issue.id` |
| `teamKey` | `data.team.key` |
| `triggerSource` | `issue` / `comment` |
| `eventType` | `Issue.create` / `Comment.create` |

---

## 4. 环节 3：Mac webhook 网关

| 属性 | 值 |
|------|-----|
| 服务 | `adnanh/webhook` v2.8.3，监听 `0.0.0.0:5555` |
| Binary | `~/.factory/webhook/bin/webhook` |
| 配置 | `~/.factory/webhook/hooks.json` |
| 进程管理 | launchd (`com.factory.webhook.plist`)，RunAtLoad + KeepAlive |
| 验证 | `X-Webhook-Token` header 匹配 `WEBHOOK_SECRET_TOKEN` |

**Hook 定义：**

| Hook ID | 触发脚本 | 验证方式 | 用途 |
|---------|----------|----------|------|
| `linear-to-droid` | `trigger-droid.sh` | `X-Webhook-Token` | Linear issue 触发 Droid |
| `wiki-refresh` | `wiki-refresh.sh` | `X-Gitlab-Token` | main 合并后刷新 Wiki |
| `ci-failed` | `ci-failed.sh` | `X-CI-Secret` | CI 失败通知 |

**linear-to-droid 参数传递：**

- **位置参数（7个）**：`action`, `type`, `data.identifier`, `data.id`, `data.team.key`, `data.title`, `data.description`
- **环境变量（9个）**：`LINEAR_ACTION`, `LINEAR_TYPE`, `LINEAR_ISSUE_REF`, `LINEAR_ISSUE_UUID`, `LINEAR_TEAM_KEY`, `LINEAR_TITLE`, `LINEAR_DESCRIPTION`, `LINEAR_SIGNATURE`, `WEBHOOK_TOKEN`
- **响应**：`{"status":"accepted","issueRef":"..."}`（立即返回，异步执行）

---

## 5. 环节 4：仓库路由（trigger-droid.sh）

**脚本路径**：`~/.factory/webhook/scripts/trigger-droid.sh`

**流程：**

1. 提取 6 个位置参数
2. 通过 `op` CLI 从 1Password 获取 `LINEAR_API_KEY`
3. 读取 `~/.factory/config/repositories.yml`，按 `teamKey` 匹配 `repoPath`
4. 路由失败 → 调用 `write_comment.py` 回写 Linear 告知无法接单，exit 0
5. 路由成功 → 后台异步启动 `droid exec`（`&`），脚本立即 `exit 0`

**仓库路由表：**

| Team | teamKey | GitLab 项目 | 本地路径 |
|------|---------|------------|----------|
| infra | INFRA | `infra/memory-core` | `~/memory` |
| gateway | GW | `root/gateway-admin` | `~/tool/gateway-admin` |
| workbot | WB | `root/workbot` | `~/workbot` |

**Droid 启动参数：**

```bash
droid exec \
  --auto medium \
  --output-format json \
  --tag '{"name":"linear-gateway","metadata":{"issueRef":"INFRA-5","teamKey":"INFRA","triggerSource":"issue","eventType":"Issue.create"}}' \
  "Linear 门铃触发。IssueRef=INFRA-5。Team=INFRA。请按 linear-gateway skill 执行。"
```

**环境变量**：`DROID_MODEL`（默认 `custom:GLM-5.1-(node-01)-0`），`LINEAR_API_KEY`

---

## 6. 环节 5：Droid 执行 + GitLab MR

### 6.1 Droid 执行

- Droid 读取 Linear issue 上下文（通过 Linear API + 1Password 凭证）
- 在本地仓库执行代码变更
- 验证：运行测试 + lint

### 6.2 GitLab 推送

**工具**：`scripts/gitlab_api_push.py`（通过 GitLab Commits API，绕过本地 git hook）

**规则：**

- **禁止** `git add` / `git commit` / `git push`（被 hooks 拦截）
- **禁止直推 main**（平台级保护），必须走 feature 分支 + MR
- **Token 优先级**：`GITLAB_ADMIN_TOKEN` > `CE_GITLAB_TOKEN` > remote URL 提取
- **默认行为**：`--auto-branch` 自动创建 feature 分支 + 自动创建 MR + 合并后自动删除源分支
- **Commit 消息必须中文**
- **MR 描述必须包含 Linear issue ID**（如 `Fixes INFRA-5`）

**GitLab 地址**：`http://node-15.tail5e888.ts.net`（Tailscale tailnet 内）

---

## 7. 环节 6：Linear 回写

**工具**：`~/.factory/webhook/scripts/write_comment.py`

- 调用 Linear GraphQL API `commentCreate` mutation
- Authorization header：`LINEAR_API_KEY`（无 Bearer 前缀）

**回写模板：**

| 场景 | 内容 |
|------|------|
| 成功 | 改动摘要、分支名、MR 链接、测试结果 |
| 失败 | 失败阶段、错误摘要、阻塞原因 |
| 路由失败 | 告知无法接单原因 |

**状态流转（GitLab ↔ Linear 集成自动处理，Droid 不直接改 Done）：**

| GitLab 事件 | Linear 状态 |
|------------|------------|
| MR open | In Progress |
| Review requested | In Review |
| MR merge | Done |

**GitLab Webhooks（3 个项目均已配置）：**

| GitLab 项目 | 项目 ID | Webhook ID |
|------------|---------|------------|
| `infra/memory-core` | 4 | 12 |
| `root/gateway-admin` | 8 | 13 |
| `root/workbot` | 10 | 14 |

---

## 8. 环节 7：CI Pipeline

**Stages**：`test` → `health_check` → `sync` → `release` → `wiki` → `notify`

| Job | Stage | 触发条件 | 关键操作 |
|-----|-------|----------|----------|
| `test` | test | push 含 .py 等文件 | ruff check + boundary check + pytest |
| `health-check` | health_check | 所有 push | ci_health_check.sh |
| `sync-to-github` | sync | push main（共享模板） | GitLab → GitHub 镜像 |
| `sync-tags-to-github` | sync | tag push（共享模板） | GitHub tag 同步 |
| `create-release` | release | tag push | GitLab Release API |
| `github-release` | release | tag push | GitHub Release API |
| `droid-wiki-refresh` | wiki | push main | 调用 `localhost:5555/hooks/wiki-refresh` |
| `test-failed` | notify | on_failure | 调用 Mac webhook `/hooks/ci-failed` |

**Runner 类型**：Shell Runner（非 Docker），无 `apk`/`gh` CLI/`release-cli`，全部用 `curl` + `python3`

**CI 已知问题与对策：**

| 问题 | 对策 |
|------|------|
| Runner 预装 pytest 9.0.3 无 RECORD | 锁定 `pytest>=8.0,<9.0` + `--no-cache-dir` |
| .pyc 缓存污染 | before_script 清理 + `PYTHONDONTWRITEBYTECODE=1` |

---

## 9. 环节 8：GitHub 同步

- **GitHub 是只读镜像**，只有 `sync-to-github` CI job 可以推送
- **禁止直推 GitHub**，任何 `git push origin main` 都是违规，会破坏单源真相
- **违规恢复**：回退 GitHub commit，重新走 GitLab 流程

---

## 10. CI 失败自愈链路

```
CI test/health-check 失败
    → test-failed job（on_failure）
    → curl Mac webhook /hooks/ci-failed
    → ci-failed.sh
    → Linear comment 回写到对应 issue
    → Linear webhook → n8n → trigger-droid.sh
    → Droid 被唤醒修复
```

---

## 11. Wiki 刷新链路

```
GitLab push main
    → droid-wiki-refresh CI job
    → curl localhost:5555/hooks/wiki-refresh
    → wiki-refresh.sh
    → git pull + droid exec /wiki
    → Factory App Wiki 更新
```

---

## 12. 凭证管理

| 凭证 | 存储位置 | 用途 |
|------|----------|------|
| Linear API Key | 1Password `sever` / `elgcm2nzfza2hjb3yffpkijj7y` | Droid + webhook 读写 Linear |
| Linear Webhook Secret | 同上 | GitLab 集成签名验证 |
| GitLab Admin Token | 1Password `sever` / `c3lbbfzby6z2btt6d7aheqlwfe` | 最高优先级推送 |
| GitLab Project Token | 环境变量 `CE_GITLAB_TOKEN` | 项目 bot |
| GITHUB_TOKEN | GitLab CI 变量 | GitHub 同步 + Release |
| Webhook Secret Token | launchd plist | adnanh/webhook 验证 |
| n8n API Key | 1Password `sever` | n8n 管理 |

---

## 13. 安全机制

| 层级 | 措施 |
|------|------|
| 网络层 | Tailscale 加密隧道（n8n → Mac webhook），不暴露公网 |
| 应用层 | X-Webhook-Token / X-Gitlab-Token / X-CI-Secret header 验证 |
| Cloudflare | nginx 路径过滤（仅 `/webhook/*`、`/webhook-test/*`、`/healthz` 放行） |
| 进程 | launchd 管理，非 root 权限 |
| 代码保护 | main 分支 "No one can push"，必须走 MR |

---

## 14. 错误处理

| 环节 | 错误场景 | 处理方式 |
|------|----------|----------|
| 仓库路由 | repositories.yml 不存在 / teamKey 无匹配 | 回写 Linear comment 告知无法接单，exit 0 |
| Droid 执行 | exit code ≠ 0 | 提取错误摘要（前500字符），回写 Linear |
| Linear 回写 | UUID 或 API Key 为空 | 记录 WARN 日志，静默跳过 |
| CI sync-to-github | GITHUB_TOKEN 过期 / scope 不足 | 检查 token + retry（max 2 次） |
| CI pytest 版本冲突 | runner 预装版本不兼容 | 锁定版本 + 清理缓存 |
| GitHub Release | tag 已存在 | 先删 GitHub 旧 tag 再推 |

---

## 15. INFRA-5 实战记录

| 尝试 | 结果 | 原因 |
|------|------|------|
| 第1-2次 | ❌ 失败 | repositories.yml 路由配置问题 |
| 第3次 | ❌ 失败 | `droid: command not found`（trigger-droid.sh 第113行） |
| 第4次 | ❌ 未接单 | delegate 为空 + source-repo-readonly 约束 |
| 第5次 | ✅ 成功 | 31 文件变更，62 测试通过，MR #40 创建 |
| CI Pipeline #392 | ❌ 失败 | runner 预装 pytest 9.0.3 无 RECORD 文件 |
| GitHub 同步 | ⏸ 未到达 | CI 失败阻塞合并 |

**结论**：链路已打通至 CI，CI 环境问题修复后即可全链路跑通。
