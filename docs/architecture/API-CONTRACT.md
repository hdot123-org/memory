---
type: "[DOC:DESIGN]"
title: "Memory API 契约（context-package-v1）"
shortname: DES-011
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: high
tags: [api-contract,context-package,gateway]
related: [DES-001, DES-002, DES-010]
---

> 文档编号：DES-011 | 版本：V1.1 | 日期：2026-09-05 | 维护人：A10（最终合成）

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05（v0.45.6）。如需精确接口签名，请参考源码（`memory_core/tools/`）。

# Memory API 契约（context-package-v1）

> 创建日期：2026-04-26 | 维护人：A10（最终合成）| 状态：可评审 | 2026-09-05 校准

> **📌 2026-09-05 校准备注**（相对 2026-05-14 / v0.4.0 Beta 版快照的变更）：
>
> 1. **schema_version 实测值**（`memory_hook_schema.py:19-20` 与 `memory_core/constants.py`）：内部 v2 = `"wb-hook-v2"`，对外 v1 = `"context-package-v1"`（与 `CANONICAL_MEMORY_LOCK_SCHEMA` 同值），另有第三层 `"memory-v1"`（project 段仅引用 canonical 文件映射）。三者均存活，转换层未移除。
> 2. **host 取值收敛**：`"codex"` / `"claude"` 已移除，现值 = `SUPPORTED_HOSTS = ("factory", "zcode")`（`CoreConfig.__post_init__` 强制校验）。
> 3. **event 扩为 9 种**：session-start / prompt-submit / stop / notification / pre-tool-use / post-tool-use / subagent-stop / pre-compact / session-end；其中 6 种非注入事件走快速路径不构建完整 package。
> 4. **入口函数现状**：`build_context_package()` 增加 `lifecycle_record` 参数（4 参）；新增薄入口 `build_context_package_simple()`（3 参 + `schema` 选择）；core 侧新增 `build_context_package_from_config(CoreConfig)` 结构化入口（37+ kwargs 问题的落地解）。
> 5. **CLI 契约面**：`pyproject.toml [project.scripts]` 共 15 入口（§6 实测清单）。
> 6. **artifact_refs 扩为 5 键**：snapshot / latest / daily_latest / event_log / legacy_event_log（Sink 落盘时注入，仅存在于 artifact 文件，不在 API 返回值中）。

---

## 1. 契约概览

`memory` 模块对外暴露 **一组入口函数 + 一组出口结构**。消费者（CLI、MCP server、validate、测试）仅通过此契约交互，不感知内部 CoreConfig 字段、adapter 配置（default_runtime_profile 约 40 键）、provider 选择等实现细节。

出口结构分三层 schema，由 `memory_hook_schema.py` 统一转换：

```
build_context_package_core()          →  内部 v2（"wb-hook-v2"，全量诊断字段）
        │ convert_to_v1()
        ▼
context-package-v1（消费契约，~12 顶层字段）
        │ convert_legacy_to_memory_v1()
        ▼
memory-v1（project 段 → memory/kb/projects/{scope}/ canonical 文件映射）
```

---

## 2. 入口契约

### 2.1 函数签名（现行三层入口）

```python
# ① Gateway 编排入口（_gateway_policy.py）
def build_context_package(
    host: str,
    event: str,
    payload: dict[str, Any],
    lifecycle_record: dict[str, Any] | None = None,
) -> dict[str, Any]: ...          # 返回内部 v2 package

# ② 薄入口（schema 转换后返回；MCP server / memory_core.tools 懒加载导出使用）
def build_context_package_simple(
    host: str,
    event: str,
    payload: dict[str, Any] | None = None,
    *,
    adapter: str | None = None,
    schema: str = "context-package-v1",   # 或 "memory-v1"
) -> dict[str, Any]: ...

# ③ Core 纯组装入口（内部；等价两种形态）
def build_context_package_from_config(config: CoreConfig) -> dict[str, Any]: ...
def build_context_package_core(*, host: str, event: str, ...,     # ~39 keyword-only 参数
                               global_kb_root: Path | None = None,
                               global_kb_enabled: bool = True) -> dict[str, Any]: ...
```

