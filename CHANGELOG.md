# Changelog

## [0.3.0] - Unreleased

### Added
- 新增 `memory_core/constants.py` 常量集中管理（CURRENT_MEMORY_VERSION, SUPPORTED_HOSTS 等）
- 新增 `memory_core/tools/consistency_check.py` 一致性检查工具（18 项检查）
- 新增 `factory` 主机支持（第三类宿主平台）
- 新增 `memory-consistency-check` CLI 入口点

### Changed
- memory.lock 格式从 JSON 迁移到 TOML
- 所有硬编码版本号统一引用 `constants.CURRENT_MEMORY_VERSION`
- 所有硬编码主机列表统一引用 `constants.SUPPORTED_HOSTS`
- init 项目模板全面升级（CANONICAL.md、PLAN.md、STATE.md、TASKS.md 结构化）
- default_runtime_profile 返回键从 21 个扩展到 51 个
- validate_project_memory 新增 3 项检查（state 枚举、SemVer、host 枚举）
- memory_hook_gateway adapter 加载重构为函数化

### Deprecated
- 多个 docs/ 文档标记为 ARCHIVED（DISPATCH_TEMPLATE, FIXTURES_VS_REAL, MIGRATION_* 等）

## [0.2.0] - 2026-04-30

### Changed
- 统一版本来源到 pyproject.toml，CLI 支持 --version
- 补齐 .gitignore，清理已追踪污染路径
- 新增 MIT LICENSE 与完整项目元数据

### Note
- 458 测试通过基线

## [0.1.0] - 2026-04-XX

### Added
- memory-init / memory-validate / memory-migrate 三大核心 CLI
- .memory/ 目录结构与版本管理能力
- adapter.toml 协议与 runtime profile 机制
- HookEvent 归一化（Codex / Claude dual-host）
- Schema 转换链（wb-hook-v2 → context-package-v1 → memory-v1）
- 污染防护（pollution guard）
- NoopHostDelegate 与 delegate resolution
- Root discovery 模块
- 项目知识目录模板（kb/）
