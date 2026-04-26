---
type: "[DOC:DESIGN]"
title: "数据管道与 Sink"
shortname: DES-008
status: 草稿中
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [data-pipeline,sink,write-route]
related: [DES-007, DES-009, DES-010]
---

> 文档编号：DES-008 | 版本：V1.0 | 日期：2026-04-26 | 维护人：codex

# 08-data-pipeline.md

## 1 Context Package 生命周期

### 1.1 入口：`main()` → `build_context_package()`

`main()` 函数（[memory_hook_gateway.py:908](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:908)）是 CLI 入口。流程如下：

1. 解析 `--host`（codex/claude）、`--event`（session-start/prompt-submit/stop/notification）、`--no-delegate` 参数（line 909-911）
2. 从 stdin 读取 raw JSON payload，通过 `read_payload()` 解析为 dict（line 910-911）
3. 通过 `discover_cwd(payload)` 确定 cwd：优先 payload.cwd，回退 PWD，最终 REPO_ROOT（line 912）
4. 检查 `should_noop_for_external_context()`：如果 cwd 不在 repo 内且未设置 `MEMORY_HOOK_FORCE`/`WORKBOT_FORCE_HOOK`，则走 delegate noop 并返回（line 914-915）
5. 调用 `build_context_package(host, event, payload)` 构建 package（line 917）
6. 调用 `write_artifacts(package)` 落盘（line 918）
7. 如果 `package["status"] != "ok"`，写入 error log 并返回退出码 1（line 920-937）
8. 如果 `--no-delegate`，直接输出 JSON 到 stdout 并返回 0（line 939-941）
9. 否则通过 `delegate_codex()` 或 `delegate_claude()` 将事件委派给 cmux 子进程（line 944）
10. 委托失败时记录 error log（line 954-966），透写 stdout/stderr（line 968-976）

### 1.2 `build_context_package()` 构建链

`build_context_package()`（[memory_hook_gateway.py:748](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:748)）是核心组装函数：

1. 确定 cwd 和 project_scope（line 749-750）
2. 获取 business_policy（line 751）
3. 组装 `core_kwargs` dict，包含 host、event、payload、路径、策略函数等全部依赖（line 752-786）
4. 通过 `_resolve_core_builder()` 解析 core provider（legacy 或 external-core），支持 fallback（line 787-788）
5. 调用 `provider_builder(**core_kwargs)` 即 `build_context_package_core()` 生成原始 package（line 789）
6. 在 `system_context` 中注入 `core_provider`、`core_provider_requested`、`core_provider_fallback_errors`（line 790-795）
7. 如果 provider fallback 发生，将错误加入 `validation_errors`，并将 status 改为 "degraded"（line 797-802）
8. 如果设置了 `MEMORY_HOOK_SHADOW_RUN`，执行 shadow provider 对比（line 804-824）
9. 调用 `_apply_artifact_compaction()` 根据 adapter 策略裁剪字段（line 826）
10. 返回 package（line 827）

### 1.3 `build_context_package_core()` 核心组装

`build_context_package_core()`（[memory_hook_core.py:69](/Users/busiji/memory/workspace/tools/memory_hook_core.py:69)）是纯组装逻辑：

1. 检查 required_canonical 文件是否存在，收集 `missing_paths`（line 114）
2. 调用 `validate_project_map_fn()` 收集 project_map_errors（line 115）
3. 调用 `validate_unique_legal_system_contract_fn()` 收集 contract_errors（line 116）
4. 调用 `policy_validate_fn()` 收集 policy_errors（line 118-126）
5. 调用 `governance_frozen_tuple_errors_fn()` 和 `event_contract_blocker_errors_fn()`（仅当 project_scope 在对应 blocker_scopes 中时）（line 128-131）
6. 调用 `git_registration_probe_fn()` 获取 registration_commit_gate（line 132）
7. 调用 `get_policy_pack_fn()` 获取 policy_pack（line 134-137）
8. 调用 `evaluate_registration_commit_gate()` 评估注册提交门（line 139-141）
9. 查找 project_file（从 project_canonical 映射），找不到则加入 policy_errors（line 143-147）
10. 收集 decisions、lessons、docs_refs、truth_basis（line 149-152）
11. 构建 `reads` 列表（allowed_reads），并校验 truth_basis 覆盖和去重（line 154-182）
12. 汇总所有 blocker_errors（line 184）
13. 根据错误集确定 status："ok" 或 "degraded"（line 185-194）
14. 确定 project_truth_status（line 195）
15. 构建 evidence_refs（line 197-202）
16. 返回完整 package dict（line 204-271）

