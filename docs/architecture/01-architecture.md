---
type: "[DOC:DESIGN]"
title: "Memory 模块总体架构"
shortname: DES-001
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [architecture,overview]
related: [DES-002, DES-003, DES-004]
---

> 文档编号：DES-001 | 版本：V1.1 | 日期：2026-09-05 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05 (v0.45.6)。如需精确接口签名，请参考源码（`memory_core/`）与 `docs/specs/` 各规范文档。

# Memory 模块架构设计文档

> 创建日期：2026-04-26（最后校准 2026-09-05）
> 维护人：D1（文档整理员）
> 状态：可评审

---

> **📌 2026-09-05 校准备注**：本文档上次校准于 2026-05-14（v0.4.0 Beta，workbot/AEdu 适配器世界），此后仓库经历约 933 个 commit 的演进。本次校准涉及的重大变更：
>
> 1. **三层架构**（v0.8.0）：Layer 1 `~/.memory-core/`（全局运行时）、Layer 2 `~/.memory/global-kb/`（operations/engineering/collaboration/pending 四域）、Layer 3 项目 `memory/`；路由遵循项目优先、全局兜底（`adapter.toml` `[global_kb]` 段）。
> 2. **仓库身份转型**：memory-core 是可复用的**只读协议库**（source repo），自身不存储业务项目状态；消费项目经 `memory-init` 初始化独立记忆。隐藏目录 `.memory/` 已于 v0.5.0 移除，项目配置位于 `memory/system/`（adapter.toml / ownership.toml / memory.lock / migrations.log / manifest.json / integrity-audit.jsonl）。
> 3. **所有权模型 + PreToolUse 守卫**：`memory_core/ownership.py` 域表 + `pretooluse_guard` 故障关闭拦截（exit 0 允许 / exit 2 阻止）、共享脱敏模块 `_redaction.py`、绝对路径归一化；source repo 支持 readonly / develop 双模式。
> 4. **模块拆分与门面**：gateway / init / migrate 主体拆为 `_*` 前缀子模块（均 ≤500 行），原文件保留薄门面；patch-redirect 兼容层维持旧测试打桩语义；console 入口 `memory-hook-gateway` 改指 `hook_runtime_guard:gateway_main`。
> 5. **引擎迁移 infra-core**（2026-08 M1–M5）：version-sync、每日审计、错误模式检测等执行体迁至 infra-core（pin v0.11.1），本仓 CI 维护 workflow 全部 thin caller 化；M5 收缩删除本地执行体副本（含 `daily_kb_audit.py` 与 `_audit_*` 族）。
> 6. **遥测本地优先**：hook 热路径只写本地 `metrics.jsonl`，session-start 每小时窗口批量同步 PostHog（2s 连通探测、`.offset` 伴车推进、路径脱敏）。
> 7. **workbot 时代终结**：`workbot_policy.py` / `workbot_runtime_profile.py` 已删除；adapters 目录仅剩 `neutral_policy.py` 与 `default_runtime_profile.py`；宿主为 factory / zcode（PR #1107 新增 zcode，v0.45.5 起随 release 生效）。
> 8. **版本与依赖**：v0.4.0 → v0.45.6；`pyproject.toml` 声明 `requires-python = "==3.12.*"`，运行时依赖 posthog、mcp、pyyaml、infra-core（git pin v0.11.1）——不再是"零第三方依赖"。

## 1. 仓库概览

`memory` 仓库（GitHub `hdot123-org/memory`）发布 Python 包 `memory-core==0.45.6`，是一个**可复用的只读协议库**：提供 `memory/` 协议、模板、Schema、Validator、Migration 与 hook CLI 工具，供消费项目初始化和管理项目级记忆。本仓库**不存储任何业务项目状态**（见 `docs/specs/BOUNDARY.md`）；消费项目通过 `memory-init --target <项目>` 获得独立的 `memory/` 布局。

包声明（`pyproject.toml`，2026-09-05 实测）：

| 项 | 值 |
|----|----|
| 包名 / 版本 | `memory-core` / `0.45.6` |
| Python | `==3.12.*`（仅支持 3.12） |
| 运行时依赖 | `posthog>=3.0,<8.0`、`mcp>=1.0,<2.0`、`pyyaml>=6.0`、`infra-core @ git+...@v0.11.1` |
| 许可证 | MIT |

核心设计原则：

- **一个正式入口**：统一 gateway（console 入口 `memory-hook-gateway`，经 `hook_runtime_guard.gateway_main` 引导后进入 gateway 门面 `main()`）
- **一个正式出口合同**：统一 route/write contract（context package，内部 v2（`wb-hook-v2`）→ 对外 `context-package-v1`）
- **项目隔离**：不同项目只做 adapter 配置适配（消费项目 `memory/system/adapter.toml`），不改入口/出口协议
- **模块中立**：模块层不内建任何单项目默认真相；唯一的 default adapter 从目标项目的 `adapter.toml` 动态生成配置
- **存储与加载分离**：memory-core 只提供协议与工具，context-package 在 session-start / prompt-submit 时按三层路由动态构建

## 2. 仓库目录结构

### 2.1 顶层结构（2026-09-05 实测）

```
memory/                          # 仓库根（GitHub 主仓 hdot123-org/memory）
├── .github/                     # CI/CD：ci.yml（ci-ok 聚合门禁）、release-please、
│                                #   thin caller 维护 workflow（evolution-scan/heartbeat/
│                                #   governance、droid-review、auto-merge、branch-cleanup）
├── .evolution/                  # evolution scanner 消费配置（rule_packs 引用 infra-core）
├── .pre-commit-config.yaml      # 本地 pre-commit（ruff/mypy 与 CI 对齐）
├── docs/                        # 仓库级文档
│   ├── architecture/            # 架构设计文档（本系列 01–10 + API-CONTRACT 等）
│   ├── specs/                   # 规范（BOUNDARY、MEMORY_LOCK、PATH_INDEX、M5-SHRINK-DISPOSITION 等）
│   ├── guides/                  # 指南（含 release-guide）
│   ├── CLASSIFICATION.md        # 文档分类决策树
│   └── INDEX.md
├── memory/                      # 本仓自身记忆区（kb/docs/log/system；source repo readonly 模式）
├── project-map/                 # 项目地图（INDEX + legal-core-map + ingestion-registry-map）
├── scripts/                     # 守护脚本（check_boundary.py、check_fix_has_test.py、
│                                #   write-pending-ci.sh wrapper、release_rollback.sh 等）
├── tests/                       # 216 个 Python 文件（201 个 test_* 测试模块、12 个
│                                #   *_helpers.py 辅助模块、conftest.py、verify_routing.py）
├── workspace/                   # 通用模板（templates/：code-review 模板、skills、memory）
├── artifacts/                   # 运行时产物（memory-hook 上下文、events.jsonl、metrics.jsonl）
├── memory_core/                 # Python 包目录
│   ├── constants.py             # 单一事实源：版本 / SUPPORTED_HOSTS / Schema 常量
│   ├── ownership.py             # 所有权模型（域表、路径分类、source repo 模式）
│   ├── compat.py                # 兼容层
│   ├── default_posthog_key.txt  # 内置公开 PostHog API Key（data 文件）
│   ├── memory/                  # 包内模板知识库（kb/lessons、kb/decisions、kb/global）
│   └── tools/                   # 代码层：88 个模块，合计 28,706 行
├── conftest.py                  # pytest 根配置
├── pyproject.toml               # 包定义 / console scripts / pytest / mypy 配置
├── ruff.toml / uv.lock / requirements-lock.txt / vulture_whitelist.py
├── README.md / CHANGELOG.md / CONTRIBUTING.md / RELEASE.md / MEMORY-STRUCTURE.md
└── AGENTS.md / INDEX.md / LICENSE / MANIFEST.in
```

