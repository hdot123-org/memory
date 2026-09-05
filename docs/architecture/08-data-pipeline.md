---
type: "[DOC:DESIGN]"
title: "数据管道与 Sink"
shortname: DES-008
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [data-pipeline,sink,write-route,telemetry]
related: [DES-007, DES-009, DES-010]
---

> 文档编号：DES-008 | 版本：V1.1 | 日期：2026-09-05 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05（v0.45.6）。如需精确接口签名，请参考源码（`memory_core/tools/`）。

# 08-data-pipeline.md

> **📌 2026-09-05 校准备注**（相对 2026-05-14 / v0.4.0 Beta 版快照的变更）：
>
> 1. **Gateway 已拆分（M3）**：`memory_hook_gateway.py` 现为薄门面（re-export 层），实现迁移到 `_gateway_config` / `_gateway_artifacts` / `_gateway_policy` / `_gateway_telemetry` / `_gateway_dispatch` / `_gateway_handlers` 六个单一职责模块；CLI console-script 入口改为 `memory_core.tools.hook_runtime_guard:gateway_main`（SIGALRM 8s / SIGINT → `os._exit(0)` 引导守卫，先于重量级 import 安装）。
> 2. **Artifact Sink 已按日分区**：快照写入 `contexts/{YYYY-MM-DD}/` 日目录，event log 双写 `events/{YYYY-MM-DD}.jsonl`（现行）与 `events.jsonl`（legacy 兼容）；`artifact_refs` 扩为 5 键（snapshot / latest / daily_latest / event_log / legacy_event_log）。
> 3. **遥测本地优先**：hook 热路径仅追加本地 `metrics.jsonl`（微秒级、锁竞争即丢弃）；`session-start` 每小时窗口经 `.offset` 伴车文件批量同步 PostHog（详见 §9）。
> 4. **host 取值收敛**：`--host` choices 从 codex/claude 收敛为 `SUPPORTED_HOSTS = ("factory", "zcode")`（`memory_core/constants.py`）；`--event` 扩为 9 种。
> 5. **v2→v1 转换层仍在**：`memory_hook_schema.py`（424 行）提供 wb-hook-v2 → context-package-v1 → memory-v1 转换，由 `build_context_package_simple()`（MCP server 与懒加载入口消费）调用；artifact 落盘仍是内部 v2 schema + `artifact_refs` 注入。
> 6. **旧版行号引用已失效**：因模块拆分，本文以「模块 + 函数」定位代码，不再引用 2026-05 版的逐行行号。

> **v2→v1 转换层说明**：核心（`build_context_package_core()`）内部使用 v2 schema（`schema_version: "wb-hook-v2"`）组装，包含完整的 system_context、project_context、task_context 三层结构。对外消费契约通过 `memory_hook_schema.convert_to_v1()` 转换为 `context-package-v1`（`build_context_package_simple()` 入口），进一步可经 `convert_to_memory_v1()` 转为 `memory-v1`（project 段仅引用 `memory/kb/projects/{scope}/` canonical 文件）。artifact 落盘路径不经过该转换，快照/event log 中保存的是 v2 全量结构。

## 1 Context Package 生命周期

### 1.1 入口：`gateway_main()` → `main()`

console-script 入口 `memory-hook-gateway = memory_core.tools.hook_runtime_guard:gateway_main`（`pyproject.toml [project.scripts]`）。`hook_runtime_guard.py`（40 行）在导入 gateway 模块**之前**安装信号处理器：

| 信号 | 行为 | 超时 |
|---|---|---|
| `SIGALRM` | `_exit0_handler` → `os._exit(0)` | `_BOOT_SECONDS = 8` 秒（早于 Factory 的 10s 硬超时） |
| `SIGINT` | 同上，干净退出无 traceback | — |

之后导入并调用 `main()`（`_gateway_handlers.py`）。流程如下：

1. `_parse_args()` 解析参数：`--host`（必填，choices = `SUPPORTED_HOSTS` = factory/zcode）、`--event`（必填，9 种：session-start / prompt-submit / stop / notification / pre-tool-use / post-tool-use / subagent-stop / pre-compact / session-end）、`--no-delegate`
2. 从 stdin 读取 raw JSON payload，`_read_payload()` 解析为 dict
3. `_discover_cwd(payload)` 确定 cwd：默认优先 payload.cwd（repo 内时）→ 环境 cwd（repo 内时）→ 环境 cwd（repo 外也接受）→ payload.cwd → `REPO_ROOT` 兜底；`MEMORY_HOOK_PREFER_EXTERNAL_CWD` 设置时直接采用原始 cwd（shell wrapper 注入）
4. `pre-tool-use` 事件先进入 `_handle_pretooluse_guard()`：PreToolUse 守卫（`pretooluse_guard.py` + `_guard_classify.py` / `_guard_patterns.py`）拦截 Write/Edit/MultiEdit/NotebookEdit/Execute，按所有权分类输出 allow（exit 0）/ block（exit 2），处理完直接返回
5. `session-start` 旁路（`_handle_session_start_setup()`）：
   - `_launch_async_health_check()` 后台分离进程执行深度健康检查，结果写 `memory/system/health-report.json`
   - `_update_state_dynamic_fields()` 刷新 `memory/kb/projects/{scope}/STATE.md` 的「当前工作区」动态字段（当前分支 + 最近提交）
   - `_maybe_sync_telemetry(ARTIFACT_ROOT)` 遥测批量同步（§9.3）
   - 自动版本跟随探测：从 infra-core 导入 `probe_version_and_sync()`（`infra_core.engine.version_sync`），regex 读取项目 `memory/system/memory.lock` 的 `memory_version`，与 `CURRENT_MEMORY_VERSION` 不一致时进程内触发单项目同步；注入 `_memory_core_resign_wrapper` 作为同步后增量重签 hook；任何异常不阻塞 hook 主链