### 2.2 参数说明

| # | 参数 | 类型 | 必填 | 取值 | 说明 |
|---|------|------|------|------|------|
| 1 | `host` | `str` | 是 | `"factory"` / `"zcode"` | 调用方身份（`SUPPORTED_HOSTS`；codex/claude 已移除） |
| 2 | `event` | `str` | 是 | 9 种（见 §2.2.1） | 触发事件类型 |
| 3 | `payload` | `dict[str, Any]` | 是（②可选） | 任意 JSON 对象 | 事件载荷（cwd、task_ref、session_id、transcript_path 等） |
| 4 | `lifecycle_record` | `dict \| None` | 否 | 生命周期记录 | ①独有；为 None 时入口内补记 |
| 5 | `schema` | `str` | 否 | `"context-package-v1"` / `"memory-v1"` | ②独有；出口 schema 选择 |

#### 2.2.1 event 取值（9 种，`_gateway_dispatch._parse_args()` choices）

| event | 路径 | 说明 |
|-------|------|------|
| `session-start` | 完整路径（注入） | 构建 package + additionalContext 注入 + 遥测同步 + 版本跟随 + 健康检查 |
| `prompt-submit` | 完整路径（注入） | 构建 package + additionalContext 注入 + 实时心跳日志 |
| `pre-tool-use` | 守卫路径 | PreToolUse 守卫（allow exit 0 / block exit 2），不构建完整 package |
| `stop` / `post-tool-use` / `subagent-stop` / `pre-compact` / `session-end` / `notification` | 快速路径 | 仅生命周期记录 + 快速指标 + 最小 event log，输出 `{"suppressOutput": true}` |

### 2.3 调用示例

```python
# MCP load_context 工具内部（mcp_server.py）
package = build_context_package_simple("factory", "session-start", {"cwd": cwd})
# schema_version == "context-package-v1"

# memory-v1 出口
package = build_context_package_simple("factory", "session-start", {"cwd": cwd}, schema="memory-v1")

# Gateway 主链（_gateway_handlers.main）
package = build_context_package(host, event, payload, lifecycle_record=record)
# schema_version == "wb-hook-v2"（内部全量结构）
```

### 2.4 为什么入口保持薄

- **A1**：core 的全部依赖（路径常量、策略派生、回调、环境变量）由 gateway 经 `CoreConfig` dataclass（38 字段，5 组）一次性组装；`from_gateway_kwargs()` 桥接旧 37 kwargs。
- **A3**：所有调用方（CLI、MCP、validate、测试）都只传 3-4 个参数。
- **A4**：default_runtime_profile 的约 40 个 adapter 配置键在 import-time 注入，是 wiring 参数，不是 API 参数。
- **A6**：LangChain 2 参数、Mem0 1 条消息——薄 API 是行业共识。

---

## 3. 出口契约

### 3.1 内部 v2 返回值结构（`"wb-hook-v2"`）

`build_context_package_core()` / `build_context_package_from_config()` 返回 18 个顶层 key（`memory_hook_core.py` 返回字面量，实测）：