### 1.4 落盘：`write_artifacts()` → `ArtifactSinkImpl.write()`

`write_artifacts()`（[memory_hook_gateway.py:857](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:857)）：

1. 调用 `_get_artifact_sink().write(package)`（line 858）
2. 如果 sink 抛出 RuntimeError，走 fallback 路径手动写入（line 860-868）

`ArtifactSinkImpl.write()`（[memory_hook_impls.py:1000](/Users/busiji/memory/workspace/tools/memory_hook_impls.py:1000)）：

1. `ensure_dirs()` 创建 context_root 目录（line 1001）
2. 生成时间戳 `YYYYMMDDTHHMMSSffffff`（line 1002）
3. 构建 snapshot 路径：`{timestamp}-{host}-{event}.json`，冲突时追加 `-{suffix:02d}`（line 1003-1007）
4. 构建 latest 路径：`latest-{host}-{event}.json`（line 1008）
5. 在 package 中注入 `artifact_refs` 字段（line 1010-1014）
6. JSON 格式化写入 snapshot 文件（line 1015-1016）
7. JSON 格式化写入 latest 文件（line 1017）
8. 以 JSONL 追加模式写入 event_log（line 1019-1020）
9. 返回 `{"snapshot": ..., "latest": ...}`（line 1022）

---

## 2 Artifact Sink

### 2.1 写入位置

| 常量 | 路径 | 来源 |
|------|------|------|
| `ARTIFACT_ROOT` | `{WORKSPACE_ROOT}/artifacts/memory-hook` | [memory_hook_gateway.py:19](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:19) |
| `CONTEXT_ROOT` | `{ARTIFACT_ROOT}/contexts` | [memory_hook_gateway.py:20](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:20) |
| `EVENT_LOG` | `{ARTIFACT_ROOT}/events.jsonl` | [memory_hook_gateway.py:21](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:21) |

`WORKSPACE_ROOT` = `SCRIPT_PATH.parents[1]`，即 `workspace/tools/` 的父目录 = `workspace/`（line 17）。

### 2.2 文件命名规则

Snapshot 文件（[memory_hook_impls.py:1003-1007](/Users/busiji/memory/workspace/tools/memory_hook_impls.py:1003)）：
- 格式：`{timestamp}-{host}-{event}.json`
- 示例：`20260426T143025123456-codex-session-start.json`
- 冲突处理：追加 `-{suffix:02d}`，如 `20260426T143025123456-01-codex-session-start.json`

Latest 文件（[memory_hook_impls.py:1008](/Users/busiji/memory/workspace/tools/memory_hook_impls.py:1008)）：
- 格式：`latest-{host}-{event}.json`
- 每次写入覆盖，始终指向最近一次该 host+event 组合的 snapshot

### 2.3 Event Log 格式

Event log 是 JSONL 文件（[memory_hook_impls.py:1019-1020](/Users/busiji/memory/workspace/tools/memory_hook_impls.py:1019)）：
- 每行一个完整的 context package JSON（compact 模式，无缩进）
- 追加模式写入
- 每条记录包含完整的 package 内容，包括注入后的 `artifact_refs` 字段

---

## 3 Error Sink

### 3.1 错误日志位置

`ERROR_LOG` = `{WORKSPACE_ROOT}/memory/system/errors.log`（[memory_hook_gateway.py:22](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:22)）

### 3.2 格式

`ErrorSinkImpl.log()`（[memory_hook_impls.py:1036-1040](/Users/busiji/memory/workspace/tools/memory_hook_impls.py:1036)）：

```
[{iso_timestamp}] [{component}] [error] {message} | context={json_context}
```

- `iso_timestamp`：`datetime.now().astimezone().isoformat(timespec="seconds")`（line 1034）
- `component`：调用方标识，如 `"memory-hook-gateway"`
- `message`：错误描述
- `context`：JSON 格式的附加上下文（`sort_keys=True`）

### 3.3 触发场景

在 `main()` 中（[memory_hook_gateway.py:920-966](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:920)）：