6. `prompt-submit` 旁路：`_handle_prompt_submit_logging()` → `_log_prompt_submit()` 实时心跳写入 `memory/log/{date}-sessions.md`（SIGALRM 2s 写超时保护）
7. **快速路径**：`NON_INJECTION_EVENTS`（stop / post-tool-use / subagent-stop / pre-compact / session-end / notification）且 host 受支持时，跳过完整 package 构建——仅记录生命周期（`_record_project_lifecycle_event()`）、发射快速指标（`_emit_fast_path_metrics()`，`fast_path: true`）、写最小事件日志（`_record_event_log_minimal()`），输出 `{"suppressOutput": true}` 并返回 0
8. **完整路径**（注入事件：session-start / prompt-submit / pre-tool-use）：
   - 预记录生命周期 → `ArtifactWriter(CONTEXT_ROOT, ERROR_LOG)` 构造写入器
   - `build_context_package(host, event, payload, lifecycle_record=...)` 构建 package（§1.2）
   - session-start：`_inject_health_alert()` 注入上一次会话的健康告警；`_handle_integrity_check()` 完整性校验，失败时 `status` 置为 `"blocked"` 并追加 `integrity-check-failed` 到 validation_errors
   - `_write_artifacts_and_emit_metrics()`：写工件（§1.4）→ 成功后 `_integrity_sign()` 增量签名 manifest → `emit_metrics()` 发射指标（§9.2）
   - `_compute_exit_code()`：`status != "ok"` 时写 error log 并返回退出码 1
   - `_dispatch_output()` 分派输出：factory/zcode 主机经 `_build_factory_hook_output()` 将 allowed_reads / allowed_writes / validation_errors 渲染为 `hookSpecificOutput.additionalContext`（session-start → SessionStart，prompt-submit → UserPromptSubmit），其余事件成功时输出 `{"suppressOutput": true}`
9. memory-core 源码仓自身：source-repo 检测（`is_memory_core_source_repo()`）命中 readonly 模式时走 `_build_readonly_source_repo_package()`，返回 `package_kind: "source-repo-rules"`、`allowed_writes: {}` 的只读规则包；develop 模式下跳过消费者校验层（§1.2 第 6 步）

### 1.2 `build_context_package()` 构建链

`build_context_package()`（`_gateway_policy.py`）是核心组装编排函数：

1. `_discover_cwd(payload)` 确定 cwd；`lifecycle_record` 为空时补记生命周期
2. `determine_project_scope(cwd)` 确定项目作用域；`_get_gateway_business_policy()` 获取业务策略
3. 组装 **`CoreConfig`** 结构化配置对象（`memory_hook_config.py`）——原 37 个扁平 kwargs 已收敛为单个 dataclass（5 组字段：环境 7 / 路径 7 / 策略 6 / 回调 14 / 接口对象与可选策略 5）
4. `_resolve_core_builder()` 解析 core provider：`MEMORY_HOOK_CORE_PROVIDER` 环境变量（默认 `legacy`），`allow_fallback=True` 自动回退
5. 调用 `provider_builder(config)`（external-core）或 `build_context_package_from_config(config)`（legacy）生成 v2 package
6. 源码仓 develop 模式跳过消费者项目校验：status 强制 "ok"、清空 validation_errors / missing_paths，标记 `system_context.source_repo_skip_validation = True`
7. 在 `system_context` 注入 `core_provider`、`core_provider_requested`、`core_provider_fallback_errors`（条件）、`project_lifecycle`（生命周期记录）
8. provider fallback 发生时，错误追加到 `validation_errors`，status "ok" → "degraded"（源码仓除外）
9. `MEMORY_HOOK_SHADOW_RUN` 设置时执行 shadow provider 对比，结果写入 `system_context.shadow_run`
10. `_apply_artifact_compaction()` 按 adapter 的 `ARTIFACT_COMPACTION` 策略裁剪 package 区段（默认 adapter 配置见 `memory_hook_adapters/default_runtime_profile.py`）
11. 返回 package

另有 `build_context_package_simple(host, event, payload=None, *, adapter=None, schema="context-package-v1")`（同文件）：在 `build_context_package()` 之上做 schema 转换（`convert_to_v1()`，`schema="memory-v1"` 时再经 `convert_legacy_to_memory_v1()`），是 MCP server `load_context` 工具与 `memory_core.tools` 懒加载导出的消费入口。

### 1.3 `build_context_package_core()` 核心组装

