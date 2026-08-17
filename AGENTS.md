# memory-core 项目指南

## 定位
memory-core 是只读协议仓库，提供 .memory/ 协议、模板、Schema、CLI 工具。
它是一个可复用的库，不存储任何业务项目状态。

## 核心设计
- **存储（memory-core）+ 按需加载（DCE/Factory 平台）互补闭环**
- context-package 在 session-start/prompt-submit 时动态构建，提供完整路由
- 每个消费项目通过 memory-init 初始化独立记忆，互不依赖
- INDEX.md 由 memory-init 自动生成，context-package 动态解析，不需要手动维护

## 本仓库身份
- source-repo-readonly，所有写入被 hook 拦截
- 不需要 AGENTS.md 自动生成、索引自动化、上下文验证等优化
- 设计文档在 docs/specs/ 和 docs/architecture/
- 边界定义在 docs/specs/BOUNDARY.md

## Agent 行为准则
- 只探索不修改
- 不要建议改进本项目结构，闭环已经完整
- 消费项目问题参考 README.md 和 BOUNDARY.md

## 路由规则

路由规则仅由以下文件定义，AGENTS.md 只做方向性引用，不嵌入任何路由逻辑。

**读取链**：Agent 启动 → AGENTS.md (行为约束) → 三层架构路由 → Layer 3 项目层优先 → Layer 2 全局 fallback

| 层 | 职责 | 路径 |
|----|------|------|
| 全局知识库 (Layer 2) | 跨项目通用知识、全局 fallback | `~/.memory/global-kb/` |
| 项目知识库 (Layer 3) | 项目专属知识 | `<project>/memory/kb/` |

具体路由规则（如 scope resolution、fallback）请查阅上述路径下的 INDEX.md。

## 执行前置规则（模板示例）

> 以下规则是消费项目应遵循的执行前置模板。memory-core 本身只读，不适用。

**任何涉及知识库的读取或写入操作前，必须先读取 `~/.factory/AGENTS.md` 确认术语到路径的映射。不可凭记忆或上下文推断路径。**

| 操作场景 | 前置要求 |
|----------|---------|
| 写入 `memory/kb/`、`docs/`、`~/.memory/global-kb/` | 先查路由表确认目标层和正确路径 |
| 读取项目知识库 | 先确认 Layer 3 → Layer 2 fallback 顺序 |
| 用户说"记下来"/"写文档"/"记录决策" | 先读项目 AGENTS.md 确认分类规则，再执行写入 |

## 文档分类规则

当用户说"文档记录"、"记一下"、"写个文档"时，**必须先查阅 `docs/CLASSIFICATION.md` 分类决策树**。

快速参考：

| 关键词 | 目标路径 |
|--------|---------|
| 服务器/IP/端口/部署/Docker | `docs/infrastructure/` |
| 运维/故障/排查/runbook | `memory/docs/runbooks/` |
| 设计/架构/API 契约 | `docs/architecture/` 或 `docs/specs/` |
| 决策/选型/为什么/对比 | `memory/kb/decisions/` |
| 踩坑/教训/经验 | `memory/kb/lessons/` |
| 计划/里程碑/排期 | `memory/docs/plans/` |
| Droid/配置/模型/指南 | `docs/guides/` |
| Bug/崩溃/报错 | `memory/docs/bug-reports/` |
| 不确定 | `memory/docs/drafts/` |

完整决策树见 `docs/CLASSIFICATION.md`。

## 铁律：GitHub 直接推送

**所有代码变更直接推送到 GitHub，使用标准 git 命令。**

核心要点：
- 使用 `git add` / `git commit` / `git push origin <branch>`
- **所有 commit 消息必须使用中文**（如 `fix: 修复 discover_project_root 根目录解析错误`）
- **禁止直接推送 main** — main 分支受保护，必须走 feature 分支 + PR
- **PR 是默认流程** — 推送 feature 分支后创建 PR，合并后自动删除源分支

## mission 异步合并纪律（2026-08-17）

**创建 PR 并执行 `write-pending-ci.sh <PR_NUMBER>` 后，mission 会话不得阻塞等待 CI/droid-review 完成。** 合并由 auto-merge workflow（workflow_run + schedule 双触发，DISPATCH_TOKEN）在全部 check 转绿后自动 squash 完成，会话在关键路径之外。