1. **status != "ok"**：missing canonical paths 或 project-map validation failed（line 920-930）
2. **delegate preflight 失败**：RuntimeError 捕获（line 945-951）
3. **delegate 命令返回非零**：returncode != 0（line 954-966）

---

## 4 build_context_package 返回值完整结构

`build_context_package_core()` 返回的 dict 包含以下顶层 key（[memory_hook_core.py:204-271](/Users/busiji/memory/workspace/tools/memory_hook_core.py:204)）：

| Key | 类型 | 说明 |
|-----|------|------|
| `schema_version` | `str` | 固定值 `"wb-hook-v2"` |
| `generated_at` | `str` | ISO 时间戳 |
| `host` | `str` | `"codex"` 或 `"claude"` |
| `event` | `str` | `"session-start"` / `"prompt-submit"` / `"stop"` / `"notification"` |
| `repo_root` | `str` | 仓库根目录绝对路径 |
| `workspace_root` | `str` | workspace 根目录绝对路径 |
| `cwd` | `str` | 当前工作目录 |
| `project_scope` | `str` | 项目作用域，如 `"workbot"`、`"AEdu"`、`"platform-capabilities"` |
| `status` | `str` | `"ok"` 或 `"degraded"` |
| `missing_paths` | `list[str]` | 缺失的 required canonical 文件路径列表 |
| `validation_errors` | `list[str]` | 所有验证错误的扁平列表 |
| `system_context` | `dict` | 系统级上下文（见 §5） |
| `project_context` | `dict` | 项目级上下文（见 §6） |
| `task_context` | `dict` | 任务级上下文 |
| `allowed_reads` | `list[str]` | 允许读取的文件路径列表 |
| `allowed_writes` | `dict` | 写入目标映射（见 §7） |
| `evidence_refs` | `list[str]` | 证据引用路径列表 |

`build_context_package()` 在 core 返回后额外注入：
- `system_context.core_provider`：实际使用的 provider 名称（[line 791](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:791)）
- `system_context.core_provider_requested`：请求的 provider 名称（line 792）
- `system_context.core_provider_fallback_errors`：fallback 错误列表（line 793-795）
- `system_context.shadow_run`：shadow 对比结果（当 `MEMORY_HOOK_SHADOW_RUN` 设置时）（line 820-824）

`write_artifacts()` 通过 `ArtifactSinkImpl.write()` 额外注入：
- `artifact_refs`：`{"snapshot": str, "latest": str, "event_log": str}`（[memory_hook_impls.py:1010-1014](/Users/busiji/memory/workspace/tools/memory_hook_impls.py:1010)）

---

## 5 system_context 子结构字段

`system_context` 在 [memory_hook_core.py:222-248](/Users/busiji/memory/workspace/tools/memory_hook_core.py:222) 构建：

| 字段 | 类型 | 来源 |
|------|------|------|
| `boot_entry` | `str` | `{workspace_root}/INDEX.md` |
| `state_entry` | `str` | `{workspace_root}/NOW.md` |
| `state_summary` | `list[str]` | NOW.md 前 12 行非空内容 |
| `project_map_refs` | `list[str]` | project map 文件路径列表 |
| `project_map_validation` | `str` | `"pass"` 或 `"fail"` |
| `legality_contract_validation` | `str` | `"pass"` 或 `"fail"` |
| `legality_source_policy` | `str` | 如 `"active-legal-map-only"` |
| `registration_commit_policy` | `str` | 如 `"required-after-absorption-complete"` |
| `registration_commit_gate` | `dict` | git registration probe 结果 |
| `registration_commit_enforced` | `bool` | 是否强制执行 |
| `registration_commit_enforcement_result` | `str` | `"passed"` / `"failed"` / `"not-enforced"` / `"awaiting-gate-event"` |
| `global_canonical` | `list[str]` | 全局 canonical 文件路径列表 |
| `truth_basis_policy` | `str` | truth basis 策略描述 |
| `truth_basis_validation` | `str` | `"pass"` 或 `"fail"` |
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

`build_context_package()` 额外注入（[memory_hook_gateway.py:790-795](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:790)）：
- `core_provider`：实际 provider 名称
- `core_provider_requested`：请求的 provider 名称
- `core_provider_fallback_errors`：fallback 错误列表
- `shadow_run`（可选）：shadow 对比结果

---

## 6 project_context 子结构字段

`project_context` 在 [memory_hook_core.py:249-259](/Users/busiji/memory/workspace/tools/memory_hook_core.py:249) 构建：

