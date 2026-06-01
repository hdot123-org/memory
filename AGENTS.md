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
- 设计文档在 memory/docs/system/ 和 memory/docs/design/
- 边界定义在 memory/docs/system/BOUNDARY.md

## Agent 行为准则
- 只探索不修改
- 不要建议改进本项目结构，闭环已经完整
- 消费项目问题参考 README.md 和 BOUNDARY.md

## 路由规则

路由规则仅由以下文件定义，AGENTS.md 只做方向性引用，不嵌入任何路由逻辑。

**读取链**：Agent 启动 → AGENTS.md (行为约束) → 指向性引用 → memory-routing.md (路由规则) → project-map (合法入口) → memory/kb (实际知识)。

| 文件 | 职责 | 路径 |
|------|------|------|
| memory-routing.md | 记忆请求路由、作用域解析、降级策略 | `memory/kb/global/memory-routing.md` |
| project-map/INDEX.md | 项目地图唯一合法入口、合法性校验 | `project-map/INDEX.md` |
| BOUNDARY.md | 仓库边界定义、职责范围、不属于本仓库的内容 | `memory/docs/system/BOUNDARY.md` |

具体路由规则（如 scope resolution、fallback）请查阅上述文件，不要在此文件中寻找。

## 文档分类规则

当用户说"文档记录"、"记一下"、"写个文档"时，**必须先查阅 `docs/CLASSIFICATION.md` 分类决策树**。

快速参考：

| 关键词 | 目标路径 |
|--------|---------|
| 服务器/IP/端口/部署/Docker | `docs/infrastructure/` |
| 运维/故障/排查/runbook | `memory/docs/runbooks/` |
| 设计/架构/API 契约 | `memory/docs/design/` |
| 决策/选型/为什么/对比 | `memory/kb/decisions/` |
| 踩坑/教训/经验 | `memory/kb/lessons/` |
| 计划/里程碑/排期 | `memory/docs/plans/` |
| Droid/配置/模型/指南 | `docs/guides/` |
| Bug/崩溃/报错 | `memory/docs/bug-reports/` |
| 不确定 | `memory/docs/drafts/` |

完整决策树见 `docs/CLASSIFICATION.md`。

## 铁律：GitLab API 推送

**所有代码变更必须通过 `scripts/gitlab_api_push.py` 推送，禁止使用手动 git 命令。**

详细使用方法见 `memory/docs/runbooks/GIT_PUSH_SPEC.md`。

核心要点：
- 禁止 `git add` / `git commit` / `git push`（被 hooks 拦截）
- Token 优先级：`GITLAB_ADMIN_TOKEN` > `CE_GITLAB_TOKEN` > remote URL 提取
- 项目路径：`infra/memory-core`（需 admin token）、`aedu/workbot`
- **所有 commit 消息、MR 标题/描述必须使用中文**（如 `fix: 修复 discover_project_root 根目录解析错误`）
- **禁止直接推送 main** — main 分支已设为 "No one can push"，必须走 feature 分支 + MR
- **MR 是默认流程** — 推送文件后脚本自动创建 MR，合并后自动删除源分支
- 仅 WIP 场景可使用 `--no-mr` 跳过 MR 创建

## 铁律：GitLab → GitHub 单向同步

**所有 Factory/Droid 接入的项目必须遵守：**

1. **代码只推 GitLab** — Agent/人/CI 都只 push 到 GitLab，创建 MR
2. **CI 门禁** — test + health-check 通过后才可合并到 main
3. **GitHub 是只读镜像** — 只有 GitLab CI 的 sync-to-github job 可以推 GitHub
4. **禁止直推 GitHub** — 任何 `git push origin main` 都是违规，会破坏单源真相
5. **违规恢复** — 如果意外直推 GitHub，回退 GitHub commit，重新走 GitLab 流程

## Linear Gateway

当 session tag 包含 `linear-gateway` 或用户要求处理 Linear issue 时，使用 `linear-gateway` skill。

**关键约束：**
- Linear API Key 在 1Password vault `sever` 条目 `REDACTED_VAULT_ID`，或环境变量 `LINEAR_API_KEY`
- 不要依赖外部传入的 issue 内容，必须自行通过 Linear API 拉完整上下文
- 仓库与目录路由规则在 `~/.factory/config/repositories.yml`
- 执行完成后直接调用 Linear API 回写 comment
- 不直接把 issue 改为 `Done`，状态流转交给 GitLab ↔ Linear 自动化
- 完整规范见 `memory/docs/design/linear-factory-integration.md`

