# Changelog

## [0.9.0] - 2026-07-14

### Added
- **仓库交付一致性健康检查脚本** (`scripts/repo_health_check.sh`): 检查仓库交付质量，纳入 CI 门禁
- **集成测试纳入 CI**: 全量集成测试作为 CI 步骤运行
- **双门禁验证**: ci-ok + droid-review 双门禁流程完善
- **单元测试补充**: daily_summary_generator 覆盖率 20%→89%, daily_kb_audit 覆盖率 18%→75%
- **truth-basis 验证逻辑测试**: 完整性验证覆盖
- **advisory 纳入 ci-ok 门禁**: dependency security scan + telemetry coverage audit 作为非阻塞 advisory job

### Changed
- **health check --full 模式修复 tag 发现逻辑**: 修复版本 tag 发现问题
- **遥测准确性修复**: degraded 状态 + duration_ms + observability 桥接
- **duration_ms 测试重构**: 使用 monkeypatch 替代 patch.object，增加 fallback 验证
- **CI 测试隔离修复**: ArtifactWriter mock + stat 错误路径重构 + yaml mock 修复

### Removed
- **移除 GitLab 同步功能**: 对齐文档至 GitHub PR 流程
- **移除 PyPI 发布步骤**: release workflow 简化
- **移除 pretooluse_guard 中 gitlab_api_push.py 死代码**: 脚本已删除
- **移除 CONTRIBUTING.md Release 段 GitLab 残留**: 文档对齐 GitHub 流程

### Fixed
- **release workflow 添加 pytest-cov 安装**: 修复 --cov 参数缺失致 release 失败
- **@droid 两路 model 修复**: droid_args + review_model 覆盖 exec pass + validator pass
- **@droid 交互式 exec 模型传参**: 改用 droid_args 传模型，修复 gpt-5.2 回退被封问题

### Docs
- **更新 README 版本号到 v0.9.0**: 移除 PyPI 和 GitLab MR 残留
- **SOP 改用 --auto 自动合并**: 合并方式仅 squash
- **同步 advisory 纳入门禁到流程规范**
- **重写为 GitHub PR 流程标准规范**: 完整 SOP + 架构 + 配置 + 纪律
- **云端模型锁定为 grok-4.5**: droid + droid-review
- **PR 流程改造**: CI 全量跑 + ci-ok 门禁 + droid 自动审查

## [0.8.0] - 2026-06-20

### Added
- 全局知识库层 (~/.memory/global-kb/): operations/engineering/collaboration/pending 四域
- 分层路由 fallback: adapter.toml [global_kb] 段, 项目优先 → 全局 fallback
- memory-init 自动创建全局 KB 并写入配置
- memory-migrate 0.7→0.8 迁移支持
- memory-promote CLI: 从 pending 提升到正式分类
- session-end 自动捕获候选到 pending/

### Fixed
- ssh-tailscale-pitfalls.md BOUNDARY IP 泄漏脱敏

### Docs
- 新增通用维护手册: VERSION_SYNC_RUNBOOK / MIGRATION_RUNBOOK / CONFIG_MANAGEMENT_RUNBOOK
- 现有 CI/CD 手册加环境特定声明标注
- runbooks/INDEX.md 分为通用维护手册 + 环境特定手册两类

# Changelog

## [0.7.0] - 2026-06-07

### 新增
- **完整性签名 `include_runtime` 参数**（VAL-P3-001~007）：`sign_project` / `sign_project_incremental` 新增 keyword-only `include_runtime: bool = False` 参数，默认不签名运行时产物（`memory/artifacts/memory-hook/`），保持 manifest 稳定
- **resign CLI `--include-runtime` 标志**：透传 `include_runtime` 到签名函数
- **审计前缀精确匹配**（VAL-P3-008~009）：`_check_manifest_includes_runtime` 从子串匹配改为前缀匹配，消除对 `memory/system/adapter.toml`、`memory/kb/global/memory-system.md`、`memory/log/*-sessions.md` 的误报
- **初始化模板补全**（VAL-P1-001~010）：
  - `legal-core-map.md` 补齐 4 个 `legal_core_markers`
  - `ingestion-registry-map.md` 补齐 8 个 `required_registry_scopes`
  - 新增 `memory/docs/记忆系统全景文档.md` 模板（含 `project-map/INDEX.md` 引用）
  - 5 个 global-canonical 文件各加 `## Truth Basis` 段（Source/Authority/Evidence/Conflict），通过 `TruthBasisResolver` 校验
  - 新增 `tests/.memory-anchor.md` 锚点文件