| Key | 类型 | 说明 |
|-----|------|------|
| `schema_version` | `str` | 固定 `"wb-hook-v2"` |
| `generated_at` | `str` | ISO 时间戳 |
| `host` / `event` | `str` | 路由标识 |
| `repo_root` / `workspace_root` / `cwd` | `str` | 路径上下文（扁平） |
| `project_scope` | `str` | 项目作用域 |
| `status` | `str` | `"ok"` / `"degraded"` / `"blocked"`（blocked 仅 session-start 完整性校验） |
| `missing_paths` | `list[str]` | 错误级缺失路径 |
| `warnings` | `list[str]` | 警告级缺失 canonical 文件（truth-model.md / memory-system.md / memory-routing.md） |
| `validation_errors` | `list[str]` | 验证错误扁平列表 |
| `system_context` | `dict` | 系统级上下文（25 基础字段 + gateway 条件注入字段） |
| `project_context` | `dict` | 项目级上下文（9 字段：scope / canonical / truth_basis_canonical / truth_status / runtime_root / source_refs / authority_refs / evidence_refs / conflict_status） |
| `task_context` | `dict` | 任务级上下文（event / task_ref / session_id / surface_id / workspace_id / payload_keys） |
| `allowed_reads` | `list[str]` | 允许读取路径（含 v0.8.0+ 全局 KB 域目录兜底） |
| `allowed_writes` | `dict` | 写入目标映射（12 基础键 + kb_policy，运行时追加 hook_lifecycle / hook_global_state_root） |
| `evidence_refs` | `list[str]` | 证据引用 |

gateway 编排在 `system_context` 条件注入：`core_provider` / `core_provider_requested` / `core_provider_fallback_errors` / `project_lifecycle` / `shadow_run` / `source_repo_skip_validation` / `previous_health_alert`。

### 3.2 context-package-v1 返回值结构（`convert_to_v1()` 实测转换规则）

```python
{
    "schema_version": "context-package-v1",
    "generated_at": "2026-09-05T12:00:00+08:00",
    "host": "factory",
    "event": "session-start",
    "status": "ok",  # "ok" | "degraded"
    "paths": {
        "repo_root": "<consumer-repo>",
        "workspace_root": "<consumer-repo>",
        "cwd": "<consumer-repo>",
    },
    "project_scope": "<scope>",
    "task": {  # task_context 原样改名
        "event": "session-start",
        "task_ref": "<scope>:session-start",
        "session_id": "...",
        "surface_id": "...",
        "workspace_id": "...",
        "payload_keys": [...],
    },
    "allowed_reads": ["/path/to/file1"],
    "allowed_writes": {
        "fact": "...",
        "kb_policy": {
            "mode": "read-first-CRUD",
            "overwrite_allowed": False,
            "conflict_strategy": "preserve-and-escalate",
        },
        # ... 共 12 基础键
    },
    "evidence_refs": ["/path/to/evidence1"],
    "validation_errors": [],
    "project": {  # project_context 原样改名（9 字段）
        "scope": "<scope>",
        "canonical": "...",
        "truth_basis_canonical": "...",
        "truth_status": "truth-ready",  # "truth-ready" | "truth-incomplete"
        "runtime_root": "/path/to/runtime",
        "source_refs": [],
        "authority_refs": [],
        "evidence_refs": [],
        "conflict_status": [...],
    },
}
```

转换规则（`memory_hook_schema.py`，逐条实测）：

| 操作 | 内容 |
|------|------|
| 版本改写 | `schema_version` → `"context-package-v1"` |
| 嵌套分组 | 扁平 `repo_root` / `workspace_root` / `cwd` → `paths` 子字典 |
| 改名 | `project_context` → `project`；`task_context` → `task`（内容原样保留） |
| 直通（`_KEEP_KEYS` 9 键） | generated_at / host / event / status / project_scope / allowed_reads / allowed_writes / evidence_refs / validation_errors |
| 丢弃（`_DROP_KEYS`） | `system_context`（诊断信息走 stderr/日志）；`missing_paths`（已在上游合并进 validation_errors 语义） |
| 隐式丢弃 | `warnings`：不在 `_KEEP_KEYS` 白名单、也不属于 paths/project/task 改名处理范围，v1 转换后不出现（v2 专属字段） |

### 3.3 memory-v1 结构（第三层）

`convert_to_memory_v1()` 在 v1 之上重写 `project` 段为 canonical 文件引用映射（`_MEMORY_CANONICAL_MAP`）：

```python
"project": {
    "scope": "<scope>",
    "canonical": "memory/kb/projects/{scope}/CANONICAL.md",
    "plan":     "memory/kb/projects/{scope}/PLAN.md",
    "state":    "memory/kb/projects/{scope}/STATE.md",
    "tasks":    "memory/kb/projects/{scope}/TASKS.md",
}
```