`build_context_package_core()`（`memory_hook_core.py`，keyword-only 签名，现约 39 个参数 = 原 37 个 + v0.8.0 新增 `global_kb_root` / `global_kb_enabled`）是纯组装逻辑；等价的 `build_context_package_from_config(config: CoreConfig)` 接受结构化配置，行为完全一致：

1. 检查 required_canonical 文件，按文件名分流：`truth-model.md` / `memory-system.md` / `memory-routing.md` 缺失进 **`warnings`**（missing_canonical_files，警告级），其余缺失进 `missing_paths`（错误级）
2. `validate_project_map_fn()` 收集 project_map_errors
3. `validate_unique_legal_system_contract_fn()` 收集 contract_errors
4. `policy_validate_fn()` 收集 policy_errors（异常时降级为单条错误消息）
5. `governance_frozen_tuple_errors_fn()` 和 `event_contract_blocker_errors_fn()`（仅当 project_scope 在对应 blocker_scopes 中时触发）
6. `git_registration_probe_fn()` 获取 registration_commit_gate，`evaluate_registration_commit_gate()` 评估注册提交门（phase=enforced 且当前事件命中 gate_event 时要求 status=committed-coupled，否则产生 blocker 错误）
7. `get_policy_pack_fn()` 获取 policy_pack（异常时记 policy_errors）
8. `_resolve_project_file()` 解析 project 文件，缺失时进 missing_paths
9. 收集 decisions、lessons、docs_refs、truth_basis
10. `_compute_truth_basis_errors()` 构建 `reads` 列表并校验 truth_basis 覆盖与去重；**v0.8.0+ 全局兜底**：`global_kb_enabled` 时把 `~/.memory/global-kb/` 下全部非 pending 域目录追加进 reads
11. 汇总 blocker_errors（governance + event_contract + registration_gate）
12. `_derive_status()` 确定 status："ok" 或 "degraded"
13. `_derive_project_truth_status()` 确定 project_truth_status
14. 构建 evidence_refs（project_map_refs + core_evidence_refs + governance 文件 + event_log）
15. `_assemble_system_context()` / `_assemble_project_context()` 组装两个子结构（§5 / §6）
16. 返回完整 v2 package dict（顶层键见 §4）

### 1.4 落盘：`ArtifactWriter` → `ArtifactSinkImpl.write()`

完整路径由 `main()` 构造 `ArtifactWriter(CONTEXT_ROOT, ERROR_LOG)`（`memory_hook_impls.py`，包装 `ArtifactSinkImpl`，写失败记 error log 不抛异常），`write()` 委托 `ArtifactSinkImpl.write()`（`memory_hook_impls.py:682-717`）：

1. `ensure_dirs()` 创建 CONTEXT_ROOT 与 `events/` 子目录（`memory_hook_impls.py:678-680`）
2. 生成时间戳 `YYYYMMDDTHHMMSSffffff` 与日期 `YYYY-MM-DD`，创建日目录 `contexts/{day}/`
3. 构建 snapshot 路径：`contexts/{day}/{timestamp}-{host}-{event}.json`，冲突时追加 `-{suffix:02d}`
4. 构建 latest 路径：`contexts/latest-{host}-{event}.json`（跨日覆盖）与 daily_latest 路径：`contexts/{day}/latest-{host}-{event}.json`
5. 在 package 中注入 `artifact_refs` 字段（5 键，见 §2.3）
6. `json.dumps(indent=2)` 写入 snapshot / latest / daily_latest 三份
7. 以 compact JSONL 追加写入 `events/{day}.jsonl`（现行日分区 event log）
8. 同时追加写入 legacy `events.jsonl`（双写，保持旧消费者兼容）
9. 返回 `{"snapshot": ..., "latest": ..., "event_log": ...}`（指向日分区 event log）

写成功后由 `_write_artifacts_and_emit_metrics()` 执行 `_integrity_sign()` 增量签名与 `emit_metrics()` 指标发射。

> 兼容回退：sink 构造失败（RuntimeError）时，`write_artifacts()`（`_gateway_artifacts.py`）提供等价的手动写入回退路径，产物布局与上述一致。

---

## 2 Artifact Sink

### 2.1 写入位置

路径常量定义于 `_gateway_config.py:93-122`，均支持环境变量覆盖：

| 常量 | 路径 | 来源 |
|------|------|------|
| `REPO_ROOT` / `WORKSPACE_ROOT` | `discover_roots()` 动态发现 | `memory_root_discovery.py`（从 seed 路径向上遍历寻找 `memory/system/`；遇到「有 .git 无 memory/system」的 monorepo 哨兵即停止） |
| `ARTIFACT_ROOT` | `{WORKSPACE_ROOT}/memory/artifacts/memory-hook` | 环境变量 `MEMORY_HOOK_ARTIFACT_ROOT` 可覆盖 |
| `CONTEXT_ROOT` | `{ARTIFACT_ROOT}/contexts` | 派生常量 |
| `EVENT_LOG`（legacy） | `{ARTIFACT_ROOT}/events.jsonl` | 派生常量（单文件历史日志，仍双写） |
| 日分区 event log | `{ARTIFACT_ROOT}/events/{YYYY-MM-DD}.jsonl` | `ArtifactSinkImpl.write()` 现行写入目标 |
| `ERROR_LOG` | `{WORKSPACE_ROOT}/memory/system/errors.log` | 环境变量 `MEMORY_HOOK_ERROR_LOG` 可覆盖 |
| `PROJECT_LIFECYCLE_ROOT` | `MEMORY_HOOK_GLOBAL_STATE_ROOT` 环境变量下 `project-lifecycle/`，否则 `{ARTIFACT_ROOT}/project-lifecycle` | Layer 1 主机级生命周期 |