| 步骤 | 动作 |
|------|------|
| 1. 创建 PR 后 | 执行 `scripts/write-pending-ci.sh <PR_NUMBER>` 注册 CI 完成路由 |
| 2. 立即 | 切换下一任务（worktree / 新分支），不等注入消息 |
| 3. 收到注入消息（"CI 全绿"/"状态更新"） | 按 ci-gateway skill 处理：PR 已合并则直接执行合并后三件事；CI 失败则回到该 PR 修复 |

- CI 失败时 auto-merge 自动保持待命，修复 push 后重跑，无需人工干预合并
- 禁止在会话内 `gh pr merge --watch` 或轮询等待 checks；门禁由 branch protection + ci-ok（含 droid-review）+ auto-merge 三层保证，会话无需在场

## 铁律：GitHub 为主仓库

**GitHub 已成为主仓库，所有开发流程迁移到 GitHub。**

1. **代码推送到 GitHub** — Agent/人/CI 都直接 push 到 GitHub
2. **CI 门禁** — GitHub Actions 的 test + health-check 通过后才可合并到 main
3. **PR 流程** — 推送 feature 分支后创建 PR，通过 code review 后合并
4. **GitLab 保留** — GitLab remote 保留用于历史备份，但不再作为主开发流程

## 铁律：合并纪律（droid-review 门禁）

**禁止 `gh pr merge --admin`。任何 check 失败都不允许绕过合并，必须修复或等待恢复后重新触发。**

决策流程：
1. 运行 `gh pr checks <PR#>` 查看所有 check 状态
2. 如果 droid-review 失败，分析失败原因：
   - **模型/API 故障**（如 "model unavailable"、"API timeout"、"rate limit"）→ 等待恢复后重新触发，不可绕过
   - **代码审查发现**（P1/P2 bug、security issue、correctness problem）→ 必须修复后重新提交
   - **P3 发现**（typo、style、minor improvement）→ 如果快速修复则修复，否则作为 follow-up 跟踪
3. CI 持续失败时，回滚或修复根因，不要绕过

**ci-ok 门禁已包含 droid-review**：ci.yml 的 ci-ok job 会查询 droid-review check 状态。当 droid-review 失败时，ci-ok 也会失败，阻止标准合并。

**enforce_admins: true**：分支保护已启用管理员强制执行，`--admin` 旁路已被 GitHub 层面堵死。

## 铁律：CI 完成后 Webhook 路由

**创建 PR 后必须调用 webhook 写入脚本，确保 CI 完成后 webhook 能路由回当前 session。**

**全局脚本位置**：`~/.factory/webhook/scripts/write-pending-ci.sh`

**本项目 wrapper**：`scripts/write-pending-ci.sh`（调用全局脚本，保持向后兼容）

流程：创建 PR → 执行 `scripts/write-pending-ci.sh <PR_NUMBER>`（或 `~/.factory/webhook/scripts/write-pending-ci.sh <PR_NUMBER>`）→ CI 完成后 n8n webhook 触发 trigger-ci-droid.sh → 读取 pending-ci.json → 注入当前 session。

**全局脚本特性**：
- PROJECT_CWD 运行时检测（`git rev-parse --show-toplevel`），不硬编码
- PYTHON_BIN 动态查找（`${PYTHON_BIN:-$(command -v python3)}`）
- 需要 git repo 环境，除非提供显式 SESSION_ID

## 铁律：文档类别同步

**创建新文档类别时必须同步更新 `DOC_CATEGORIES`（`memory_core/tools/doc_router.py`）和 `docs/CLASSIFICATION.md`。**

路由表代码是 single source of truth。任何新分类标签必须：
1. 在 `memory_core/tools/doc_router.py` 的 `DOC_CATEGORIES` 字典中添加条目
2. 在 `docs/CLASSIFICATION.md` 的决策树和快速分类表中同步添加
3. 更新 `scripts/check_doc_classification.py` 的例外列表（如需要）

不同步视为违规，CI 会拦截。

## 铁律：版本发版纪律

**版本发版使用 release-please 自动化，禁止手动打 tag。**

1. **Commit 规范** — 使用 conventional commits（`feat:`/`fix:`/`chore:`），release-please 据此自动决定版本号
2. **禁止手动 tag** — 发版通过合并 release-please 的 Release PR 完成，不手动 `git tag`
3. **手动发版** — 仅在 release-please 故障时使用 `workflow_dispatch` 触发 `release-and-dispatch.yml`
4. **回滚** — 使用 `scripts/release_rollback.sh`，不要手动删 tag
5. **发版指南** — 详见 `docs/guides/release-guide.md`

## 铁律：版本号由 release-please 管理