| 字段 | 类型 | 说明 |
|------|------|------|
| `scope` | `str` | 项目作用域 |
| `canonical` | `str` | 项目 canonical 文件路径 |
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

`allowed_reads` 是 `list[str]`（[memory_hook_core.py:154-162](/Users/busiji/memory/workspace/tools/memory_hook_core.py:154)），包含：

1. `{workspace_root}/NOW.md`
2. 所有 `project_map_refs`
3. `{workspace_root}/memory/kb/INDEX.md`
4. `{workspace_root}/memory/docs/INDEX.md`
5. 所有 `truth_basis_refs`
6. 所有 `decisions`
7. 所有 `lessons`
8. 所有 `docs_refs`

代码在 line 163-166 校验 `truth_basis_refs` 是否全部被 `allowed_reads` 覆盖，未覆盖则追加错误到 `truth_basis_errors`。

### 7.2 allowed_writes

`allowed_writes` 是 `dict[str, Any]`，由 `write_targets_fn()` 返回（[memory_hook_core.py:269](/Users/busiji/memory/workspace/tools/memory_hook_core.py:269)）。

默认实现 `WriteTargetPolicyImpl`（[memory_hook_impls.py:392-417](/Users/busiji/memory/workspace/tools/memory_hook_impls.py:392)）返回：

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
| `artifacts` | `{workspace_root}/artifacts` |
| `system_error` | `{workspace_root}/memory/system/errors.log` |
| `invalid_memory` | `{workspace_root}/memory/archive/invalid` |
| `kb_policy` | `{"mode": "read-first-CRUD", "overwrite_allowed": false, "conflict_strategy": "preserve-and-escalate"}` |

---

## 8 validation_errors / warnings 收集链

`validation_errors` 是扁平的 `list[str]`，在 [memory_hook_core.py:215-221](/Users/busiji/memory/workspace/tools/memory_hook_core.py:215) 汇总：

```python
"validation_errors": [
    *project_map_errors,     # validate_project_map_fn()
    *contract_errors,        # validate_unique_legal_system_contract_fn()
    *policy_errors,          # policy_validate_fn()
    *truth_basis_errors,     # truth_basis 校验 + reads 覆盖校验
    *blocker_errors,         # governance + event_contract + registration_gate
]
```

### 8.1 各来源

**project_map_errors**（line 115）：
- 来自 `validate_project_map_files()`，校验 project map 文件的 Truth Basis 完整性

**contract_errors**（line 116）：
- 来自 `validate_unique_legal_system_contract()`，校验 legal system contract 唯一性

**policy_errors**（line 118-126）：
- 来自 `policy_validate_fn(context)`，context 包含 host、event、cwd、project_scope
- 异常时追加 `"policy validation failed: {exc}"`

**truth_basis_errors**（line 152, 163-182）：
- 来自 `truth_basis_for_scope()` 的 `errors` 字段
- 额外校验：
  - `allowed_reads` 未覆盖所有 truth_basis_refs
  - decision refs 与 truth_basis_refs 重叠
  - lesson refs 与 truth_basis_refs 重叠
  - docs refs 与 truth_basis_refs 重叠

**blocker_errors**（line 184）：
- `governance_tuple_errors`：仅当 `project_scope` 在 `governance_blocker_scopes` 中时触发（默认 AEdu）
- `event_contract_errors`：仅当 `project_scope` 在 `event_contract_blocker_scopes` 中时触发（默认 AEdu）
- `registration_gate_errors`：来自 `evaluate_registration_commit_gate()`，当 phase=enforced 且 status≠committed-coupled 时触发

### 8.2 provider fallback 错误

在 [memory_hook_gateway.py:797-802](/Users/busiji/memory/workspace/tools/memory_hook_gateway.py:797) 中：
- provider fallback 产生的错误追加到 `validation_errors`
- 如果原 status 为 "ok"，则改为 "degraded"

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
（[memory_hook_core.py:185-194](/Users/busiji/memory/workspace/tools/memory_hook_core.py:185)）

---

## 9 cmux_hook_state.py 的 hook state 记录机制

### 9.1 状态文件位置

`default_hook_state_path()`（[cmux_hook_state.py:42-43](/Users/busiji/memory/workspace/tools/cmux_hook_state.py:42)）：
- 优先路径：`{project_dir}/workspace/artifacts/cmux-runtime/hook-state.json`
- 回退路径：`{project_dir}/.cmux-runtime/hook-state.json`

