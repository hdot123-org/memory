# Project Truth — memory_core

> memory-core 是只读协议仓库，提供 .memory/ 协议、模板、Schema、CLI 工具。
> 它是一个可复用的库，不存储任何业务项目状态。

## Project Scope

- **scope**: memory_core
- **description**: 只读协议仓库，提供记忆系统协议、模板和 CLI 工具
- **status**: active

## Truth Basis

### Source Refs

- memory/docs/记忆系统全景文档.md

### Authority Refs

- project-map/INDEX.md
- project-map/legal-core-map.md

### Evidence Refs

- tests/conftest.py

### Conflict Status

- resolved

## Project Context

memory-core 定义 .memory/ 协议规范，包含：
- 知识库结构模板（kb/global、kb/projects、kb/decisions、kb/lessons）
- 验证器工具链（TruthBasisResolver、evidence_ref_validator 等）
- Hook 网关（session-start、prompt-submit 生命周期事件）
- adapter.toml 配置解析与 scope 路由

消费项目通过 memory-init 初始化独立记忆，互不依赖。

## Version History

- v1.0 — 初始项目规范文件，修复 TruthBasisResolver 硬失败