### 2.2 `memory_core/tools/` — Python 代码层（88 个模块 / 28,706 行，wc -l 实测）

按域归纳（行数为 2026-09-05 `wc -l` 实测）：

| 域 | 模块（行数） | 职责 |
|----|--------------|------|
| **gateway 门面** | `memory_hook_gateway.py`（494） | 薄门面：re-export 全部拆分模块符号 + 安装 patch-redirect |
| **gateway 子模块** | `_gateway_handlers.py`（495）、`_gateway_policy.py`（487）、`_gateway_telemetry.py`（483）、`_gateway_config.py`（467）、`_gateway_dispatch.py`（444）、`_gateway_artifacts.py`（301） | 六个单一职责模块：事件处理与 main / 策略与上下文构建 / 遥测同步 / 配置常量与 adapter 存储 / 调度与 delegate / artifact 写入 |
| **gateway 兼容层** | `_gateway_patch_redirect.py`（158） | 把门面符号的 monkeypatch 重定向到实际子模块（旧测试语义不变） |
| **守卫族** | `_guard_classify.py`（1225）、`pretooluse_guard.py`（475）、`_guard_patterns.py`（147） | PreToolUse 所有权拦截：工具载荷分类、保护路径模式、guard CLI |
| **hook 核心** | `memory_hook_impls.py`（904）、`memory_hook_core.py`（552）、`memory_hook_interfaces.py`（341）、`memory_hook_schema.py`（424）、`memory_hook_config.py`（262）、`memory_hook_metrics.py`（138）、`cmux_hook_state.py`（184）、`hook_event.py`（211）、`memory_root_discovery.py`（106）、`hook_runtime_guard.py`（40）、`memory_hook_provider_rollback.py`（58）、`memory_hook_provider_probe.py`（73） | 接口默认实现 / 核心组装 / 接口契约 / v2→v1 Schema 转换 / CoreConfig dataclass / metrics.jsonl 写入 / hook 状态文件 / 引导守卫 |
| **init 族** | `init_project_memory.py`（419，门面）+ `_init_autofill.py`（376）、`_init_hooks.py`（334）、`_init_render.py`（331）、`_init_templates_misc.py`（306）、`_init_pipeline.py`（301）、`_init_templates_plans.py`（300）、`_init_templates_core.py`（281）、`_init_config.py`（246）、`_init_finalize.py`（234） | `memory-init` 执行体：布局创建/采纳/更新/修复、auto-fill、hooks 渲染 |
| **migrate 族** | `migrate_project_memory.py`（269，门面）+ `_migrate_orchestration.py`（483）、`_migrate_registry.py`（315）、`_migrate_v05.py`（299）、`_migrate_rollback.py`（259）、`_migrate_cli.py`（181）、`_migrate_hooks.py`（148）、`_migrate_constants.py`（84）、`_migrate_patch_redirect.py`（71） | `memory-migrate` 执行体：版本/Schema 迁移与回滚 |
| **所有权 / 完整性** | `ownership_cli.py`（733）、`memory_hook_integrity_manifest.py`（690）、`memory_integrity_resign.py`（256）、`memory_hook_integrity_verify.py`（214）、`memory_hook_integrity_keys.py`（72） | `memory-ownership` CLI；manifest 签名/验证/重签（SHA-256 + 密钥） |
| **遥测 / 日志** | `session_end_logger.py`（696）、`telemetry_bridge.py`（423）、`error_logger.py`（234）、`posthog_client.py`（170）、`_redaction.py`（130）、`log_utils.py`（47） | SessionEnd 日志（双预算扫描）、PostHog 桥（memory.* 事件）、错误日志、共享脱敏 |
| **生命周期 / 宿主** | `project_lifecycle.py`（666）、`daily_summary_generator.py`（653）、`factory_global_hooks.py`（395）、`codex_session_analyzer.py`（301）、`denylist.py`（190）、`feature_flags.py`（179）、`task_dispatcher.py`（150） | path-index 生命周期记录/重建、每日摘要、Factory 全局 hook 安装器、拒绝列表、特性开关 |
| **校验 / 审计** | `consistency_check.py`（964）、`validate_project_memory.py`（881）、`validate_memory_system.py`（558）、`business_policy_checks.py`（706）、`project_probe.py`（643）、`verify_consumer.py`（281）、`adapter_toml_schema.py`（318）、`evidence_ref_validator.py`（139）、`prompt_validator.py`（81）、`index_schema.py`（113） | `memory-validate` / `memory-consistency-check` / `memory-verify-consumer` 执行体 |
| **全局 KB** | `global_kb_init.py`（296）、`promote_global_kb.py`（260） | Layer 2 `~/.memory/global-kb/` 初始化与 `memory-promote` 晋升 |
| **MCP / 其他** | `mcp_server.py`（829）、`apply_residue_plan.py`（851）、`hook_upgrade.py`（506）、`hook_event_stats.py`（353）、`memory_health_report.py`（243）、`doc_router.py`（72）、`template_sync.py`（35） | `memory-mcp-server`（stdio MCP，9 个工具）、残留处置、hook 升级、健康报告、文档路由 |
| **共享工具** | `_patch_redirect_shared.py`（132）、`_rule_helpers.py`（124）、`_scope_resolver_base.py`（97）、`_file_utils.py`（79）、`_validation_constants.py`（76）、`_rule_types.py`（72）、`_rule_errors.py`（31）、`_utils.py`（30） | 跨族复用的路径/规则/文件工具 |

注：早期版本的 `daily_kb_audit.py` 门面与 `_audit_*` 子模块族已随 M5 收缩删除（引擎迁 infra-core，见 `docs/specs/M5-SHRINK-DISPOSITION.md`）；`version_sync.py`、`error_pattern_detector.py` 等六个引擎工具同步删除。

