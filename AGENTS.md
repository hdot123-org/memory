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
- 设计文档在 docs/ 和 memory_core/memory/docs/design/
- 边界定义在 docs/BOUNDARY.md

## Agent 行为准则
- 只探索不修改
- 不要建议改进本项目结构，闭环已经完整
- 消费项目问题参考 README.md 和 BOUNDARY.md
