# Changelog

## [Unreleased]

### Added
- Ownership 数据模型 + classify API（ownership.py, 641行）
- Factory PreToolUse P0 写入拦截（pretooluse_guard.py, 620行）
- Source repo readonly context-package（三模式 Runtime 隔离）
- Integrity manifest v2 ownership-aware 签名 + 禁止 auto re-sign
- 子代理 ownership policy 注入
- ownership CLI（show/validate/plan-update/apply-update）
- hook 升级工具（inspect/plan-upgrade/apply-upgrade）
- integrity re-sign CLI（专用重签名 + reason + token）
- memory-init ownership.toml 生成 + --force 限制
- validate/audit/apply ownership-aware 检查
- 242 个新增测试覆盖全部 M1-M6 里程碑

## [0.4.0] - 2026-05-14

### Changed
- Development Status 从 Alpha (3) 升级为 Production/Stable (5)
- Lint ignore 条目从 13 条收敛到仅全局 E501/E402
- 统一 ruff 配置到 ruff.toml，删除 pyproject.toml 重复段
- CLI API 签名全部冻结（11 个入口点）
- .gitignore 补全 .ruff_cache/

### Added
- 7 个新测试文件（246 个测试），覆盖 codex_session_analyzer、daily_session_summary、consistency_check、validate_project_memory、provider_probe、denied_project_roots、neutral_policy
- Python API 参考文档写入 ShowDoc（9 个页面）
- Ownership 数据模型 + classify API（ownership.py, 641行）
- Factory PreToolUse P0 写入拦截（pretooluse_guard.py, 620行）
- Source repo readonly context-package（三模式 Runtime 隔离）
- Integrity manifest v2 ownership-aware 签名 + 禁止 auto re-sign
- 子代理 ownership policy 注入
- ownership CLI（show/validate/plan-update/apply-update）
- hook 升级工具（inspect/plan-upgrade/apply-upgrade）
- integrity re-sign CLI（专用重签名 + reason + token）
- memory-init ownership.toml 生成 + --force 限制
- validate/audit/apply ownership-aware 检查
- 242 个新增测试覆盖全部 M1-M6 里程碑

### Fixed
- 修复新测试文件中的未使用 import 和未使用变量

## [0.3.0] - 2026-05-13

### Added
- **Layout governance CLI**：新增 `memory-init --mode create|adopt|update|repair`、`memory-audit-layout`、`memory-plan-residue`、`memory-apply-residue-plan`，用于安全接入、布局审计、残留计划和低风险计划应用
- **Forbidden overwrite guard**：自动初始化/残留应用禁止覆盖业务入口 `AGENTS.md`、`INDEX.md`、`project-map/**`、`CLAUDE.md`；`adopt` 不向未标记 `AGENTS.md` 追加 hook block
- **Health Report layout_audit**：健康报告包含只读布局审计摘要，布局审计失败或 P0/P1 发现降级为 `degraded` 而非硬失败
- **L2 Integrity Layer**：SHA-256 + HMAC-SHA256 签名和验证，三个模块（keys/manifest/verify）
- **Health Report**：异步健康检查，`session-start` 时后台启动，下次注入检查结果作为 alert
- **Project Lifecycle**：多项目生命周期追踪，project_id 唯一标识，path-index 路径索引，missing 标记
- **Memory Root Discovery**：从 cwd 向上查找 `.memory/` 定位项目根，支持 monorepo sentinel
- **Thread-safe Config**：`get_config(key)` + `_config_lock` 线程安全配置访问
- **Schema `is_lossless()` API**：运行时检测 schema 转换数据丢失，审计日志写入 `schema-audit.log`
- **Adapter TOML Schema 校验**：`adapter_toml_schema.py` 结构化校验，字段类型/必填/枚举约束
- **`memory-init` 新增模板**：NOW.md、inbox.md、policy-pack.json、project-scope.md（runtime required）
- **`memory-init` L2 自动签名**：初始化后自动签名首个 manifest（best-effort）
- **Artifact 日期分区隔离**：按 project_scope 隔离 artifact 输出
- **Pollution detection whitelist** + `--check pollution` CLI（validate_memory_system）
- **CI health check script** + GitHub/GitLab integration（scripts/ci_health_check.sh）
- 新增 `memory_core/constants.py` 常量集中管理（CURRENT_MEMORY_VERSION, SUPPORTED_HOSTS 等）
- 新增 `memory_core/tools/consistency_check.py` 一致性检查工具（18 项检查）
- 新增 `factory` 主机支持（第三类宿主平台）
- 新增 `memory-consistency-check` CLI 入口点

### Changed
- **文档更新**：README.md 改为开源项目首页并补充 layout governance CLI
- **文档更新**：DOT_MEMORY_SPEC.md 补充 NOW.md/inbox.md/manifest.json/policy-pack.json 及布局治理规则
- **文档更新**：MULTI_PROJECT_SCAN_SPEC.md 状态从 ARCHIVED 改为 implemented
- memory.lock 格式从 JSON 迁移到 TOML
- 所有硬编码版本号统一引用 `constants.CURRENT_MEMORY_VERSION`
- 所有硬编码主机列表统一引用 `constants.SUPPORTED_HOSTS`
- init 项目模板全面升级（CANONICAL.md、PLAN.md、STATE.md、TASKS.md 结构化）
- default_runtime_profile 返回键从 21 个扩展到 51 个
- validate_project_memory 新增 3 项检查（state 枚举、SemVer、host 枚举）
- memory_hook_gateway adapter 加载重构为函数化
- migrations.log writes now use fcntl.flock (POSIX, Windows fail-soft)
- adapter.toml migration refactored to structured transformer registry
- workbot DeprecationWarning suppressed during pytest collection (conftest.py)

### Deprecated
- 多个 docs/ 文档标记为 ARCHIVED（DISPATCH_TEMPLATE, FIXTURES_VS_REAL, MIGRATION_* 等）

### Removed
- `CLAUDE_HOOK_STATE_DIR` dead code
- `# TODO: remove if unused` annotation on `CoreConfig.from_gateway_kwargs`

### Archived
- `memory_core/tools/ANALYSIS_GATEWAY_ADAPTER.md` → `archive/legacy-analysis/`

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