### 2.3 `memory_hook_adapters/` — 适配层

| 文件 | 行数 | 职责 |
|------|------|------|
| `neutral_policy.py` | 23 | 宿主中性基类 `NeutralGatewayBusinessPolicy`（继承 `GatewayBusinessPolicyImpl`） |
| `default_runtime_profile.py` | 245 | 从目标项目 `memory/system/adapter.toml` 生成通用 runtime profile（`build_default_runtime_profile`），含 `[global_kb]` 解析（`GLOBAL_KB_ROOT` / `GLOBAL_KB_ENABLED`） |

**已移除**：`workbot_policy.py`（82 行）与 `workbot_runtime_profile.py`（267 行）随 workbot 时代终结删除；`docs/workbot-cli-tools.md` 归档说明不复存在。注册表 `_ADAPTER_REGISTRY` 现仅含 `default` 一个条目。

### 2.4 `memory/` — 本仓知识库 + 文档（source repo 自身）

```
memory/
├── docs/                     # 记忆系统文档（INDEX + 全景 + drafts/plans/runbooks 等分类目录）
├── kb/
│   ├── INDEX.md
│   ├── decisions/            # 决策记录（15+ 篇）
│   ├── lessons/              # 经验教训（25+ 篇）
│   ├── patterns/             # 错误模式 registry（registry.jsonl，infra-error-patterns 产物）
│   ├── projects/             # 项目真相（default.md 等）
│   └── global/               # 跨项目规范：truth-model.md、memory-system.md、
│                             #   memory-routing.md、hook-contract.md、
│                             #   project-map-governance.md、kb-format-spec.md、
│                             #   orchestrator-security-standard.md、INDEX.md
├── log/                      # 每日事实日志（YYYY-MM-DD.md）
├── system/
│   ├── ownership.toml        # source repo 所有权（readonly 模式）
│   └── errors/ + errors.log  # 错误日志
└── artifacts/memory-hook/    # gateway 运行时产物（contexts/、events.jsonl、metrics.jsonl）
```

说明：本仓是 source repo，自身 `memory/system/` 只需 `ownership.toml`（readonly 模式，无 memory.lock/adapter.toml）。消费项目的完整 `memory/system/` 六件套（memory.lock、adapter.toml、ownership.toml、migrations.log、manifest.json、integrity-audit.jsonl）由 `memory-init` 生成。旧文档描述的 `workbot-hook-contract.md`、`workbot-policy-pack.json` 等全局面文件均已清理；policy-pack JSON 不再是运行时前提（`PolicyRegistryImpl` 内置 repository-agnostic 兜底策略）。

## 3. 模块角色说明

### 3.1 接口层（interfaces）

**文件**：`memory_core/tools/memory_hook_interfaces.py` — 341 行

定义核心接口族 + TypedDict（类起始行为 2026-09-05 实测）：

| 接口编号 | 接口名 | 起始行 | 职责 |
|----------|--------|--------|------|
| — | `TruthBasis` / `RegistrationCommitGate`（TypedDict） | L21 / L36 | truth basis 四要素与注册门禁的数据结构 |
| IF-1 | `HostDelegate` | L52 | 将 hook 事件委派给宿主运行时（factory/zcode） |
| IF-2 | `PolicyRegistry` | L97 | 策略查找、验证、冲突解决 |
| IF-3 | `RouteTargetPolicy` / `WriteTargetPolicy` | L193 / L206 | 路由目标解析 / 写入目标解析 |
| IF-3.5 | `GatewayBusinessPolicy` | L219 | 业务策略（项目范围判定、canonical 管理、truth basis 验证等 14 个抽象方法） |
| IF-4 | `ArtifactSink` / `ErrorSink` | L298 / L316 | 产物输出 / 错误日志 |
| IF-6 | `PathUtils` | L330 | 路径工具回调（extract_excerpt / write_targets） |

关键方法摘要（现行）：

- `HostDelegate.can_handle()` / `execute(event, raw_payload, payload)` / `noop_response()` / `host_unavailable`（属性，区分"策略决策"与"宿主不可用"）
- `PolicyRegistry.get_policy(key)` / `validate(context)` / `get_policy_pack(scope)` / `resolve_conflict(...)`
- `GatewayBusinessPolicy.determine_project_scope(cwd)` / `truth_basis_for_scope(scope)` / `validate_project_map_files()` 等
- `ArtifactSink.write(package)` / `ensure_dirs()`

### 3.2 默认实现层（impls）

**文件**：`memory_core/tools/memory_hook_impls.py` — 904 行

| 类名 | 起始行 | 实现接口 | 职责 |
|------|--------|----------|------|
| `FactoryDelegate` | L125 | `HostDelegate` | factory/zcode 宿主的中性委派：所有事件返回空 JSON（`{}\n`），无需 cmux 集成 |
| `NoopHostDelegate` | L152 | `HostDelegate` | 兜底 noop 委派：输出 `host_unavailable: true` + `policy_decision: "no_host"` |
| `resolve_host_delegate()` | L194 | — | 按 host 解析委派：SUPPORTED_HOSTS（factory/zcode）→ FactoryDelegate，其余 → NoopHostDelegate；支持 auto/noop/cmux 三种模式 |
| `PolicyRegistryImpl` | L227 | `PolicyRegistry` | 策略注册表：policy-pack JSON 可选加载（`MEMORY_HOOK_POLICY_PACK_PATH`）、内置 repository-agnostic 兜底策略、冲突策略表 |
| `RouteTargetPolicyImpl` | L437 | `RouteTargetPolicy` | 路由目标映射（fact/global-rule/source-material/project-runtime/system-error/invalid-memory） |
| `WriteTargetPolicyImpl` | L505 | `WriteTargetPolicy` | 写入目标映射（kb/global/project/decision/lesson/docs/log 等） |
| `GatewayBusinessPolicyConfig` | L542 | 配置 dataclass | 承载业务策略配置参数（canonical、refs、governance 等） |
| `GatewayBusinessPolicyImpl` | L584 | `GatewayBusinessPolicy` | 业务策略核心：scope 解析（继承 `_ScopeResolverBase`）、truth basis 校验、project-map 验证、governance/event-contract blocker |
| `ArtifactSinkImpl` | L665 | `ArtifactSink` | 产物写入：snapshot + latest + 按日 event log |
| `ErrorSinkImpl` | L720 | `ErrorSink` | 错误日志写入 |
| `ArtifactWriter` | L808 | — | gateway 使用的写入器（含 last_error 状态） |
| `DelegateRouter` | L870 | — | 按 SUPPORTED_HOSTS 路由 delegate |

