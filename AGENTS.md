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
- 设计文档在 memory_core/memory/docs/system/ 和 memory_core/memory/docs/design/
- 边界定义在 memory_core/memory/docs/system/BOUNDARY.md

## Agent 行为准则
- 只探索不修改
- 不要建议改进本项目结构，闭环已经完整
- 消费项目问题参考 README.md 和 BOUNDARY.md

## 铁律：GitLab → GitHub 单向同步

**所有 Factory/Droid 接入的项目必须遵守：**

1. **代码只推 GitLab** — Agent/人/CI 都只 push 到 GitLab，创建 MR
2. **CI 门禁** — test + health-check 通过后才可合并到 main
3. **GitHub 是只读镜像** — 只有 GitLab CI 的 sync-to-github job 可以推 GitHub
4. **禁止直推 GitHub** — 任何 `git push origin main` 都是违规，会破坏单源真相
5. **违规恢复** — 如果意外直推 GitHub，回退 GitHub commit，重新走 GitLab 流程

