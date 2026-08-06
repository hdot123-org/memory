# Changelog

## [0.15.3](https://github.com/hdot123/memory/compare/v0.15.2...v0.15.3) (2026-08-06)


### Bug Fixes

* 创建 memory_core.md 项目规范并修复 INDEX.md 幻影条目 ([#315](https://github.com/hdot123/memory/issues/315)) ([231cdc6](https://github.com/hdot123/memory/commit/231cdc6449926f3128046bdc17c2fb21439a7d40))

## [0.15.2](https://github.com/hdot123/memory/compare/v0.15.1...v0.15.2) (2026-08-06)


### Documentation

* 修正文档索引引用并清理 lesson 失效 refs (INFRA-69) ([4a97828](https://github.com/hdot123/memory/commit/4a978282f19af9f5fd8fe3b779be8b120111d12b))

## [0.15.1](https://github.com/hdot123/memory/compare/v0.15.0...v0.15.1) (2026-08-06)


### Bug Fixes

* 补全基础层缺失的 project-map/global canonical 文件及 CI 守卫适配 ([#310](https://github.com/hdot123/memory/issues/310)) ([76c2e28](https://github.com/hdot123/memory/commit/76c2e28fab0f415e1fe53ae4562fbbeda402b500))

## [0.15.0](https://github.com/hdot123/memory/compare/v0.14.0...v0.15.0) (2026-08-05)


### Features

* stub添加定时扫描+workflow_dispatch兜底重试机制 ([9afa8c2](https://github.com/hdot123/memory/commit/9afa8c22b5fe212b86c8a934216ffdff17a314fe))


### Bug Fixes

* pull_request改为pull_request_target，修复bot触发被action_required拦截 ([79b3bc5](https://github.com/hdot123/memory/commit/79b3bc5df18be4ddf7970a1fd8136f785925570a))

## [0.14.0](https://github.com/hdot123/memory/compare/v0.13.4...v0.14.0) (2026-08-05)


### Features

* 添加 dependabot 配置，启用 auto-merge 自动合并 ([#305](https://github.com/hdot123/memory/issues/305)) ([128d14c](https://github.com/hdot123/memory/commit/128d14cdf25c9fa9ecf9a2b2f50ff9adc67399ad))

## [0.13.4](https://github.com/hdot123/memory/compare/v0.13.3...v0.13.4) (2026-08-05)


### Bug Fixes

* 创建 auto-merge workflow，接入 shared-workflows 引擎 ([#306](https://github.com/hdot123/memory/issues/306)) ([3a501e7](https://github.com/hdot123/memory/commit/3a501e788ef83e445c5c33a48961989a0d667586))

## [0.13.3](https://github.com/hdot123/memory/compare/v0.13.2...v0.13.3) (2026-08-05)


### Bug Fixes

* 根治 SessionEnd hook SIGINT 崩溃 ([#300](https://github.com/hdot123/memory/issues/300)) ([1ffe055](https://github.com/hdot123/memory/commit/1ffe055ca6eb01333ce38b82c320c9a6a77b2c0c))

## [0.13.2](https://github.com/hdot123/memory/compare/v0.13.1...v0.13.2) (2026-08-04)


### Bug Fixes

* upgrade-consumer 添加 --break-system-packages 修复 PEP 668 限制 ([#297](https://github.com/hdot123/memory/issues/297)) ([76c63cb](https://github.com/hdot123/memory/commit/76c63cb1837fee73d522d9ceac86ef1c069574aa))

## [0.13.1](https://github.com/hdot123/memory/compare/v0.13.0...v0.13.1) (2026-08-04)


### Bug Fixes

* 修复 upgrade-consumer 使用错误 Python 路径，修复 workflow_dispatch 发版失败 ([#295](https://github.com/hdot123/memory/issues/295)) ([2bbdb3d](https://github.com/hdot123/memory/commit/2bbdb3dd0c9f498740b919e661c51ba0daa6e02c))

## [0.13.0](https://github.com/hdot123/memory/compare/v0.12.0...v0.13.0) (2026-08-04)


### Features

* 发版后自动升级 Mac 全局 memory-core 安装 ([#293](https://github.com/hdot123/memory/issues/293)) ([4bfc42f](https://github.com/hdot123/memory/commit/4bfc42f4d2712d815430305e56082bad21fdde92))

## [0.12.0](https://github.com/hdot123/memory/compare/v0.11.1...v0.12.0) (2026-08-04)


### Features

* release-please 启用 automerge，CI 通过后自动合并 ([#291](https://github.com/hdot123/memory/issues/291)) ([4671873](https://github.com/hdot123/memory/commit/467187320ab9eda2a1678aef0bf1d0c6476de211))

## [0.11.1](https://github.com/hdot123/memory/compare/v0.11.0...v0.11.1) (2026-08-04)


### Bug Fixes

* 修复 branch-cleanup.yml 安全性问题 ([#289](https://github.com/hdot123/memory/issues/289)) ([fec5c85](https://github.com/hdot123/memory/commit/fec5c857b2f4d31fd4fdacc1be2b9d0ff2655069))

## [0.11.0](https://github.com/hdot123/memory/compare/v0.10.1...v0.11.0) (2026-08-04)


### Features

* 添加自动清理孤立分支的 GitHub Actions workflow ([#286](https://github.com/hdot123/memory/issues/286)) ([7609869](https://github.com/hdot123/memory/commit/76098691b87f0601956580f4b865cafdd69d5100))

## [0.10.1](https://github.com/hdot123/memory/compare/v0.10.0...v0.10.1) (2026-08-04)


### Bug Fixes

* release-please 使用 DISPATCH_TOKEN 触发下游 workflow ([#284](https://github.com/hdot123/memory/issues/284)) ([221040d](https://github.com/hdot123/memory/commit/221040d9ce807a56f7d7d6417d9e7587852a41c0))

## [0.10.0](https://github.com/hdot123/memory/compare/v0.9.5...v0.10.0) (2026-08-04)


### Features

* 引入 release-please 自动化版本管理 ([#270](https://github.com/hdot123/memory/issues/270)) ([95d80a0](https://github.com/hdot123/memory/commit/95d80a0d98679f07647b506d4b415c0d86faeee8))
* 引入 release-please 自动化版本管理 ([#273](https://github.com/hdot123/memory/issues/273)) ([b1f7109](https://github.com/hdot123/memory/commit/b1f7109c8b679c3ac71d7048a0c0fe01a709eaae))


### Bug Fixes

* 为 README.md 添加 x-release-please-version 注解 ([#283](https://github.com/hdot123/memory/issues/283)) ([4e8a910](https://github.com/hdot123/memory/commit/4e8a910183f63e360fe0cbf09242cdbe17057b52))
* 修正 release-please extra-files 配置，README.md 使用 rewrite 类型 ([#280](https://github.com/hdot123/memory/issues/280)) ([1cd1bd5](https://github.com/hdot123/memory/commit/1cd1bd55c9a0febce77e8d3de57fc3d4d3aa6cd3))
* 修正 release-please extra-files 配置，移除 type: rewrite ([#282](https://github.com/hdot123/memory/issues/282)) ([2898aa9](https://github.com/hdot123/memory/commit/2898aa969355a82b1720afe3df57077a3ed565d1))
* 修正 release-please manifest 格式，添加 tag 推送触发器 ([#276](https://github.com/hdot123/memory/issues/276)) ([853ce83](https://github.com/hdot123/memory/commit/853ce830bf4d0ae43f8a71cd1bee9bc9d72b9beb))
* 暴露 __version__ 让 release-please 原生 bump 版本号 ([#278](https://github.com/hdot123/memory/issues/278)) ([f4e0e54](https://github.com/hdot123/memory/commit/f4e0e54299f8e1d0e43e62b7e39d29b31b22dd78))


### Documentation

* 发布流程文档全面更新，对齐 release-please 自动化 ([#271](https://github.com/hdot123/memory/issues/271)) ([3c61440](https://github.com/hdot123/memory/commit/3c614406b8cb509016157f570d3605b26f592a14))
* 更新发版流程文档对齐 release-please 自动化 (INFRA-37) ([#277](https://github.com/hdot123/memory/issues/277)) ([007658a](https://github.com/hdot123/memory/commit/007658acf6764a6049bc51aaace114dc12002c9a))
* 标准化发版流程文档，引入 release-please 自动化 ([#274](https://github.com/hdot123/memory/issues/274)) ([09ad703](https://github.com/hdot123/memory/commit/09ad7031074c0d7454a09e21fe59217a588df170))

## [0.9.5] - 2026-08-04

### Added
- **release-please 自动化版本管理**：引入 [release-please](https://github.com/googleapis/release-please) 自动管理版本号、CHANGELOG 和 GitHub Release。基于 Conventional Commits 自动判定版本级别（patch/minor/major）。
- **发版流程文档**：新增 `docs/guides/release-guide.md` 发版指南，覆盖自动发版、手动发版、回滚、下游通知全流程。

### Changed
- **版本号一致性**：pyproject.toml、constants.py、README.md 统一为 0.9.5
- **测试版本号读取**：测试文件通过 `CURRENT_MEMORY_VERSION` 动态读取版本号，消除硬编码

### Notes
- release-please 使用 `packages` 模式，manifest 格式为 `{"\u002e": "X.Y.Z"}`
- `release-and-dispatch.yml` 支持 tag 推送触发（`push: tags: [v*]`）和手动触发（`workflow_dispatch`）

## [0.9.4] - 2026-08-01

### Added
- **生命周期事件按项目分片存储**：从全局 `events.jsonl` 迁移到 `projects/{project_id}/events/{YYYY-MM-DD}.jsonl` 结构，支持按项目和日期隔离事件，便于归档和清理。
- **自动清理机制**：新增 `_cleanup_old_event_files()` 函数，通过 `MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS` 环境变量配置保留天数（默认 30 天，设为 0 禁用），每个项目每天最多清理一次。
- **迁移 CLI 工具**：`memory-lifecycle-migrate` 命令将旧的 `events.jsonl` 迁移到新的分片结构，支持幂等运行、自动归档原文件、输出统计信息。
- **向后兼容性测试**：新增 VAL-COMPAT-01~04 和 VAL-CROSS-01~03 测试，验证 `rebuild_path_index()`、`build_project_lifecycle_record()`、`hook_event_stats.py` 不受影响，以及完整生命周期原子性、迁移后写入连续性、并发项目隔离。

### Changed
- **生命周期事件写入路径**：`record_project_lifecycle()` 现在写入 `projects/{project_id}/events/{YYYY-MM-DD}.jsonl` 而非全局 `events.jsonl`。返回字典的 `event_log` 字段指向新路径。
- **文档更新**：HOOK_INTEGRATION_SPEC.md 新增第 9 章，说明新的事件存储结构、写入路径、自动清理、迁移工具和向后兼容性。

### Fixed
- **迁移健壮性**：非对象 JSON 行（如 `123`、`[1,2]`）不再崩溃，通过 `isinstance(event_data, dict)` 守卫优雅跳过 (PR #232)。
- **迁移统计准确性**：空行计入 `skipped` 计数器，确保 `written + skipped == total_read` 对账成立 (PR #232)。
- **清理日志可见性**：`_cleanup_old_event_files()` 和 `record_project_lifecycle()` 中的清理异常现在发出 `warnings.warn()` 而非静默吞掉 (PR #232)。
- **retention 环境变量容错**：非整数 `MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS` 值回退到默认 30，不再静默禁用清理 (PR #232)。
- **版本一致性**：0.9.3 → 0.9.4 全量同步（constants.py、compat.py、README.md、全部 test fixtures） (PR #232)。

### Notes
- 全局 `events.jsonl` 已弃用但不会被删除，可通过 `memory-lifecycle-migrate` 迁移并归档为 `events.jsonl.archived`
- 所有现有测试通过，无破坏性变更

## [0.9.3] - 2026-08-01

### Changed
- **Hook 性能优化**：非注入事件（stop、notification、subagent-stop、post-tool-use、pre-compact、session-end）实现快速路径，跳过 `build_context_package()` 和 artifact snapshot 写入，仅保留生命周期记录、metrics 和轻量审计日志。预期减少 90% 文件读取、60% git 子进程、50% 文件写入。注入事件（session-start、prompt-submit）行为不变 (PR #229)。

### Fixed
- `_try_resign_ownership` silent exception swallowing: expanded to `_try_resign_all`, which now reports errors instead of `except: pass`.
- `path-index.json` divergence from the `projects/` directory: no rebuild mechanism existed before; `memory-lifecycle-rebuild` closes this gap.
- 非注入事件（stop/notification/session-end）输出抑制：成功时返回 `{"suppressOutput": true}` 避免终端空输出干扰，降级状态仍返回 `{}` 保持错误可见 (PR #227)。

## [0.9.1] - 2026-07-24

### Fixed
- **SessionEnd hook SIGALRM boot-timeout 保护**: 修复 SessionEnd hook 在系统高负载时 import 超时被 Factory SIGINT 强杀的问题。添加 8 秒 SIGALRM boot-timeout 保护，让脚本在 Factory 10 秒 SIGINT 强杀前自行干净退出（exit 0）

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