**已移除**：`CodexDelegate` / `ClaudeDelegate`（及 `cmux codex-hook` / `cmux claude-hook` 执行协议）已删除；`_gateway_dispatch.py` 中保留 `_delegate_codex` / `_delegate_claude` 两个历史函数，但 CLI `--host` 的 choices 限定为 `SUPPORTED_HOSTS = ("factory", "zcode")`（`memory_core/constants.py`），这两个分支不再可达。

`GatewayBusinessPolicyImpl` 职责要点：

- Truth basis 四要素校验（source/authority/evidence/conflict）
- Project-map 合法性验证（active-legal-map-only 合同）
- Governance frozen tuple / event contract blocker（scope 门控，default profile 下默认为空集）
- Event contract 对齐验证（按 adapter 配置启用）

### 3.3 核心组装层（core）

**文件**：`memory_core/tools/memory_hook_core.py` — 552 行

| 函数名 | 起始行 | 职责 |
|--------|--------|------|
| `_resolve_callbacks()` | L16 | 从 CoreConfig 的复合接口对象或扁平回调字段解析回调集 |
| `registration_phase_from_policy_pack()` | L76 | 从 policy pack 解析 registration phase |
| `evaluate_registration_commit_gate()` | L92 | 评估注册提交门禁（enforced/awaiting/passed/failed） |
| `_compute_truth_basis_errors()` 等私有辅助 | L131–L330 | canonical 缺失收集、truth basis 校验、状态推导、system/project context 组装 |
| `build_context_package_core()` | L331 | 核心组装：约 39 个 keyword-only 参数（含 v0.8.0 新增 `global_kb_root` / `global_kb_enabled`） |
| `build_context_package_from_config()` | L507 | 结构化 `CoreConfig` 变体（推荐入口，行为与 core 等价） |

`build_context_package_core()` 输出结构（`schema_version: "wb-hook-v2"`）：

```python
{
    "schema_version": "wb-hook-v2",
    "generated_at": "...",
    "host": "...",              # factory | zcode
    "event": "...",
    "repo_root": "...", "workspace_root": "...", "cwd": "...",
    "project_scope": "...",
    "status": "ok" | "degraded" | "blocked",   # blocked = 完整性校验失败
    "missing_paths": [...], "warnings": [...], "validation_errors": [...],
    "system_context": {...},
    "project_context": {...},
    "task_context": {...},
    "allowed_reads": [...],
    "allowed_writes": {...},
    "evidence_refs": [...],
}
```

对外出口经 `memory_hook_schema.py`（424 行）转换为 `context-package-v1`（`convert_to_v1`），或进一步转为 legacy memory-v1（`convert_legacy_to_memory_v1`）。配置载体为 `memory_hook_config.py`（262 行）的 `CoreConfig` dataclass。

### 3.4 Gateway 编排层（gateway）

**门面文件**：`memory_core/tools/memory_hook_gateway.py` — 494 行（薄门面，全部符号 re-export）

Gateway 拆分为六个单一职责子模块（均 ≤500 行）+ patch-redirect 兼容层：

| 子模块 | 行数 | 职责 |
|--------|------|------|
| `_gateway_config.py` | 467 | 路径常量（`discover_roots` 发现 REPO_ROOT/WORKSPACE_ROOT）、adapter 配置存储（`_adapter_config` + 线程安全 `get_config` / `reload_adapter`）、IF-5 门面、完整性签名/验证 |
| `_gateway_artifacts.py` | 301 | artifact / error 写入（含直接落盘 fallback）、只读 source-repo package（`_build_readonly_source_repo_package`）、健康告警注入 |
| `_gateway_policy.py` | 487 | core builder 解析（provider 双轨）、业务策略委托、`build_context_package` 组装、git registration probe |
| `_gateway_telemetry.py` | 483 | PostHog 批量同步（小时窗口 + backoff）、prompt-submit 实时日志（SIGALRM 超时保护） |
| `_gateway_dispatch.py` | 444 | CWD 发现、delegate 执行、Factory 官方 hook 输出格式（`_build_factory_hook_output`）、fast-path metrics/event log |
| `_gateway_handlers.py` | 495 | 事件处理器（source repo 检查、PreToolUse guard、session-start 副作用）与 `main()` 主入口、`_gateway_excepthook` |
| `_gateway_patch_redirect.py` | 158 | 兼容层：门面符号的 monkeypatch 重定向到实际子模块 |

编排要点（详见 DES-002）：

1. **引导**：console 入口 `hook_runtime_guard.gateway_main` 先装 SIGALRM(8s)/SIGINT 处理器再 import gateway
2. **门禁**：source repo readonly 检查 → 拒绝列表 → 外部上下文 noop → PreToolUse guard 子进程拦截
3. **组装**：`build_context_package()` 构建 `CoreConfig` → `_resolve_core_builder()`（provider 双轨）→ `build_context_package_from_config`
4. **写入**：`ArtifactWriter.write()`（snapshot + latest + 按日 event log）→ `_integrity_sign` 增量重签 → `emit_metrics`
5. **输出**：`--no-delegate` 输出 JSON；否则 `_execute_delegate` → factory/zcode 走 `_build_factory_hook_output`（SessionStart/UserPromptSubmit 注入 additionalContext）

### 3.5 适配层（adapters）

**目录**：`memory_core/tools/memory_hook_adapters/`

| 文件 | 行数 | 职责 |
|------|------|------|
| `neutral_policy.py` | 23 | `NeutralGatewayBusinessPolicy`：宿主中性基类，继承 `GatewayBusinessPolicyImpl` |
| `default_runtime_profile.py` | 245 | `build_default_runtime_profile(repo_root, workspace_root)`：读取目标项目 `memory/system/adapter.toml`，生成通用配置字典 |

`build_default_runtime_profile()` 返回的键与旧 workbot profile 同构（`PROJECT_MAP_ROOT`、`TRUTH_MODEL`、`REQUIRED_CANONICAL`、`PROJECT_CANONICAL`、`SCOPE_MATCH_HINTS`、`ARTIFACT_COMPACTION`、`POLICY_ALLOWED_SCOPES` 等 40+ 键），差异在于**全部从 adapter.toml 派生**而非硬编码项目路径，并新增 `GLOBAL_KB_ROOT` / `GLOBAL_KB_ENABLED`（v0.8.0 `[global_kb]` 段）。project scope 取自 `adapter.toml [routing].project_scope`（缺省 `default`）。

### 3.6 守卫 / 所有权 / 遥测 / 生命周期模块