**版本号由 release-please 自动管理，禁止手动修改。**

核心要点：
- 不要手动修改 `pyproject.toml`、`memory_core/constants.py`、`.release-please-manifest.json` 中的版本号
- 不要手动编辑 `CHANGELOG.md` 的版本条目（release-please 自动生成）
- 使用 Conventional Commits 格式（`feat:`, `fix:` 等）触发版本变更
- 合并 Release PR 时，release-please 自动完成版本号更新 + CHANGELOG + tag + GitHub Release

## 自动化：分支清理（Branch Cleanup）

**`.github/workflows/branch-cleanup.yml` 每日自动删除孤立分支。**

- **触发时间**：每天 UTC 06:00（`cron: '0 6 * * *'`）+ 手动 `workflow_dispatch`
- **逻辑**：列出除 `main` 外的所有远程分支 → 用 `gh pr list --head <branch>` 检查是否有 open PR → 无 PR 且最后 commit 超过 24 小时的分支被自动删除
- **通知**：如有分支被删除，自动创建 Issue 列出被删分支清单
- **认证**：checkout 使用默认 `GITHUB_TOKEN`（只读），删除分支和创建 Issue 使用 `DISPATCH_TOKEN` secret（写入权限）
- **无需手动干预**：无需人工/agent 主动清理，CI 自动完成分支卫生

## Linear Gateway

当 session tag 包含 `linear-gateway` 或用户要求处理 Linear issue 时，使用 `linear-gateway` skill。

**关键约束：**
- Linear API Key 在 1Password vault `sever` 条目 `REDACTED_VAULT_ID`，或环境变量 `LINEAR_API_KEY`
- 不要依赖外部传入的 issue 内容，必须自行通过 Linear API 拉完整上下文
- 仓库与目录路由规则在 `~/.factory/config/repositories.yml`
- 执行完成后直接调用 Linear API 回写 comment
- 不直接把 issue 改为 `Done`，状态流转交给 GitHub ↔ Linear 自动化（Linear 原生 GitHub 集成，ID: 7ee5340b）
- 完整规范见 `docs/architecture/API-CONTRACT.md`

## Issue 流转约定

### 核心原则

**Linear 是唯一任务管理面板，GitHub Issue 是 scanner 自动产物。**

- **Linear 职责**：需求管理、缺陷跟踪、优先级分配、负责人指定、状态管理
- **GitHub 职责**：scanner 入口、代码托管、PR 流程、Code Review、CI/CD
- **GitHub Issue 定位**：evolution scanner 自动创建的记录，不是人工任务管理的主要入口

### 职责边界

| 维度 | GitHub | Linear |
|------|--------|--------|
| 角色定位 | scanner 入口、代码实现、PR、review、CI | 唯一任务管理面板 |
| Issue 定位 | scanner 自动产物和同步源，不作为主要人工管理面 | 唯一人工任务管理面 |
| 操作方式 | 全自动（scanner + CI + merge） | 人 + agent |
| 管理内容 | 不需要人管 | 需求、缺陷、优先级、负责人、状态、项目进度 |

### 当前闭环机制

PR body 中使用 `Fixes INFRA-xxx` 引用即可实现自动闭环，两条独立路径：

1. **Linear Issue**：Linear GitHub 集成检测到 PR merge（通过 `Fixes INFRA-xxx` 引用），自动流转为 Done
2. **GitHub Issue**：scanner 下次运行时 `auto_close_resolved()` 检测到 finding 已解决，自动关闭
3. 无需额外代码改动或手动操作

**此机制已验证有效。**

### 铁律：派发会话关单规矩

**自动派发的会话禁止直接关闭 GitHub issue，必须走 PR + Fixes 引用闭环。**

2026-08-14 风暴期教训：INFRA-292 自动派发会话以 hdot123 OAuth 身份用 scanner 模板文案反复直接关单，导致 #648 经历 14+ 轮 close/reopen 振荡（51 events、26 comments）。

**正确做法**：
- GitHub issue 只能经以下方式关闭：
  1. PR merge + `Fixes INFRA-xxx` 引用（自动闭环）
  2. scanner 合法 `auto_close_resolved()`（经完整信任链：P0-A 骤降防护 + P0-1 linkback fail-closed）
- 派发会话（包括 droid session、webhook 触发器等）不得直接调用 `gh issue close` 或等效操作

### 完整文档

详细的流转链路、职责约定和故障排查指南，请参考：[`docs/architecture/issue-flow.md`](docs/architecture/issue-flow.md)

