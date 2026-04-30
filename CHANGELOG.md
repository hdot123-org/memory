# Changelog

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