| 模块 | 行数 | 职责 |
|------|------|------|
| `memory_core/ownership.py` | 785 | 所有权模型：`OwnershipDomain`/`OwnershipResource`/`Owned`/`NotOwned`/`MemoryOwnership`、三级保护（RECOMMENDED/STANDARD/CRITICAL）、`classify_owned_path`、`_normalize_to_project_relative`（绝对路径归一化单一事实源）、`load_memory_ownership`（ownership.toml）、`is_memory_core_source_repo`、`get_source_repo_mode`（readonly/develop） |
| `_guard_classify.py` / `pretooluse_guard.py` / `_guard_patterns.py` | 1225 / 475 / 147 | PreToolUse 守卫：stdin JSON → 工具载荷分类（Write/Edit/MultiEdit/NotebookEdit/Execute）→ `{"decision": "allow"\|"block"}` 双格式输出；exit 0 允许 / exit 2 阻止 |
| `hook_runtime_guard.py` | 40 | console 入口引导守卫：import 前 installing SIGALRM(8s)+SIGINT → `os._exit(0)` |
| `factory_global_hooks.py` | 395 | `memory-factory-hooks install`：渲染 `~/.factory/bin/memory-hook` wrapper（`shutil.which` 解析绝对路径）、注册 9 个事件到 `~/.factory/settings.json` |
| `session_end_logger.py` | 696 | SessionEnd 摘要：确定性双预算扫描（TIME_BUDGET 1.8s / BYTE_BUDGET 8MB / CHUNK 64KB / MAX_LINE 1MB） |
| `telemetry_bridge.py` / `posthog_client.py` | 423 / 170 | 统一 PostHog 桥（`memory.*` 事件、路径 basename 脱敏、fail-safe） |
| `project_lifecycle.py` | 666 | 全局生命周期 registry（`~/.memory-core/project-lifecycle/`）与 `memory-lifecycle-rebuild` / `memory-lifecycle-migrate` CLI |
| `memory_hook_metrics.py` | 138 | 每次调用追加 `metrics.jsonl`（`MEMORY_HOOK_METRICS_DISABLED` / `MEMORY_HOOK_METRICS_PATH`） |
| `mcp_server.py` | 829 | `memory-mcp-server`：stdio MCP 服务器，9 个工具（load_context / search_memory / resolve_doc_path / save_memory / validate_write / record_event / get_health / list_projects / get_daily_summary） |
| `cmux_hook_state.py` | 184 | hook 状态文件管理（lock / load / write / record_hook_event），保留供 cmux 集成场景 |

## 4. 模块依赖关系图

```
                          ┌────────────────────────────┐
                          │  hook_runtime_guard.py     │ ← console 入口（SIGALRM 引导）
                          └─────────────┬──────────────┘
                                        ▼
          ┌───────────────────────────────────────────────┐
          │  memory_hook_gateway.py（门面 494 行）          │
          │  re-export + patch-redirect 兼容层             │
          └───────────────┬───────────────────────────────┘
                          │ 六个单一职责子模块
     ┌──────────┬─────────┼──────────┬────────────┬─────────────┐
     ▼          ▼         ▼          ▼            ▼             ▼
┌─────────┐┌─────────┐┌──────────┐┌──────────┐┌──────────┐┌───────────┐
│_gateway_││_gateway_││_gateway_ ││_gateway_ ││_gateway_ ││_gateway_  │
│config   ││artifacts││policy    ││telemetry ││dispatch  ││handlers   │
│(467 行) ││(301 行) ││(487 行)  ││(483 行)  ││(444 行)  ││(495 行)   │
└────┬────┘└────┬────┘└────┬─────┘└────┬─────┘└────┬─────┘└─────┬─────┘
     │          │          │           │           │            │
     ▼          │          ▼           ▼           ▼            ▼
┌─────────┐    │   ┌───────────────────────────────────────────────┐
│memory_  │    │   │ memory_hook_impls.py（904 行）                 │
│hook_    │    │   │  FactoryDelegate / NoopHostDelegate /          │
│adapters/│    │   │  PolicyRegistryImpl / *PolicyImpl /            │
│default_ │    │   │  GatewayBusinessPolicyImpl / ArtifactWriter    │
│runtime_ │    │   └───────────────┬───────────────────────────────┘
│profile  │    │                   │ implements
│(245 行) │    │                   ▼
└─────────┘    │           ┌──────────────────────┐
               │           │ memory_hook_         │
               ▼           │ interfaces.py(341行) │
        ┌────────────┐     │ IF-1/2/3/3.5/4/6    │
        │memory_hook_│     └──────────────────────┘
        │core.py     │
        │(552 行)    │  ← build_context_package_core / from_config
        └─────┬──────┘     （CoreConfig: memory_hook_config.py 262 行）
              │
              ▼
        ┌────────────┐     ┌──────────────────────┐
        │memory_hook_│     │ memory_core/         │
        │schema.py   │     │ ownership.py(785 行) │
        │(424 行)    │     │ + pretooluse_guard / │
        │ v2→v1 转换 │     │ _guard_classify      │
        └────────────┘     └──────────────────────┘
```

具体 import 关系（要点）：

- `_gateway_config` import → `memory_root_discovery`（根发现）、`_file_utils`/`_rule_helpers`（工具）、`memory_core.ownership`（source repo 模式）、`project_lifecycle`、`denylist`、`memory_hook_adapters.neutral_policy` + `memory_hook_impls`（IF-5 门面）
- `_gateway_handlers` import → `memory_core.constants`（SUPPORTED_HOSTS）、`_gateway_{config,artifacts,dispatch,policy,telemetry}`、`_guard_patterns`、`memory_hook_impls.ArtifactWriter`
- `_gateway_policy` import → `memory_hook_config.CoreConfig`、`memory_hook_core.build_context_package_from_config`、`memory_hook_schema`
- `_gateway_dispatch` import → `memory_hook_impls.resolve_host_delegate`、`project_lifecycle`
- `memory_hook_core` → 无运行时模块依赖（纯函数，回调注入；TYPE_CHECKING 引 CoreConfig）
- `default_runtime_profile` import → `neutral_policy`、`adapter_toml_schema.load_adapter_toml`
- `memory_hook_impls` import → `_rule_errors`、`_file_utils`、`memory_core.constants`（延迟）

## 5. 数据流概览

### 5.1 完整调用路径（`_gateway_handlers.main()`，2026-09-05 现状）