v1 → memory-v1 额外丢弃 project 子键：`name` / `description` / `tech_stack`（`_DROP_PROJECT_KEYS`）。`convert_legacy_to_memory_v1()` 接受 v2 / v1 / memory-v1 任一输入统一归一到 memory-v1。

### 3.4 artifact_refs（仅 artifact 文件，5 键）

`ArtifactSinkImpl.write()` 落盘前向 **v2** package 注入：

| 键 | 指向 |
|----|------|
| `snapshot` | `contexts/{day}/{timestamp}-{host}-{event}.json` |
| `latest` | `contexts/latest-{host}-{event}.json` |
| `daily_latest` | `contexts/{day}/latest-{host}-{event}.json` |
| `event_log` | `events/{day}.jsonl` |
| `legacy_event_log` | `events.jsonl` |

因此：**API 返回值（任何 schema 层）均不含 artifact_refs**；只有落盘的 snapshot / latest / daily_latest / event log 文件中的 v2 package 携带它。

### 3.5 无损审计（is_lossless）

`is_lossless()` 支持两种调用约定：通用 dict 对比（主用）与 schema-aware 回退（v2→v1 / v1→memory-v1 / v2→memory-v1）。转换发生丢弃时，`_write_audit_log()` 写结构化审计行到 `MEMORY_SCHEMA_AUDIT_LOG`（默认 `memory/system/schema-audit.log`）并镜像 stderr；`MEMORY_HOOK_SCHEMA_AUDIT=0` 静默。

---

## 4. 设计原则

1. **入口最薄**：消费者只传 host + event + payload，其余依赖 gateway 经 CoreConfig（38 字段 dataclass）组装。
2. **出口分层**：内部 v2 全量诊断 → v1 消费契约（~12 顶层字段）→ memory-v1 canonical 引用；诊断信息走独立通道。
3. **provider 透明**：external-core / legacy 切换（`MEMORY_HOOK_CORE_PROVIDER`，默认 legacy，allow_fallback）对消费者透明，`status` 是唯一降级信号。
4. **adapter 隔离**：default_runtime_profile 约 40 配置键是 wiring 参数。
5. **版本化**：三层 schema_version 常量 + `CANONICAL_MEMORY_LOCK_SCHEMA` 锁定消费契约版本。

---

## 5. 迁移状态核对（原三阶段已落地）

| 原阶段 | 落地状态 | 现状证据 |
|--------|----------|----------|
| 阶段 1：诊断通道分离 | ✅ | `core_provider*` / `shadow_run` 位于 v2 `system_context` 内，v1 转换时随 system_context 整体丢弃 |
| 阶段 2：出口结构精简 | ✅ | `paths` / `task` / `project` 嵌套重组与改名在 `convert_to_v1()` 实现；`missing_paths` 在 v1 中丢弃；`schema_version` 写 `"context-package-v1"` |
| 阶段 3：验证与稳定 | ✅ | CLI / MCP（load_context 经 build_context_package_simple）/ 测试三路径消费同一转换；schema_version 随 package 持久化到 artifact 文件头 |

补充校准：原方案设想的「artifact 文件头写入 v1 schema_version」实际实现为——**artifact 落盘保存 v2 全量 + artifact_refs**（保留诊断能力），v1 仅作为 API/工具消费契约出口；memory-v1 由 MCP 等按需请求。

---

## 6. CLI 契约面（pyproject [project.scripts]，15 入口实测）