> 注意：`WORKSPACE_ROOT` 不再是「`memory_core/` 源码目录的父目录」的静态推导（2026-05 版语义），而是按消费项目动态发现的项目根；产物随之落在**消费项目**的 `memory/artifacts/memory-hook/` 下。

### 2.2 文件命名规则

Snapshot 文件（`memory_hook_impls.py:684-693`）：
- 格式：`contexts/{YYYY-MM-DD}/{YYYYMMDDTHHMMSSffffff}-{host}-{event}.json`
- 示例：`contexts/2026-09-05/20260905T143025123456-factory-session-start.json`
- 冲突处理：追加 `-{suffix:02d}`，如 `...-01-factory-session-start.json`

Latest 文件（`memory_hook_impls.py:694-695`）：
- `contexts/latest-{host}-{event}.json`：每次写入覆盖，指向最近一次该 host+event 组合
- `contexts/{day}/latest-{host}-{event}.json`：日维度 latest，便于按日回溯

### 2.3 Event Log 格式与 artifact_refs

Event log 是 JSONL 文件，现行按日分区（`memory_hook_impls.py:696, 710-715`）：
- 每行一个完整的 v2 context package JSON（compact 模式，无缩进）
- 双写：`events/{day}.jsonl`（现行）+ `events.jsonl`（legacy）
- 每条记录包含完整 package 内容，包括 sink 注入后的 `artifact_refs` 字段

`artifact_refs`（`memory_hook_impls.py:698-704`）共 5 键：

| 键 | 指向 |
|----|------|
| `snapshot` | `contexts/{day}/{timestamp}-{host}-{event}.json` |
| `latest` | `contexts/latest-{host}-{event}.json` |
| `daily_latest` | `contexts/{day}/latest-{host}-{event}.json` |
| `event_log` | `events/{day}.jsonl` |
| `legacy_event_log` | `events.jsonl` |

**下游消费者**：`hook_event_stats.py`（353 行）按日读取 `events/{date}.jsonl`（回退 `events.jsonl`）与 `contexts/{date}/*.json` 快照聚合 session 统计；`infra-error-patterns`（infra-core）跨项目扫描 `memory/log/*-errors.jsonl`（§9.6）。

---

## 3 Error Sink

### 3.1 错误日志位置

`ERROR_LOG` = `{WORKSPACE_ROOT}/memory/system/errors.log`（`_gateway_config.py:100-104`，环境变量 `MEMORY_HOOK_ERROR_LOG` 可覆盖）。日分区镜像写入 `errors/{YYYY-MM-DD}.log`（与主文件同内容双写，`memory_hook_impls.py:765-772`）。

### 3.2 格式

`ErrorSinkImpl.log()`（`memory_hook_impls.py:720-787`）输出两路并行格式：

结构化行（机器消费，主文件 + 日分区双写）：

```
[{iso_timestamp}] [{component}] [error] {message} | context={json_context}
```

- `iso_timestamp`：`now_iso()` 生成
- `component`：调用方标识，如 `"memory-hook-gateway"`
- `context`：JSON 格式附加上下文（`sort_keys=True`）

可读镜像（人工 triage，best-effort）：
- 路径：`{原文件名去扩展}-readable.log`（主文件与日分区各一份）
- 格式：`[{timestamp}] [ERROR] component={component} {message} | {key=value 串}`
- 开关：`MEMORY_HOOK_READABLE_ERRORS_DISABLED=1` 关闭；写入失败静默跳过，不阻塞结构化输出

### 3.3 触发场景

- **status != "ok"**：missing canonical paths / 校验失败（`_compute_exit_code()`）
- **完整性校验失败**：`_handle_integrity_check()` 记 `memory-hook-integrity` 组件日志
- **delegate preflight 失败 / delegate 命令返回非零**（`_execute_delegate()`）
- **artifact write failed**（`_write_artifacts_and_emit_metrics()`）
- **生命周期记录失败 / 健康检查启动失败**（各旁路的 except 分支，经 `append_error_log()` 走同一 sink）

回退路径：sink 构造失败时 `append_error_log()`（`_gateway_artifacts.py`）直接双写主文件与日分区。

---

## 4 build_context_package 返回值完整结构

`build_context_package_core()` 返回的 dict 包含以下 18 个顶层 key（`memory_hook_core.py` 返回字面量）：