```
宿主（factory / zcode）
    │
    │  wrapper ~/.factory/bin/memory-hook 调用 console 入口
    │  memory-hook-gateway --host factory --event <event>
    │  stdin 传入 raw_payload (JSON)
    ▼
hook_runtime_guard.gateway_main()
  └─ install_guard(): SIGALRM(8s) + SIGINT → os._exit(0)
    ▼
_gateway_handlers.main()
  1. _parse_args() / _read_payload() / _discover_cwd()
  2. _handle_source_repo_check()
     └─ memory-core source repo 且非 develop 模式
        → _build_readonly_source_repo_package()（source-repo-rules 包）→ exit 0
  3. is_denied_project_root(cwd) → 输出 "{}" → exit 0
  4. _should_noop_for_external_context() → delegate.noop_response()
  5. _handle_pretooluse_guard()（仅 pre-tool-use）
     └─ subprocess: python -m memory_core.tools.pretooluse_guard（timeout 5s）
        ├─ 成功：透传 guard stdout（allow/block 双格式 JSON），exit 0/2
        └─ 失败：fail-closed——保护路径 deny（exit 2），非保护路径 allow（exit 0）
  6. session-start 副作用（_handle_session_start_setup）：
     ├─ _launch_async_health_check()（后台健康检查）
     ├─ _update_state_dynamic_fields()
     ├─ _maybe_sync_telemetry()（每小时窗口批量同步 PostHog）
     └─ 自动版本跟随：probe_version_and_sync(cwd)（infra-core 引擎，
        探测 memory.lock 的 memory_version ≠ CURRENT_MEMORY_VERSION
        时进程内 sync_single_project；resign hook 回填本仓签名器）
  7. prompt-submit → _handle_prompt_submit_logging()（实时日志）
  8. 非注入事件 fast path（stop/notification/post-tool-use/
     subagent-stop/pre-compact/session-end）：
     └─ 生命周期记录（env 门控）+ fast-path metrics + 最小 event log
        → 输出 {"suppressOutput": true} → exit 0
  9. 注入事件（session-start / prompt-submit）全路径：
     ├─ _record_project_lifecycle_event()（env 门控）
     ├─ ArtifactWriter + build_context_package()（见 5.2）
     ├─ session-start：_inject_health_alert() + _handle_integrity_check()
     │   （manifest 验证失败 → status="blocked"）
     ├─ _write_artifacts_and_emit_metrics()（写入 + _integrity_sign + metrics）
     └─ _dispatch_output()：
         ├─ --no-delegate → 输出 context package JSON
         └─ _execute_delegate() → factory/zcode:
             _build_factory_hook_output()（SessionStart/UserPromptSubmit
             注入 "## Memory Context" additionalContext；其余 suppressOutput）
```

产物输出（默认 `ARTIFACT_ROOT = <workspace>/memory/artifacts/memory-hook/`）：

- `contexts/<YYYY-MM-DD>/<timestamp>-<host>-<event>.json`（snapshot，双写防覆盖）
- `contexts/latest-<host>-<event>.json` + 按日 latest
- `events/<YYYY-MM-DD>.jsonl`（按日 event log；legacy `events.jsonl` 同步追加）
- `metrics.jsonl`（每次调用一条指标记录）
- `memory/system/errors.log` + `errors/<YYYY-MM-DD>.log`（错误时）

### 5.2 Context Package 结构（v2，`wb-hook-v2`）

```json
{
  "schema_version": "wb-hook-v2",
  "generated_at": "2026-09-05T...",
  "host": "factory" | "zcode",
  "event": "session-start" | "prompt-submit" | "...",
  "repo_root": "...", "workspace_root": "...", "cwd": "...",
  "project_scope": "...",
  "status": "ok" | "degraded" | "blocked",
  "missing_paths": ["..."],
  "warnings": ["..."],
  "validation_errors": ["..."],
  "system_context": {
    "boot_entry": "...", "state_summary": ["..."],
    "project_map_validation": "pass" | "fail",
    "legality_contract_validation": "pass" | "fail",
    "truth_basis_validation": "pass" | "fail",
    "registration_commit_gate": { ... },
    "core_provider": "legacy" | "external-core",
    "core_provider_requested": "...",
    "policy_pack": { ... },
    "project_lifecycle": { ... }
  },
  "project_context": {
    "scope": "...",
    "canonical": "...",
    "truth_status": "truth-ready" | "truth-incomplete",
    "runtime_root": "...",
    "source_refs": [...], "authority_refs": [...], "evidence_refs": [...]
  },
  "task_context": {
    "event": "...", "task_ref": "...", "session_id": "...",
    "surface_id": "...", "workspace_id": "...", "payload_keys": ["..."]
  },
  "allowed_reads": ["..."],
  "allowed_writes": { "fact": "...", "decision": "...", "...": "..." },
  "evidence_refs": ["..."]
}
```

对外合同为 `context-package-v1`（`memory_hook_schema.convert_to_v1`），详见 `docs/architecture/API-CONTRACT.md`。

### 5.3 Provider 双轨机制

| Provider | 说明 | 触发方式 |
|----------|------|----------|
| `legacy`（默认） | 直接调用 `memory_hook_core.build_context_package_from_config` | 默认值 / fallback |
| `external-core` | 可选 provider，动态加载外部模块 | `MEMORY_HOOK_CORE_PROVIDER=external-core` |

Provider 切换逻辑（`_gateway_policy._resolve_core_builder`）：

1. 请求 `external-core` → 尝试动态导入 `MEMORY_HOOK_EXTERNAL_CORE_MODULE`（默认 `memory_core.tools.memory_hook_core`）的 `MEMORY_HOOK_EXTERNAL_CORE_FUNC`
2. 导入失败 → 自动 fallback 到 `legacy`，错误记入 `system_context.core_provider_fallback_errors` 并使 status 降级为 `degraded`
3. `MEMORY_HOOK_SHADOW_RUN` 开启时，同时运行对端 provider 做对比验证（结果记入 `system_context.shadow_run`）

### 5.4 遥测数据流（本地优先）

```
hook 调用（gateway / guard / SessionEnd）
  → memory_hook_metrics / emit_metrics 追加本地 metrics.jsonl（微秒级，零网络）
  → session-start 时 _maybe_sync_telemetry()：
       1. 小时窗口（成功后 3600s 内跳过）+ 5 分钟失败 backoff
       2. socket 探测 PostHog ingestion 域名（2s 超时）
       3. 通过 .offset 伴车文件批量发送未投递记录（BATCH_SIZE=500）
       4. 成功后推进 .offset，从 JSONL 截断已同步记录
```

## 6. 模块分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                     消费者层 (Consumers)                     │
│           Factory Droid / zcode（经 ~/.factory wrapper）     │
└──────────────────────────┬──────────────────────────────────┘
                           │ stdin (raw_payload JSON)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  引导层 (hook_runtime_guard)                 │
│         SIGALRM(8s) + SIGINT → os._exit(0)                  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            Gateway 层（门面 + 六个 _gateway_* 子模块）         │
│  main()：门禁（readonly/denylist/noop/guard）→ 组装 → 写入    │
│  → 完整性签名 → metrics → delegate 分派                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼─────────────────────┐
        ▼                  ▼                     ▼