- **初始化行为修复**（VAL-P2-001~008）：
  - `update_agents_md` repair 模式：文件不存在时也创建
  - `_apply_auto_fill` 增强：从 `package.json` / `tsconfig.json` / `pyproject.toml` 抽取技术栈，填充占位符；未知占位符替换为 `（待补充：xxx）`
  - init 成功后调用 `audit_project_layout` 做只读体检，P1 项作为 `result["warnings"]` 输出
- **跨 phase 端到端 golden 测试**（VAL-CROSS-001~006）：
  - init → audit → sign 全链路验证
  - init update 幂等性
  - 存量项目迁移路径（旧 codex host 残留 → update → 干净）
  - audit 不报 init 产物误判
  - 单一 factory wrapper 验证
  - version bump 记录

### 变更
- **收紧 `SUPPORTED_HOSTS` 为 `("factory",)`**（VAL-P0-006）：废弃 codex 和 claude host
- **`template_adapter_toml` 固定写入 `host = "factory"`**（VAL-P0-003）：不再从 `--host` 参数插值
- **`template_agents_md_block` 改写为 host 无关 prose**（VAL-P0-002）：不嵌入 `~/.codex/` / `~/.claude/` 路径
- **`--host` argparse 入口收紧**（VAL-P0-005/007）：init 和 gateway 仅接受 `"factory"`
- **`CURRENT_MEMORY_VERSION` 升级到 `0.7.0`**

### 删除
- **`codex_global_hooks.py` / `claude_global_hooks.py`**（VAL-P4-001/002）
- **`tests/test_codex_global_hooks.py` / `tests/test_claude_global_hooks.py`**（VAL-P4-003）
- **`pyproject.toml` 中 `memory-codex-hooks` / `memory-claude-hooks` entry points**（VAL-P4-004）
- **所有 `if host == "codex"` / `elif host == "claude"` 分支**（VAL-P4-005/006）
- **`ownership.py` 中 `codex_global_hooks.py` source-repo 标记引用**（VAL-P4-007）
- **`factory_global_hooks.py` 中 codex/claude 存在性检测探针**（VAL-P4-008）
- **`hook_upgrade.py` 中 codex/claude 导入**（VAL-P4-009）

### 修复
- **init 不再生成 `hooks.json`**（VAL-P0-001）：移除 `generate_hooks_json` 调用
- **update 模式自动清理存量项目旧 host 痕迹**（VAL-P4-010/011）：
  - AGENTS.md 中 `~/.codex/bin/memory-hook` / `~/.claude/bin/memory-hook` 引用被清除
  - `.codex/hooks.json` / `.claude/hooks.json` 残留文件被删除
- **README.md / droid-wiki 文档删除 `--host codex|claude` 引用**（VAL-P4-012/013）

## [0.6.0] - 2026-06-01

### Added
- **docs/ 展示层（AutoWiki 可索引）**：新增 `docs/` 目录结构，作为 AutoWiki 扫描入口
  - `docs/INDEX.md`：全局知识文档索引
  - `docs/CLASSIFICATION.md`：文档分类决策树
  - `docs/infrastructure/servers.md`：服务器资产清单
  - `docs/infrastructure/1password-mcp.md`：1Password Connect MCP 架构
  - `docs/guides/droid-computers.md`：Droid Computer 管理指南
  - `docs/guides/byok-models.md`：自定义模型配置指南
- **AGENTS.md 文档分类规则段**：新增快速分类表，引导 Droid 写入文档时参照 `docs/CLASSIFICATION.md`
- **.gitlab-ci.yml wiki stage**：新增 `droid-wiki-refresh` job，main 分支 push 后自动触发 AutoWiki 刷新
- **Error logger 模块**（error_logger.py）：结构化错误日志，集成到 A 层 hook gateway
- **Session end logger**（session_end_logger.py）：会话结束日志记录
- **Daily summary generator**（daily_summary_generator.py）：每日摘要生成器
- **Cross-integrity integration 测试**（test_cross_integrity_integration.py）：完整性集成测试
- **Ownership 模型增强**（ownership.py）：新增路径分类 API
- **Hook gateway 增强**（memory_hook_gateway.py）：错误日志集成、增量签名机制
- **Template sync 增强**（template_sync.py）：模板同步功能增强
- **Init project memory 增强**（init_project_memory.py）：初始化流程优化

### Changed
- `memory_core/constants.py`：版本升级到 0.6.0
- `pyproject.toml`：版本升级到 0.6.0

### Removed
- `daily_session_summary.py`：功能拆分到 daily_summary_generator.py
- `sync_to_showdoc.py`：移除 ShowDoc 同步功能
- `adapter_toml_schema.py`：精简 schema 校验逻辑
- `CONTRIBUTING.md`：移除过时内容
- `audit/SUMMARY.md`：移除过时审计摘要

## [0.5.0] - 2026-05-23