| Key | 类型 | 说明 |
|-----|------|------|
| `schema_version` | `str` | 固定 `"wb-hook-v2"`（内部 v2 版本标识） |
| `generated_at` | `str` | ISO 时间戳 |
| `host` | `str` | `"factory"` 或 `"zcode"`（`SUPPORTED_HOSTS`） |
| `event` | `str` | 9 种事件之一（§1.1） |
| `repo_root` | `str` | 仓库根目录绝对路径 |
| `workspace_root` | `str` | workspace 根目录绝对路径 |
| `cwd` | `str` | 当前工作目录 |
| `project_scope` | `str` | 项目作用域 |
| `status` | `str` | `"ok"` / `"degraded"` / `"blocked"`（blocked 仅由 session-start 完整性校验设置） |
| `missing_paths` | `list[str]` | 缺失的 required canonical 路径（错误级） |
| `warnings` | `list[str]` | 缺失的 canonical 文件名警告级清单（truth-model.md / memory-system.md / memory-routing.md） |
| `validation_errors` | `list[str]` | 所有验证错误的扁平列表 |
| `system_context` | `dict` | 系统级上下文（见 §5） |
| `project_context` | `dict` | 项目级上下文（见 §6） |
| `task_context` | `dict` | 任务级上下文（event / task_ref / session_id / surface_id / workspace_id / payload_keys） |
| `allowed_reads` | `list[str]` | 允许读取的文件路径列表（§7.1） |
| `allowed_writes` | `dict` | 写入目标映射（§7.2） |
| `evidence_refs` | `list[str]` | 证据引用路径列表 |

`build_context_package()`（`_gateway_policy.py`）在 core 返回后额外注入（均位于 `system_context`）：
- `core_provider`：实际使用的 provider 名称
- `core_provider_requested`：请求的 provider 名称
- `core_provider_fallback_errors`：fallback 错误列表（条件）
- `project_lifecycle`：本次事件的生命周期记录（条件）
- `shadow_run`：shadow 对比结果（当 `MEMORY_HOOK_SHADOW_RUN` 设置时）
- `source_repo_skip_validation = True`（源码仓 develop 模式，条件）

`ArtifactSinkImpl.write()` 落盘前额外注入：
- `artifact_refs`：`{"snapshot": str, "latest": str, "daily_latest": str, "event_log": str, "legacy_event_log": str}`（§2.3）

`main()` 在 session-start 时额外注入：
- `system_context.previous_health_alert`：上一次会话健康检查 degraded 时注入（status / errors 前 5 条 / note）

---

## 5 system_context 子结构字段

`system_context` 由 `_assemble_system_context()`（`memory_hook_core.py`）构建，25 个基础字段：

| 字段 | 类型 | 来源 |
|------|------|------|
| `boot_entry` | `str` | `{workspace_root}/INDEX.md` |
| `state_entry` | `str` | `{workspace_root}/NOW.md` |
| `state_summary` | `list[str]` | NOW.md 摘录 |
| `project_map_refs` | `list[str]` | project map 文件路径列表 |
| `project_map_validation` | `str` | `"pass"` 或 `"fail"` |
| `legality_contract_validation` | `str` | `"pass"` 或 `"fail"` |
| `legality_source_policy` | `str` | 如 `"active-legal-map-only"` |
| `registration_commit_policy` | `str` | 注册提交策略描述 |
| `registration_commit_gate` | `dict` | git registration probe 结果（含 phase / enforced / triggered_on_current_event / enforcement_result） |
| `registration_commit_enforced` | `bool` | 是否强制执行 |
| `registration_commit_enforcement_result` | `str` | `"passed"` / `"failed"` / `"not-enforced"` / `"awaiting-gate-event"` |
| `global_canonical` | `list[str]` | 全局 canonical 文件路径列表 |
| `truth_basis_policy` | `str` | truth basis 策略描述 |
| `truth_basis_validation` | `str` | `"pass"` / `"fail"` / `"unknown"` |
| `truth_basis_refs` | `list[str]` | truth basis 引用路径 |
| `truth_basis_errors` | `list[str]` | truth basis 验证错误 |
| `governance_frozen_tuple_validation` | `str` | `"pass"` 或 `"fail"` |
| `governance_frozen_tuple_errors` | `list[str]` | governance frozen tuple 错误 |
| `event_contract_alignment_validation` | `str` | `"pass"` 或 `"fail"` |
| `event_contract_alignment_errors` | `list[str]` | event contract 对齐错误 |
| `decision_refs` | `list[str]` | 决策文档引用 |
| `lesson_refs` | `list[str]` | 经验教训文档引用 |
| `docs_refs` | `list[str]` | 文档引用 |
| `hook_contract` | `str` | hook contract 文件路径 |
| `policy_pack` | `dict` | 策略包内容 |

gateway 编排层注入的条件字段见 §4（core_provider 系列 / project_lifecycle / shadow_run / source_repo_skip_validation / previous_health_alert）。

---

## 6 project_context 子结构字段

`project_context` 由 `_assemble_project_context()`（`memory_hook_core.py`）构建，9 个字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `scope` | `str` | 项目作用域 |
| `canonical` | `str` | 项目 canonical 文件路径（未注册 scope 回退 `{workspace_root}/projects/{scope}/PROJECT.md`） |
| `truth_basis_canonical` | `str` | truth basis 项目引用路径 |
| `truth_status` | `str` | `"truth-ready"` 或 `"truth-incomplete"` |
| `runtime_root` | `str` | 项目运行时根目录 |
| `source_refs` | `list[str]` | source 引用路径 |
| `authority_refs` | `list[str]` | authority 引用路径 |
| `evidence_refs` | `list[str]` | evidence 引用路径 |
| `conflict_status` | `list[str]` | 冲突状态列表 |