┌───────────────┐ ┌────────────────┐ ┌────────────────────────┐
│ Core 层       │ │ Impl 层        │ │ Adapter 层             │
│ memory_hook_  │ │ memory_hook_   │ │ default_runtime_       │
│ core.py       │ │ impls.py       │ │ profile.py（读目标项目  │
│ (552 行)      │ │ (904 行)       │ │ adapter.toml）          │
│ CoreConfig +  │ │ 全部 IF 实现 + │ │ + neutral_policy.py    │
│ 回调注入组装  │ │ ArtifactWriter │ │（268 行 合计）          │
└───────┬───────┘ └───────┬────────┘ └────────────────────────┘
        │                 │
        ▼                 ▼
┌──────────────────────────────────────────┐
│ Interfaces 层：memory_hook_interfaces.py │
│ (341 行) IF-1/2/3/3.5/4/6                │
└──────────────────────────────────────────┘
        ▲
        │ 横切面（gateway 子模块直接调用）
┌───────┴──────────────────────────────────┐
│ ownership.py + pretooluse_guard 族       │
│ （PreToolUse 拦截、绝对路径归一化）        │
│ _gateway_telemetry + metrics/redaction   │
│ （本地优先遥测、共享脱敏）                 │
└──────────────────────────────────────────┘
```

分层职责：

| 层 | 文件 | 职责 | 可修改性 |
|----|------|------|----------|
| **interfaces** | `memory_hook_interfaces.py`（341 行） | 定义抽象接口与 TypedDict，不依赖任何实现 | 稳定，变更需全层同步 |
| **core** | `memory_hook_core.py`（552 行） + `memory_hook_config.py`（262 行） | 纯函数组装 + CoreConfig 载体，回调注入 | 稳定，通过参数注入扩展 |
| **impls** | `memory_hook_impls.py`（904 行） | 接口的默认实现（宿主中性） | 新增实现需对应新接口 |
| **adapters** | `memory_hook_adapters/*.py`（268 行合计） | 配置派生（adapter.toml → runtime profile） | 新项目只需 `memory-init` 写 adapter.toml |
| **gateway** | 门面（494 行）+ `_gateway_*`（2,677 行合计） | 编排：门禁 → 组装 → 写入 → 分派 | 稳定，子模块 ≤500 行 |
| **横切面** | `ownership.py`、guard 族、telemetry 族、integrity 族 | 所有权拦截、遥测、完整性签名 | 独立演进，gateway 按事件挂点调用 |

## 7. 关键设计决策

### 7.1 Adapter 配置机制（default profile + adapter.toml）

Gateway 通过 `MEMORY_HOOK_ADAPTER` 环境变量选择 adapter（**默认 `"default"`**，注册表 `_ADAPTER_REGISTRY` 现仅含 `default` 一个条目），`importlib` 动态加载 `build_default_runtime_profile(repo_root, workspace_root)`。该函数从目标项目 `memory/system/adapter.toml` 派生全部配置（含 `[global_kb]` 段），gateway 代码不硬编码任何项目路径。

**注入方式已重构**：早期版本的 `globals().update(profile)` 已改为线程安全的 `_adapter_config` 字典存储 + `get_config(key)` / `get_config_dict()` / `reload_adapter()` 访问器（`_gateway_config.py`），消除隐式全局变量。

### 7.2 Provider 双轨 + Shadow Run

- 默认 `legacy` provider（`build_context_package_from_config`）
- `MEMORY_HOOK_CORE_PROVIDER=external-core` 切换到 external provider，加载失败自动 fallback 并降级
- `MEMORY_HOOK_SHADOW_RUN=1` 同时运行对端 provider，对比结果记入 system_context（不改变主输出）

### 7.3 Artifact Compaction

`ARTIFACT_COMPACTION` 策略字典（adapter profile 提供）控制 context package 裁剪：`_apply_artifact_compaction()` 按 `include_<section>` 布尔值剥离 `system_context` / `project_context` / `task_context` / `evidence_refs` / `allowed_reads` / `allowed_writes` 六个 section。default profile 默认全包含。

### 7.4 Truth Basis 四要素

所有项目 canonical 文件必须包含 Truth Basis 四要素（`TruthBasis` TypedDict）：

- **source_refs**：信息来源（不能全是 canonical）
- **authority_refs**：权威引用（必须是 formal canonical）
- **evidence_refs**：证据引用（必须包含 lower-layer 支持）
- **conflict_status**：冲突状态（必须为 `resolved`）

校验在 `memory_hook_core._compute_truth_basis_errors` 执行，失败计入 `validation_errors` 并影响 status 推导。

### 7.5 所有权模型与只读协议库身份（2026-05 后新增）

memory-core 自身定位为 source repo：`is_memory_core_source_repo()` 探测 + `get_source_repo_mode()`（ownership.toml，readonly/develop 二值）。readonly 模式下 gateway 返回 `source-repo-rules` 上下文包（`allowed_writes: {}` + 所有权域表 + 保护路径清单），hook 对本仓写入一律拒绝；develop 模式跳过消费者验证层（`source_repo_skip_validation`）。PreToolUse 守卫以 ownership.toml 域表分类每次写工具调用，故障关闭设计确保守卫自身崩溃时保护路径仍被拒绝。

### 7.6 三层架构与项目优先路由（v0.8.0）

知识查找先命中项目 `memory/kb/`（Layer 3），领域条目缺失时 fallback 到全局 `~/.memory/global-kb/`（Layer 2，operations/engineering/collaboration/pending 四域）；`~/.memory-core/`（Layer 1）只存宿主级运行时（project-lifecycle registry、path-index、完整性密钥），不是项目记忆池。全局兜底由 `memory-init` 写入的 `adapter.toml [global_kb]` 段启用。

### 7.7 本地优先遥测（2026-05 校准后新增）

hook 热路径只写本地 JSONL（微秒级），不导入 PostHog SDK、零网络阻塞；session-start 事件按小时窗口批量同步（2s 连通探测、`.offset` 伴车增量推进、发送前路径脱敏为 basename）。所有遥测逻辑 try/except 包裹，分析失败绝不影响 hook 行为；`POSTHOG_API_KEY=''` 可整体禁用。

### 7.8 模块拆分 + 门面 + patch-redirect（M3 拆分）

gateway / init / migrate 主体按单一职责拆为 ≤500 行子模块，原文件保留薄门面（re-export）。`_gateway_patch_redirect` / `_migrate_patch_redirect` 与共享的 `_patch_redirect_shared` 把打在门面符号上的 `monkeypatch` / `patch.object` 写入重定向到实际查找该符号的子模块，保证既有测试语义不变。audit 族（`daily_kb_audit` 门面 + `_audit_*`）曾属同一拆分家族，已随 M5 引擎迁移删除。

## 8. 测试覆盖

**目录**：`tests/` — 216 个 Python 文件（201 个 `test_*` 测试模块 + 12 个纯 `*_helpers.py` 辅助模块 + `conftest.py` + `__init__.py` + `verify_routing.py`；另有 3 个 `test_*_helpers.py` 前缀辅助计入测试模块数），无子目录。

按域归纳（文件名抽样实测）：

| 域 | 代表测试文件 | 覆盖内容 |
|----|--------------|----------|
| Gateway 编排 | `test_memory_hook_gateway_coverage.py`、`test_gateway_injection_refactor.py`、`test_gateway_concurrent_config.py`、`test_gateway_project_lifecycle.py`、`test_gateway_truth_basis_coverage.py`、`test_gateway_sigint_coverage.py` | main 流程、注入事件重构、adapter 配置并发、生命周期、truth basis、SIGINT 防护 |
| 守卫 / 所有权 | `test_guard_classify.py`、`test_guard_fail_closed.py`、`test_guard_compound_escape.py`、`test_ownership_absolute_path.py`、`test_ownership_git_timeout.py`、`test_ownership_cli.py`、`test_ownership_anti_drift.py` | 载荷分类、fail-closed、复合转义、绝对路径归一化、git 超时、ownership CLI |
| 初始化 | `test_init_*.py`（10 个） | memory-init 布局创建/采纳/更新/修复、auto-fill、hooks 渲染 |
| 迁移 | `test_migrate_*.py`（4 个） | 版本迁移、0.5 遗留清理、回滚 |
| 遥测 | `test_audit_telemetry_coverage.py`、`test_gateway_telemetry_health_coverage.py` 等（6 个） | metrics 采集、批量同步、健康检查 |
| 版本跟随 | `test_auto_version_follow.py` | session-start 自动版本跟随（六分支，17 用例） |
| 引擎契约 | `test_pr_merged_verification.py`（import `infra_core.engine.evolution_utils`）等 | infra-core 引擎行为回归 |
| 完整性 | `test_integrity_*.py`（3 个） | manifest 签名/验证/重签 |
| source repo | `test_source_repo_*.py`（3 个） | readonly/develop 模式分支 |
| 其他 | MCP（`test_mcp_server.py`）、denylist、redaction、adapter.toml、factory hooks、zcode、session-end 等 | 各横切面与 CLI 入口 |

运行方式与门禁：

```bash
python -m pytest tests/     # addopts 已含 --cov=memory_core --cov-fail-under=80 --durations=10
```

CI 在自建 runner 上以串行模式（`-n 0`）运行以保证覆盖率统计准确；当前分支覆盖率基线约 84%（README 口径）。另有 ruff（含 C901 max-complexity=15）、mypy --strict（scripts/ + memory_core/ 双域）、deptry、vulture 四道静态门禁。

## 9. 环境变量（grep `os.environ` 实测，2026-09-05）

### 9.1 Gateway / 路由

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MEMORY_HOOK_ADAPTER` | `default` | 选择 adapter profile（注册表仅 `default`） |
| `MEMORY_HOOK_CORE_PROVIDER` | `legacy` | Core builder provider（`external-core` 或 `legacy`） |
| `MEMORY_HOOK_EXTERNAL_CORE_MODULE` | `memory_core.tools.memory_hook_core` | external core 模块路径 |
| `MEMORY_HOOK_EXTERNAL_CORE_FUNC` | `build_context_package_from_config` | external core 函数名 |
| `MEMORY_HOOK_SHADOW_RUN` | — | 开启 shadow run 对比 |
| `MEMORY_HOOK_FORCE` / `WORKBOT_FORCE_HOOK` | — | 强制 hook 执行（跳过外部上下文检查；后者为历史别名） |
| `MEMORY_HOOK_POLICY_PACK_PATH` | — | Policy-pack JSON 路径（`PolicyRegistryImpl.POLICY_PACK_PATH_ENV`；缺省时用内置兜底策略） |

### 9.2 路径 / CWD 发现

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MEMORY_HOOK_PROJECT_CWD` | — | wrapper 注入的项目 CWD（根发现种子；减少冗余子进程探测） |
| `MEMORY_HOOK_ORIGINAL_CWD` | — | 原始 cwd（guard 项目根探测来源之一） |
| `MEMORY_HOOK_PREFER_EXTERNAL_CWD` | — | 优先采用外部注入的原始 cwd |
| `MEMORY_HOOK_ARTIFACT_ROOT` | `<workspace>/memory/artifacts/memory-hook` | artifact 根覆盖 |
| `MEMORY_HOOK_ERROR_LOG` | `<workspace>/memory/system/errors.log` | 错误日志路径覆盖 |
| `MEMORY_HOOK_GLOBAL_STATE_ROOT` | `~/.memory-core` | Layer 1 全局状态根（project-lifecycle / 完整性密钥） |
| `MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS` | — | 生命周期记录保留天数 |

### 9.3 守卫 / 拒绝列表

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `FACTORY_PROJECT_DIR` / `ZCODE_PROJECT_DIR` | — | 宿主注入的项目根（guard 项目根探测首选） |
| `MEMORY_HOOK_DENY_PROJECT_ROOTS` | — | 拒绝列表（denylist.py） |
| `MEMORY_CORE_BYPASS_DENYLIST` | — | 测试用绕过拒绝列表 |

### 9.4 遥测 / 日志

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `POSTHOG_HOST` | `https://us.posthog.com` | PostHog 域（自动归一化为 us/eu.i.posthog.com ingestion 端点） |
| `POSTHOG_API_KEY` | 内置公开 key（`default_posthog_key.txt`） | 设为空字符串禁用遥测 |
| `MEMORY_HOOK_METRICS_DISABLED` | — | 置 `1` 禁用 metrics 采集 |
| `MEMORY_HOOK_METRICS_PATH` | `<artifact_root>/metrics.jsonl` | metrics 文件路径覆盖 |
| `MEMORY_HOOK_SCHEMA_AUDIT` / `MEMORY_SCHEMA_AUDIT_LOG` | — | Schema 转换审计 |

### 9.5 生命周期 / 宿主

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE` | — | 置 `1` 时 gateway 记录项目生命周期事件 |
| `FACTORY_HOME` | `~/.factory` | Factory 用户配置目录（factory_global_hooks） |
| `CMUX_SURFACE_ID` / `CMUX_WORKSPACE_ID` / `CMUX_HOOK_STATE_FILE` | — | cmux 集成上下文（task_context 字段 / Claude 状态文件路径） |
| `MEMORY_HOST` / `MEMORY_INIT_RUNNING` | — | 宿主标识 / init 重入保护 |

**已移除**：早期文档中的 `WORKBOT_FORCE_HOOK` 语义（保留为兼容别名）、workbot 专属注入变量族随 adapter 删除。

---

*文档基于代码实际阅读整理；行数与文件数为 2026-09-05 `wc -l` / `ls` 实测，对应 v0.45.6（commit `6ac1cdb`）。*