### Breaking Changes
- **Two-layer architecture**: Project-level configuration moved from hidden `.memory/` to `memory/system/`. Global runtime `~/.memory-core/` remains unchanged.
- **Removed `.memory/` directory**: The hidden project protocol directory is eliminated. All config and state files now live under `memory/system/`.
- **Deleted 5 AI template files**: `CANONICAL.md`, `STATE.md`, `PLAN.md`, `TASKS.md`, `NOW.md` are no longer created or validated. These were redundant with project README/CLAUDE.md and linear/project tools.

### Added
- **`SYSTEM_DIR` constant**: New `SYSTEM_DIR = "memory/system"` in `constants.py`
- **`memory/system/kb/` and `memory/system/skills/`**: Migrated from `.memory/kb/` and `.memory/skills/`
- **`0.4.0 → 0.5.0` migration step**: `migrate_project_memory.py` supports migrating existing projects, with backup at `memory/system/backups/pre-0.5/` and rollback support
- **Idempotent migration**: Re-running `memory-migrate --from 0.4.0 --to 0.5.0` on an already-migrated project is a no-op
- **`INDEX.md` auto-generation**: `memory-init` now auto-generates INDEX.md; context-package dynamically parses, no manual maintenance needed

### Changed
- `constants.py`: Removed CANONICAL/STATE/PLAN/TASKS/NOW constants, removed FRONTMATTER_REQUIREMENTS, removed STATUS_ENUMERATIONS
- `init_project_memory.py`: All `target / ".memory"` → `target / "memory" / "system"`, removed 5 template file generators
- `memory_root_discovery.py`: Hard cutover — marker changed from `.memory` to `memory/system`, no dual detection
- `validate_project_memory.py`: Path migration, removed validation of deleted template files
- `ownership.py` + `ownership_cli.py`: Updated path declarations from `.memory/*` to `memory/system/*`
- `memory_hook_gateway.py` + `memory_hook_impls.py` + `memory_hook_integrity_manifest.py`: Path migration
- `*_global_hooks.py` × 3 (codex, claude, factory): Path migration
- 12+ other tool files: Path migration
- `workspace/templates/.memory/` → `workspace/templates/memory/system/`
- Version bumped to `0.5.0` in `constants.py` and `pyproject.toml`

### Migration Path
- New projects: `memory-init` creates `memory/system/` directly
- Existing v0.4.x projects: `memory-migrate --from 0.4.0 --to 0.5.0` with automatic backup
- Rollback: `memory-migrate --rollback` restores from backup

## [0.4.0] - 2026-05-18

### Added
- **Ownership 数据模型 + classify API**（ownership.py, 641行）：ProtectionLevel/OwnershipKind 枚举、classify_owned_path() 统一分类 API、DEFAULT_OWNERSHIP_DOMAINS 默认三域
- **Factory PreToolUse P0 写入拦截**（pretooluse_guard.py, 620行）：Write/Edit/MultiEdit/Execute/Task 六种工具拦截，Execute 命令静态解析
- **Source repo readonly context-package**（三模式 Runtime 隔离）：consumer-project / source-repo-readonly / noop 三模式，git status 和 mtime 不变
- **Integrity manifest v2 ownership-aware 签名**：签名范围从固定 canonical 改为 ownership-derived，禁止 auto re-sign
- **integrity re-sign CLI**（memory_integrity_resign.py）：专用重签名，需 reason + token/force，写 audit trail
- **子代理 ownership policy 注入**：Task 子代理自动注入 policy block + cwd 固定为 project_root
- **ownership CLI**（ownership_cli.py）：show/validate/plan-update/apply-update 四命令
- **hook 升级工具**（hook_upgrade.py）：inspect/plan-upgrade/apply-upgrade 三命令
- **memory-init ownership.toml 生成**：create/adopt/update/repair 四模式自动生成，--force 不得绕过 Ownership
- **validate/audit/apply ownership-aware 检查**：4 类检查（declaration/domain_integrity/document_paths/shared_resources）
- **兼容矩阵**（compat.py）：memory-core / ownership schema / hook schema / manifest version 兼容性检查
- **242 个新增测试**覆盖全部 M1-M6 里程碑，全量 1612 测试通过

### Changed
- Development Status 从 Beta (4) 升级为 Production/Stable (5)
- 6 个 ARCHIVED 文档归档到 docs/archive/（DISPATCH_TEMPLATE, FIXTURES_VS_REAL, MIGRATION_*）
- Lint ignore 条目从 13 条收敛到仅全局 E501/E402
- 统一 ruff 配置到 ruff.toml，删除 pyproject.toml 重复段
- CLI API 签名全部冻结（11 个入口点）
- .gitignore 补全 .ruff_cache/

### Fixed
- 修复新测试文件中的未使用 import 和未使用变量
- 修复 prompt_validator.py 和 resilient_orchestrator.py 空白行空白符问题

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