---

## 7 allowed_reads / allowed_writes 的结构

### 7.1 allowed_reads

`allowed_reads` 是 `list[str]`（`_compute_truth_basis_errors()`，`memory_hook_core.py`），包含：

1. `{workspace_root}/NOW.md`
2. 所有 `project_map_refs`
3. `{workspace_root}/memory/kb/INDEX.md`
4. `{workspace_root}/memory/docs/INDEX.md`
5. 所有 `truth_basis_refs`
6. 所有 `decisions`
7. 所有 `lessons`
8. 所有 `docs_refs`
9. **v0.8.0+ 全局兜底**：`global_kb_enabled` 且 `global_kb_root` 存在时，`~/.memory/global-kb/` 下全部非 `pending` 域目录（operations / engineering / collaboration）

代码校验 `truth_basis_refs` 是否全部被 `allowed_reads` 覆盖，未覆盖则追加错误到 `truth_basis_errors`；同时校验 decision/lesson/docs refs 与 truth_basis_refs 不重叠。

### 7.2 allowed_writes

`allowed_writes` 是 `dict[str, Any]`，由 `write_targets_fn()` 返回（gateway 接线为 `_gateway_policy.write_targets()`：优先走 policy 解析，异常回退 `_apply_hook_runtime_write_targets(_get_write_targets_dict(WORKSPACE_ROOT))`）。

默认映射（`_rule_helpers._get_write_targets_dict()`，单一事实源）：

| Key | 值 |
|-----|-----|
| `fact` | `{workspace_root}/memory/log/{today}.md` |
| `global_canonical` | `{workspace_root}/memory/kb/global` |
| `project_canonical` | `{workspace_root}/memory/kb/projects` |
| `decision` | `{workspace_root}/memory/kb/decisions` |
| `lesson` | `{workspace_root}/memory/kb/lessons` |
| `docs` | `{workspace_root}/memory/docs` |
| `action` | `{workspace_root}/memory/inbox.md` |
| `project_runtime` | `{workspace_root}/projects` |
| `artifacts` | `{workspace_root}/memory/artifacts` |
| `system_error` | `{workspace_root}/memory/system/errors.log` |
| `invalid_memory` | `{workspace_root}/memory/archive/invalid` |
| `kb_policy` | `{"mode": "read-first-CRUD", "overwrite_allowed": false, "conflict_strategy": "preserve-and-escalate"}` |

> 相对 2026-05 版：`artifacts` 从 `{workspace_root}/artifacts` 移到 `{workspace_root}/memory/artifacts`（与 ARTIFACT_ROOT 新布局对齐）。此外 `_apply_hook_runtime_write_targets()` 会在运行时追加 hook 运行时目标（如 `hook_lifecycle` → `PROJECT_LIFECYCLE_ROOT`、`hook_global_state_root` → Layer 1 全局状态根），供 hook 自身写生命周期数据。

---

## 8 validation_errors / warnings 收集链

`validation_errors` 是扁平的 `list[str]`，在 `build_context_package_core()` 返回字面量中汇总：

```python
"validation_errors": [
    *project_map_errors,     # validate_project_map_fn()
    *contract_errors,        # validate_unique_legal_system_contract_fn()
    *policy_errors,          # policy_validate_fn() + policy-pack 解析失败
    *truth_basis_errors,     # truth_basis 校验 + reads 覆盖校验
    *blocker_errors,         # governance + event_contract + registration_gate
]
```

### 8.1 各来源

**project_map_errors**：`validate_project_map_files()`，校验 project map 文件的 Truth Basis 完整性

**contract_errors**：`validate_unique_legal_system_contract()`，校验 legal system contract 唯一性

**policy_errors**：
- `policy_validate_fn(context)`（context 含 host / event / cwd / project_scope），异常时追加 `"policy validation failed: {exc}"`
- policy pack 解析失败时追加 `"policy-pack resolution failed: {exc}"`

**truth_basis_errors**：
- truth_basis 自带 `errors` 字段
- 额外校验：allowed_reads 覆盖 / decision / lesson / docs refs 与 truth_basis_refs 重叠

**blocker_errors**：
- `governance_tuple_errors`：仅当 `project_scope` 在 `governance_blocker_scopes` 中时触发
- `event_contract_errors`：仅当 `project_scope` 在 `event_contract_blocker_scopes` 中时触发
- `registration_gate_errors`：phase=enforced 且当前事件为 gate_event（默认 stop）时，status ≠ committed-coupled 即失败

**warnings（新增，非 errors）**：required_canonical 中文件名为 `truth-model.md` / `memory-system.md` / `memory-routing.md` 的缺失项归入顶层 `warnings`（missing_canonical_files），不再计入 missing_paths 错误。

### 8.2 provider fallback 错误

`build_context_package()` 中：provider fallback 产生的错误追加到 `validation_errors`；如果原 status 为 "ok"，则改为 "degraded"（源码仓 develop 模式豁免）。

### 8.3 status 判定逻辑

```
status = "ok" if (not missing_paths
                  and not project_map_errors
                  and not contract_errors
                  and not policy_errors
                  and not truth_basis_errors
                  and not blocker_errors)
         else "degraded"
```