由 `runtime_state_dir()`（line 34-39）决定：如果 `workspace/artifacts` 存在则用 `workspace/artifacts/cmux-runtime`，否则用 `.cmux-runtime`。

### 9.2 状态文件结构

hook-state.json 的顶层结构（[cmux_hook_state.py:74-79](/Users/busiji/memory/workspace/tools/cmux_hook_state.py:74)）：

```json
{
    "runtime": "cmux",
    "updated_at": "2026-04-26T14:30:25+0800",
    "surfaces": {
        "{surface_ref}": { ... }
    }
}
```

### 9.3 surface 状态结构

每个 surface 的状态字段（[cmux_hook_state.py:176-189](/Users/busiji/memory/workspace/tools/cmux_hook_state.py:176)）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `workspace_ref` | `str` | workspace 引用 |
| `surface_ref` | `str` | surface 引用 |
| `session_start_count` | `int` | session-start 事件计数 |
| `prompt_submit_count` | `int` | prompt-submit 事件计数 |
| `stop_count` | `int` | stop 事件计数 |
| `notification_count` | `int` | notification 事件计数 |
| `last_event` | `str` | 最近一次事件名 |
| `last_event_at` | `str` | 最近一次事件时间（`YYYY-MM-DDTHH:MM:SS±ZZZZ`） |
| `last_session_id` | `str` | 最近一次 session ID |
| `last_cwd` | `str` | 最近一次 cwd |

### 9.4 record_hook_event() 流程

`record_hook_event()`（[cmux_hook_state.py:160-225](/Users/busiji/memory/workspace/tools/cmux_hook_state.py:160)）：

1. 获取文件级排他锁 `_exclusive_hook_state_lock()`（line 169），使用 `fcntl.flock(LOCK_EX)`（line 27）
2. 加载现有状态 `load_hook_state()`（line 170），文件不存在或解析失败时返回 base payload
3. 获取或创建对应 `surface_ref` 的 surface_state（line 171-204）
4. 更新 `workspace_ref`、`surface_ref`、`last_event`、`last_event_at`、`last_session_id`、`last_cwd`（line 207-212）
5. 根据 `event_name` 递增对应计数器（line 214-221）：
   - `session-start` → `session_start_count += 1`
   - `prompt-submit` → `prompt_submit_count += 1`
   - `stop` → `stop_count += 1`
   - `notification` → `notification_count += 1`
6. 更新顶层 `updated_at`（line 223）
7. 原子写入 `_write_hook_state_unlocked()`（line 224）：
   - 写入临时文件 → `fsync` → `rename` 替换（line 125-135）
   - 写入后 `load_hook_state_strict()` 验证（line 140）
8. 释放锁，返回更新后的 surface_state

### 9.5 原子写入机制

`_write_hook_state_unlocked()`（[cmux_hook_state.py:121-140](/Users/busiji/memory/workspace/tools/cmux_hook_state.py:121)）：

1. 在目标目录创建临时文件 `tempfile.mkstemp()`（line 125-129）
2. 写入 JSON 内容并 `fsync`（line 131-134）
3. `Path.replace()` 原子替换（line 135）
4. finally 块清理残留临时文件（line 137-139）
5. 读取验证 `load_hook_state_strict()`（line 140）

### 9.6 并发安全

通过 `_exclusive_hook_state_lock()` context manager（line 22-31）实现：
- 锁文件路径：`{hook-state.json}.lock`（line 17-19）
- 使用 `fcntl.flock(LOCK_EX)` 排他锁
- 锁文件自动创建（`open("a+")`）
- finally 块确保 `LOCK_UN` 释放

### 9.7 在 gateway 中的调用

`ClaudeDelegate` 在 `execute()` 中调用 `record_hook_event()`（[memory_hook_impls.py:149-159](/Users/busiji/memory/workspace/tools/memory_hook_impls.py:149)）：

1. 通过 `state_path_factory` 确定 state 文件路径（line 150）
2. 通过 `canonicalizer` 规范化 workspace_ref 和 surface_ref（line 151-154）
3. 构建 payload `{session_id, cwd}`（line 155）
4. 调用 `state_recorder()` 即 `record_hook_event()`（line 156-158）
5. 异常时静默忽略（line 159）