| # | 入口 | 模块:函数 |
|---|------|-----------|
| 1 | `memory-init` | `memory_core.tools.init_project_memory:main` |
| 2 | `memory-migrate` | `memory_core.tools.migrate_project_memory:main` |
| 3 | `memory-validate` | `memory_core.tools.validate_project_memory:main` |
| 4 | `memory-promote` | `memory_core.tools.promote_global_kb:main` |
| 5 | `memory-hook-gateway` | `memory_core.tools.hook_runtime_guard:gateway_main` |
| 6 | `memory-factory-hooks` | `memory_core.tools.factory_global_hooks:main` |
| 7 | `memory-consistency-check` | `memory_core.tools.consistency_check:main` |
| 8 | `memory-plan-residue` | `infra_core.packs.memory.layout_audit:plan_main` |
| 9 | `memory-apply-residue-plan` | `memory_core.tools.apply_residue_plan:main` |
| 10 | `memory-ownership` | `memory_core.tools.ownership_cli:main` |
| 11 | `memory-verify-consumer` | `memory_core.tools.verify_consumer:main` |
| 12 | `memory-integrity-resign` | `memory_core.tools.memory_integrity_resign:main` |
| 13 | `memory-lifecycle-rebuild` | `memory_core.tools.project_lifecycle:rebuild_main` |
| 14 | `memory-lifecycle-migrate` | `memory_core.tools.project_lifecycle:migrate_main` |
| 15 | `memory-mcp-server` | `memory_core.tools.mcp_server:main_sync` |

MCP server 暴露 9 工具：`load_context` / `search_memory` / `resolve_doc_path` / `save_memory` / `validate_write` / `record_event` / `get_health` / `list_projects` / `get_daily_summary`（`--tools` 逗号列表可裁剪子集）。

---

## 7. 常量与版本（schema_version 实测值清单）

| 常量 | 值 | 出处 |
|------|-----|------|
| `V2_VERSION` | `"wb-hook-v2"` | `memory_hook_schema.py:20`（内部 v2 标识；core 返回字面量同值） |
| `V1_VERSION` | `"context-package-v1"` | `memory_hook_schema.py:19` |
| `MEMORY_V1_VERSION` | `"memory-v1"` | `memory_hook_schema.py`（`convert_to_memory_v1` 段） |
| `CANONICAL_MEMORY_LOCK_SCHEMA` | `"context-package-v1"` | `memory_core/constants.py` |
| `CANONICAL_ADAPTER_VERSION` | `"builtin"` | `memory_core/constants.py` |
| `OWNERSHIP_SCHEMA_VERSION` | `"memory-ownership-v1"` | `memory_core/constants.py` |
| `INDEX_SCHEMA_VERSION` | `"1.0"` | `index_schema.py`（INDEX.md 契约版本；verify-consumer 的 expected_schema_version 来源） |
| `SUPPORTED_HOSTS` | `("factory", "zcode")` | `memory_core/constants.py` |
| `CURRENT_MEMORY_VERSION` | `"0.45.6"` | `memory_core/__init__.py`（`__version__`，constants 再导出） |

---

## 8. 分析来源声明（历史，2026-04-26）

| 子代理 | 文件 | 核心贡献 |
|--------|------|----------|
| A1（入口分析） | `a1-entry-analysis.md` | 确认 3 参数为最小必要集 |
| A2（出口分析） | `a2-exit-analysis.md` | 设计 context-package-v1 嵌套结构 |
| A3（消费审计） | `a3-consumer-usage.md` | 审计调用方，确认实际消费面 ~10 字段 |
| A4（adapter 配置） | `a4-adapter-config.md` | 确认 adapter key 是 wiring 非 API |
| A5（provider 透明度） | `a5-provider-transparency.md` | 确认 provider/shadow 移入诊断通道 |
| A6（业界参考） | `a6-industry-reference.md` | 参考 LangChain/Mem0/Zep，确认薄 API 趋势 |
| A7（交叉验证） | `a7-cross-validation.md` | 调和 A2/A3 矛盾，确认 system_context 移除 |
| A8（迁移计划） | 本文档第 5 节 | 三阶段迁移路径（2026-09-05 核对：已全部落地，见 §5） |
| A9（API 骨架） | 本文档第 2-3 节 | 入口函数签名 + 出口结构 |
| A10（最终合成） | 本文档 | 综合 A1-A9，产出唯一设计产出物；2026-09-05 按源码重校准 |