（`_derive_status()`，`memory_hook_core.py`）。另有两种 status 变更不在 core：源码仓 develop 模式强制 "ok"（§1.2 第 6 步）；session-start 完整性校验失败置 `"blocked"`（§1.1 第 8 步）。

---

## 9 遥测管道（本地优先）

### 9.1 数据流总览

```
hook 事件（注入/非注入/pre-tool-use）
  │
  ├─ 热路径：append metrics.jsonl（本地 JSONL，微秒级，零网络）
  │    memory/artifacts/memory-hook/metrics.jsonl
  │
  └─ session-start 批量同步（每小时窗口）：
       1. 检查 .last_sync_success（< 3600s 跳过）/ .last_sync_attempt（< 300s 退避）
       2. socket 探测 PostHog ingestion 主机连通性（2s 超时）
       3. 读 .offset 伴车，增量读取未投递记录
       4. telemetry_bridge.batch_capture 分批（BATCH_SIZE=500）直连 /batch/ API
       5. 成功：截断 metrics.jsonl + offset 归零 + 更新 .last_sync_success
          失败：仅更新 .last_sync_attempt（.offset 不动，下次续传）
```

### 9.2 本地 metrics.jsonl

写入方：`memory_hook_metrics.py`（138 行）`emit_metrics()` / `_emit_fast_path_metrics()`。

- 路径：`{ARTIFACT_ROOT}/metrics.jsonl`（`MEMORY_HOOK_METRICS_PATH` 可覆盖）；禁用开关 `MEMORY_HOOK_METRICS_DISABLED=1`
- 完整路径记录字段：timestamp / host / event / status / context_package_size_bytes / validation_error_count / missing_paths_count / degraded / core_provider / package_kind / duration_ms
- 快速路径记录：精简字段 + `fast_path: true`
- 崩溃兜底：`_gateway_excepthook` 将未捕获异常写为 `event: "hook_error"` 记录
- **锁竞争丢弃语义**：`append_metrics_record()` 使用 `try_exclusive_lock`（`LOCK_EX | LOCK_NB`），文件被并发持锁时**直接丢弃该记录**而非阻塞——遥测显式容忍丢失，避免高事件量下的 hook 进程风暴（这是设计决策，不是缺陷）

### 9.3 `_maybe_sync_telemetry()` 同步机制

实现于 `_gateway_telemetry.py`（483 行），仅由 session-start 事件调用：

| 机制 | 值 | 说明 |
|------|-----|------|
| 成功窗口 | 3600s | `.last_sync_success` 时间戳，窗口内跳过 |
| 失败退避 | 300s | `.last_sync_attempt` 时间戳，窗口内跳过 |
| 连通探测 | 2s | `socket.create_connection((hostname, 443), timeout=2)`；host 经 `_normalize_posthog_host()` 归一（us/eu → `*.i.posthog.com` ingestion 域） |
| 增量游标 | `.offset` 伴车文件 | 记录已同步的行号，单句柄排他锁写入（truncate + write + fsync） |
| 批大小 | `BATCH_SIZE = 500` | 分批调用 `telemetry_bridge.batch_capture()` |
| 周期锁 | `.sync_cycle.lock` | `flock(LOCK_EX | LOCK_NB)` 串行化整个「读取→发送→截断」周期，持锁失败即本轮跳过 |
| 状态文件 | `.sync_status.json` | last_success_ts / last_failure_ts / failure_count / pending_count，单句柄锁内原子读改写 |
| 截断 | `_compact_metrics_jsonl()` | 成功后在同一锁持有期内重写 metrics.jsonl 仅保留未同步行，offset 归零 |

发送侧 `telemetry_bridge.py`（423 行）`batch_capture()`：
- 绕过 PostHog SDK，`urllib.request` 直连 `{ingestion_host}/batch/`，**timeout=3s、max_retries=0**（遥测必须不让 hook 超过 Factory ~10s 预算；旧版 15s×2 重试曾导致 SessionEnd 超时，已移除）
- 每条 batch item 补齐 `$geoip_disable` / `$is_server` / 顶层 `timestamp` / `uuid`（对齐 SDK wire format，缺失会触发 400）
- 公共属性注入 `memory_core_version`（`CURRENT_MEMORY_VERSION`）与 `host`
- `distinct_id` = project_id（`project_lifecycle.build_project_lifecycle_record()` 解析；失败回退目录名确定性哈希）
- 内部失败经 `_capture_error()` 发 `memory.error` 事件（直接 capture，避免递归）

### 9.4 数据脱敏

`telemetry_bridge` 对出网属性执行两级清洗（`_sanitize_value()`，顺序关键）：

1. **共享脱敏 `_redaction.py`**：`redact()` 覆盖 API token（`sk-` / `sk-ant-` / `ghp_` / `AKIA` / `lin_api_` / `glpat-`）、JWT 类 token、认证头（`Authorization: Bearer/Basic`、裸 `Bearer`）、密码/密钥参数、私有 IP（192.168.x.x / 10.x.x.x / 172.16-31.x.x）、用户 home 路径
2. **路径 basename 降级**：键名含 path / file / cwd / dir / root 片段的字符串值，绝对路径替换为 basename（先脱敏后降级，保证路径中嵌密的密钥也被捕获）

四个日志/指标消费者（`log_utils` / gateway / `error_logger` / `telemetry_bridge`）统一委托该共享模块。

### 9.5 SessionEnd 日志链与双预算扫描

- `session_end_logger.py`（696 行）：SessionEnd hook 主体，`TIMEOUT_SECONDS = 2` 整体超时；`_extract_session_info_streaming()` 为确定性双预算扫描（`session_end_logger.py:88-98`）：

| 参数 | 值 | 含义 |
|------|-----|------|
| `TIME_BUDGET` | 1.8s | 单次扫描时间上限（留 0.2s 余量） |
| `BYTE_BUDGET` | 8 MB | 单次扫描字节上限 |
| `CHUNK_SIZE` | 64 KB | 每次读取块大小 |
| `MAX_LINE` | 1 MB | 超过此长度的行直接跳过 |

  达到任一预算立即停止并写入 `truncated: true` 标记；内存占用 O(1)。产出去向：A 层 `memory/log/{date}-sessions.md`（session 记录）。
- `daily_summary_generator.py`（653 行）：读取 A 层 sessions 日志，聚合生成 B 层数据报告 `memory/log/{date}.md`（token 统计、模型、时长、工具调用、用户/助手摘录）。
- 错误兜底：session_end_logger 内部失败经 `error_logger.write_error_log()`（§9.6）落盘。

### 9.6 error_logger 与错误模式检测

- `error_logger.py`（234 行）`write_error_log()`：写入 `memory/log/{YYYY-MM-DD}-errors.jsonl`，每行 `{ts, type, script, project, ctx, msg}`；msg 超 500 字符截断；ctx/msg 经共享脱敏递归清洗；自动检测调用方脚本名；写入成功后对文件做增量完整性签名（`_try_sign_file`）。
- 跨项目错误模式检测（指纹归一化 + 阈值标记 `threshold_met`）的执行体自 M5 起在 **infra-core**（CLI 入口 `infra-error-patterns`），本仓不再持有引擎副本；其扫描输入即上述 `*-errors.jsonl` 文件。

---

## 10 cmux_hook_state.py 的 hook state 记录机制

### 10.1 状态文件位置

`default_hook_state_path()`（`cmux_hook_state.py`，184 行）：
- 路径：`{project_dir}/memory/artifacts/cmux-runtime/hook-state.json`（单一固定路径；2026-05 版描述的 `.cmux-runtime` 回退路径**已移除**）

### 10.2 状态文件结构

hook-state.json 的顶层结构：

```json
{
    "runtime": "cmux",
    "updated_at": "2026-09-05T14:30:25+08:00",
    "surfaces": {
        "{surface_ref}": { ... }
    }
}
```

### 10.3 surface 状态结构

每个 surface 的状态字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `workspace_ref` | `str` | workspace 引用 |
| `surface_ref` | `str` | surface 引用 |
| `session_start_count` | `int` | session-start 事件计数 |
| `prompt_submit_count` | `int` | prompt-submit 事件计数 |
| `stop_count` | `int` | stop 事件计数 |
| `notification_count` | `int` | notification 事件计数 |
| `last_event` | `str` | 最近一次事件名 |
| `last_event_at` | `str` | 最近一次事件时间 |
| `last_session_id` | `str` | 最近一次 session ID |
| `last_cwd` | `str` | 最近一次 cwd |

### 10.4 record_hook_event() 流程

`record_hook_event()`：

1. 获取文件级排他锁 `_exclusive_hook_state_lock()`（`fcntl.flock(LOCK_EX)`，锁文件 `{hook-state.json}.lock`）
2. 加载现有状态 `load_hook_state()`，文件不存在或解析失败时返回 base payload
3. 获取或创建对应 `surface_ref` 的 surface_state
4. 更新 `workspace_ref`、`surface_ref`、`last_event`、`last_event_at`、`last_session_id`、`last_cwd`
5. 根据 `event_name` 递增对应计数器（session-start / prompt-submit / stop / notification）
6. 更新顶层 `updated_at`
7. 原子写入 `_write_hook_state_unlocked()`：临时文件 → 写入 → `fsync` → `Path.replace()` 原子替换 → `load_hook_state_strict()` 读回验证
8. 释放锁，返回更新后的 surface_state

### 10.5 并发安全与调用方

- 锁文件自动创建（`open("a+")`），finally 块确保 `LOCK_UN` 释放
- 模块经 `_file_utils` 复用 `exclusive_lock` / `now_iso` 工具
- **调用方现状（2026-09-05 实测）**：当前 gateway 主链（host = factory/zcode）不触发该状态文件；`record_hook_event` / `default_hook_state_path` 仅作为 `_gateway_config.py` 的 re-export 兼容面保留，仓库内无活跃调用方。现行 HostDelegate 实现为 `FactoryDelegate`（中性空 JSON 直通）与 `NoopHostDelegate`（`resolve_host_delegate()` 解析，factory/zcode 均支持）；2026-05 版描述的 `ClaudeDelegate`/`CodexDelegate` 已移除，`_execute_delegate()` 中的 codex/claude 分支为遗留死代码（CLI choices 已不含这两个 host）。
