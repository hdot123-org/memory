---
type: "[DOC:DESIGN]"
title: "Core Assembly 核心装配"
shortname: DES-003
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-09-05
source: code-analysis
confidence: medium
tags: [core,assembly,context]
related: [DES-001, DES-004, DES-005]
---

> 文档编号：DES-003 | 版本：V1.1 | 日期：2026-09-05 | 状态：可评审 | 维护人：codex

> **⚠️ 版本快照**：本文档为架构设计参考，最后校准于 2026-09-05 (v0.45.6)。如需精确接口签名，请参考源码。

# Core Assembly 设计文档

> 来源文件：`memory_core/tools/memory_hook_core.py`（552 行）、`memory_core/tools/memory_hook_config.py`（262 行）
> 校准日期：2026-09-05（v0.45.6；行号均经 `grep -n` / `wc -l` 实测）

> **📌 2026-09-05 校准备注**
> 1. `memory_hook_core.py` 已是独立的核心装配模块（552 行），不再寄居于 gateway；gateway 本体瘦身为 494 行门面（`memory_hook_gateway.py`）+ `_gateway_{handlers,policy,config,dispatch,telemetry,artifacts}.py` 子模块（合计 2,835 行），并有 `_gateway_patch_redirect.py`（158 行）保证 monkeypatch 门面语义不变。
> 2. 新增结构化入口 `build_context_package_from_config(config: CoreConfig)`（memory_hook_core.py:507），以 `memory_hook_config.py` 的 `CoreConfig` dataclass 替代散装 keyword-only 参数；两个入口行为一致（见第 7 节）。
> 3. `build_context_package_core` 相比 v0.4.0 新增 `global_kb_root` / `global_kb_enabled` 两个参数（v0.8.0 全局知识库 fallback 读取），输出新增顶层 `warnings` key：canonical 缺失分为错误（`missing_paths`）与警告（`warnings`，仅限 truth-model.md / memory-system.md / memory-routing.md 三个文件名）两桶。
> 4. 输出 `schema_version` 当前真实值为 `"wb-hook-v2"`（memory_hook_core.py:473 硬编码；`memory_hook_schema.py:14` 定义 `V2_VERSION = "wb-hook-v2"`）。v2→v1 / memory-v1 转换层**仍然存在**（`memory_hook_schema.py`，424 行）；`_apply_artifact_compaction` 现位于 `_gateway_policy.py:458`。
> 5. 装配逻辑重组为 5 个 Phase + 10 个模块级辅助函数；本文全部行号锚点按 v0.45.6 实测刷新。
> 6. 仓库规模（实测）：`memory_core/tools/` 88 个模块、28,706 行；`tests/` 216 个 Python 文件。

> **Schema 双层说明**：核心内部组装 wb-hook-v2 schema，对外由 `memory_hook_schema.py` 转换：`convert_to_v1()`（:162）产出 `context-package-v1`，`convert_to_memory_v1()`（:235）与 `convert_legacy_to_memory_v1()`（:285）产出 `memory-v1`；转换丢弃 key 时写审计日志（`MEMORY_SCHEMA_AUDIT_LOG`，默认 `memory/system/schema-audit.log`；`MEMORY_HOOK_SCHEMA_AUDIT=0` 关闭，并始终向 stderr 输出一行）。Gateway 简化入口 `build_context_package_simple(host, event, payload, *, adapter=None, schema="context-package-v1")`（`_gateway_policy.py:438`）在内部完成 v2 构建 + schema 转换；adapter 级字段裁剪由 `_apply_artifact_compaction`（`_gateway_policy.py:458`）按 `ARTIFACT_COMPACTION` 配置的 `include_*` 开关移除对应 section。

---

## 1. build_context_package_core() 完整签名

函数定义在 memory_hook_core.py:331-505，全部参数均为 **keyword-only**（`*` 之后），共 **39 个**（v0.4.0 为 37 个，新增 #38/#39）。

### 1.1 参数列表

| # | 参数名 | 类型 | 用途 |
|---|--------|------|------|
| 1 | `host` | `str` | 当前执行主机标识（factory / zcode） |
| 2 | `event` | `str` | 触发事件名（如 `"stop"`），用于 gate 判定和 task_ref 构造 |
| 3 | `payload` | `dict[str, Any]` | 上游传入的原始事件载荷，从中提取 `task_ref`、`session_id` |
| 4 | `cwd` | `Path` | 当前工作目录 |
| 5 | `project_scope` | `str` | 项目作用域标识，用于查找 project_canonical、truth_basis 等 |
| 6 | `workspace_root` | `Path` | 工作区根目录 |
| 7 | `repo_root` | `Path` | Git 仓库根目录 |
| 8 | `required_canonical` | `list[Path]` | 必须存在的规范文件路径列表，缺失将被分桶记录（见 Phase 1） |
| 9 | `project_canonical` | `dict[str, Path]` | 项目作用域 → 项目规范文件路径的映射 |
| 10 | `project_runtime_root` | `dict[str, Path]` | 项目作用域 → 运行时根目录的映射 |
| 11 | `global_canonical` | `list[Path]` | 全局规范文件路径列表 |
| 12 | `project_map_governance` | `Path` | 项目映射治理文件路径 |
| 13 | `event_log` | `Path` | 事件日志文件路径 |
| 14 | `legality_source_policy` | `str` | 合法性源策略标识 |
| 15 | `registration_commit_policy` | `str` | 注册提交策略标识 |
| 16 | `registration_commit_phase` | `str` | 注册提交阶段（如 `"enforced"` / `"declared-not-enforced"`），作为 gate 的 default_phase |
| 17 | `project_map_refs` | `list[str]` | 项目映射引用字符串列表 |
| 18 | `extract_excerpt_fn` | `Callable[[Path], list[str]]` | 从文件提取摘要片段的回调 |
| 19 | `now_iso_fn` | `Callable[[], str]` | 返回当前 ISO 时间戳的回调 |
| 20 | `write_targets_fn` | `Callable[[], dict[str, Any]]` | 返回写入目标列表的回调（`allowed_writes` 的唯一来源，:502） |
| 21 | `validate_project_map_fn` | `Callable[[], list[str]]` | 验证项目映射，返回错误列表 |
| 22 | `validate_unique_legal_system_contract_fn` | `Callable[[], list[str]]` | 验证唯一合法系统合约，返回错误列表 |
| 23 | `policy_validate_fn` | `Callable[[dict[str, Any]], list[str]]` | 策略校验回调，接收 context dict，返回错误列表 |
| 24 | `get_policy_pack_fn` | `Callable[[str], dict[str, Any]]` | 按 project_scope 获取策略包，返回 dict |
| 25 | `governance_frozen_tuple_errors_fn` | `Callable[[], list[str]]` | 检查治理冻结元组约束，返回错误列表 |
| 26 | `event_contract_blocker_errors_fn` | `Callable[[], list[str]]` | 检查事件合约阻塞条件，返回错误列表 |
| 27 | `git_registration_probe_fn` | `Callable[[str, dict[str, Any]], dict[str, Any]]` | 探测 git 注册状态，接收 (event, payload)，返回 gate dict |
| 28 | `truth_basis_for_scope_fn` | `Callable[[str], dict[str, Any]]` | 获取指定 scope 的 truth basis 信息 |
| 29 | `decision_refs_for_scope_fn` | `Callable[[str], list[str]]` | 获取指定 scope 的决策引用列表 |
| 30 | `lesson_refs_for_scope_fn` | `Callable[[str], list[str]]` | 获取指定 scope 的经验教训引用列表 |
| 31 | `docs_refs_for_scope_fn` | `Callable[[str], list[str]]` | 获取指定 scope 的文档引用列表 |
| 32 | `hook_contract_path` | `Path` | Hook 合约文件路径 |
| 33 | `surface_id` | `str` | 表面/面板标识 |
| 34 | `workspace_id` | `str` | 工作区标识 |
| 35 | `governance_blocker_scopes` | `Collection[str] \| None` | 需要执行治理冻结检查的 scope 集合；`None` 表示不检查 |
| 36 | `event_contract_blocker_scopes` | `Collection[str] \| None` | 需要执行事件合约检查的 scope 集合；`None` 表示不检查 |
| 37 | `core_evidence_refs` | `list[str] \| None` | 核心证据引用列表（可选追加） |
| 38 | `global_kb_root` | `Path \| None` | 全局知识库根目录（v0.8.0+；启用时其领域目录追加进 `allowed_reads`），默认 `None` |
| 39 | `global_kb_enabled` | `bool` | 全局知识库 fallback 开关，默认 `True` |

### 1.2 返回类型

`dict[str, Any]` — 完整的 context package（wb-hook-v2 schema），见第 4 节。

---

## 2. 核心装配逻辑 — 执行顺序（5 个 Phase）

函数体到 line 505 返回（docstring 位于 :373-376，首个执行语句为 Phase 1，line 377）。v0.45.6 将装配拆为 10 个模块级辅助函数，主函数体只保留 5 个 Phase 的编排（Phase 注释锚点：377 / 380 / 390 / 410 / 429）。

### Phase 1：canonical 缺失分桶（lines 377-378）

调用 `_collect_canonical_missing()`（:139-157）遍历 `required_canonical`：

- 文件名命中 `_CANONICAL_FILENAMES`（:136，= `{truth-model.md, memory-system.md, memory-routing.md}`）的缺失路径 → `missing_canonical_files`（**warning 级**，输出为顶层 `warnings` key，不参与 status 判定）；
- 其余缺失路径 → `missing_paths`（**error 级**，参与 status 判定）。

### Phase 2：验证错误（lines 380-389）

1. `validate_project_map_fn()` → `project_map_errors`（:381）。
2. `validate_unique_legal_system_contract_fn()` → `contract_errors`（:382）。
3. `policy_validate_fn({host, event, cwd: str(cwd), project_scope})`，try/except 包裹，异常捕获为单条错误（:383-389）。

### Phase 3：治理 / 注册（lines 390-409）

1. 仅当 `project_scope ∈ governance_blocker_scopes` 时执行 `governance_frozen_tuple_errors_fn()`（:393）。
2. 仅当 `project_scope ∈ event_contract_blocker_scopes` 时执行 `event_contract_blocker_errors_fn()`（:394）。
3. `git_registration_probe_fn(event, payload)` 获取 gate 初始状态（:395）。
4. `get_policy_pack_fn(project_scope)`（try/except：失败时构造 `{"error": ..., "scope": ...}` 并向 `policy_errors` 追加一条，:397-401）。
5. `evaluate_registration_commit_gate()`（:92-128，见第 6.2 节）回填 gate 元数据并产生 `registration_gate_errors`（:403-409）。

### Phase 4：项目文件 + truth basis（lines 410-428）

1. `_resolve_project_file()`（:159-176）：`project_scope` 不在 `project_canonical` → 向 `policy_errors` 追加 unsupported 错误，并构造 fallback 路径 `workspace_root / "projects" / <scope> / "PROJECT.md"`；路径存在但文件不存在 → 追加到 `missing_paths`。
2. 依次调用 4 个 `*_for_scope_fn` 收集 decisions / lessons / docs_refs / truth_basis。
3. `_compute_truth_basis_errors()`（:180-226）：
   - 构建 `reads`（即 `allowed_reads`）：`NOW.md` + `project_map_refs` + `memory/kb/INDEX.md` + `memory/docs/INDEX.md` + truth_basis_refs + decisions + lessons + docs_refs；
   - **全局知识库 fallback（v0.8.0+）**：当 `global_kb_enabled` 且 `global_kb_root` 非 None 时，将全局 KB 下各领域目录（跳过 `pending/`）追加进 reads；
   - 交叉验证：truth_basis_refs ⊆ reads（subset 检查）；decisions / lessons / docs_refs 与 truth_basis_refs 两两不重叠（3 个 overlap 检查）。

### Phase 5：status + 组装（lines 429-505）

1. `blocker_errors = governance_tuple_errors + event_contract_errors + registration_gate_errors`（:430）。
2. `_derive_status()`（:228-247）与 `_derive_project_truth_status()`（:249-253）判定状态（见第 5 节）。
3. `runtime_root = project_runtime_root.get(scope, workspace_root / "projects" / scope)`（fallback）。
4. `evidence_refs = project_map_refs + core_evidence_refs + project_map_governance + event_log`（:436）。
5. `_assemble_system_context()`（:256-307）与 `_assemble_project_context()`（:309-329）组装子结构。
6. 组装并返回顶层 dict（:472-505；`schema_version` 在 :473，`allowed_writes` 在 :502）。

---

## 3. 验证链条顺序（摘要）

按执行先后排列（锚点为 Phase 注释行与辅助函数定义行）：

```
1. required_canonical 存在性分桶              (Phase 1, line 377; helper :139)
2. validate_project_map_fn()                  (Phase 2, line 381)
3. validate_unique_legal_system_contract_fn() (Phase 2, line 382)
4. policy_validate_fn(context_dict)           (Phase 2, lines 383-389)
5. governance_frozen_tuple_errors_fn()        (Phase 3, line 393, 条件)
6. event_contract_blocker_errors_fn()         (Phase 3, line 394, 条件)
7. git_registration_probe_fn(event, payload)  (Phase 3, line 395)
8. get_policy_pack_fn(project_scope)          (Phase 3, lines 397-401)
9. evaluate_registration_commit_gate(...)     (Phase 3, lines 403-409)
10. project_canonical 查找 + fallback         (Phase 4; helper :159)
11. 引用收集 (decisions/lessons/docs/truth)   (Phase 4)
12. reads 构建 + 全局 KB fallback + 交叉验证  (Phase 4; helper :180)
```

条件执行说明：
- Step 5 仅在 `project_scope ∈ governance_blocker_scopes` 时执行。
- Step 6 仅在 `project_scope ∈ event_contract_blocker_scopes` 时执行。
- Step 9 始终执行，但其内部逻辑根据 `phase` 和 `gate_event` 决定是否产生错误。

---

## 4. 返回值结构

返回 dict（lines 472-505）包含以下 **顶层 key**（共 17 个）：

| Key | 类型 | 来源 |
|-----|------|------|
| `schema_version` | `str` | 固定 `"wb-hook-v2"`（:473） |
| `generated_at` | `str` | `now_iso_fn()` |
| `host` | `str` | 入参 `host` |
| `event` | `str` | 入参 `event` |
| `repo_root` | `str` | `str(repo_root)` |
| `workspace_root` | `str` | `str(workspace_root)` |
| `cwd` | `str` | `str(cwd)` |
| `project_scope` | `str` | 入参 `project_scope` |
| `status` | `str` | `"ok"` / `"degraded"`（见第 5 节） |
| `missing_paths` | `list[str]` | 不存在的 required_canonical（非 canonical 三文件名）+ project_file |
| `warnings` | `list[str]` | 缺失的 canonical 文件（truth-model.md / memory-system.md / memory-routing.md），warning 级 |
| `validation_errors` | `list[str]` | 按序合并：project_map + contract + policy + truth_basis + blocker 五类错误 |
| `system_context` | `dict` | 系统级上下文（见 4.1） |
| `project_context` | `dict` | 项目级上下文（见 4.2） |
| `task_context` | `dict` | 任务级上下文（见 4.3） |
| `allowed_reads` | `list[str]` | 构建的 reads 列表（含全局 KB fallback 目录） |
| `allowed_writes` | `dict[str, Any]` | `write_targets_fn()`（:502） |
| `evidence_refs` | `list[str]` | 证据引用汇总 |

### 4.1 system_context 子结构（25 个 key，由 `_assemble_system_context` :256 组装）

| Key | 值来源 |
|-----|--------|
| `boot_entry` | `workspace_root / "INDEX.md"` |
| `state_entry` | `workspace_root / "NOW.md"` |
| `state_summary` | `extract_excerpt_fn(workspace_root / "NOW.md")` |
| `project_map_refs` | 入参 `project_map_refs` |
| `project_map_validation` | `"pass"` 或 `"fail"` |
| `legality_contract_validation` | `"pass"` 或 `"fail"` |
| `legality_source_policy` | 入参 |
| `registration_commit_policy` | 入参 |
| `registration_commit_gate` | evaluate 后的 gate dict |
| `registration_commit_enforced` | gate 的 `enforced` 字段（默认 False） |
| `registration_commit_enforcement_result` | gate 的 `enforcement_result` 字段（默认 `"not-enforced"`） |
| `global_canonical` | `[str(p) for p in global_canonical]` |
| `truth_basis_policy` | `truth_basis["policy"]`（缺省 `"default"`） |
| `truth_basis_validation` | `"pass"` / `"fail"`（有 truth_basis_errors 时强制 `"fail"`；缺省 `"unknown"`） |
| `truth_basis_refs` | truth_basis 的 refs |
| `truth_basis_errors` | truth basis 错误列表 |
| `governance_frozen_tuple_validation` | `"pass"` / `"fail"` |
| `governance_frozen_tuple_errors` | 治理错误列表 |
| `event_contract_alignment_validation` | `"pass"` / `"fail"` |
| `event_contract_alignment_errors` | 事件合约错误列表 |
| `decision_refs` | decisions 列表 |
| `lesson_refs` | lessons 列表 |
| `docs_refs` | docs_refs 列表 |
| `hook_contract` | `str(hook_contract_path)` |
| `policy_pack` | 策略包 dict |

### 4.2 project_context 子结构（9 个 key，由 `_assemble_project_context` :309 组装）

| Key | 值来源 |
|-----|--------|
| `scope` | `project_scope` |
| `canonical` | `str(project_file)` |
| `truth_basis_canonical` | `truth_basis["project_ref"]` |
| `truth_status` | `"truth-ready"` / `"truth-incomplete"` |
| `runtime_root` | 从 `project_runtime_root` 或 fallback 路径 |
| `source_refs` | `truth_basis["source_refs"]` |
| `authority_refs` | `truth_basis["authority_refs"]` |
| `evidence_refs` | `truth_basis["evidence_refs"]` |
| `conflict_status` | `truth_basis["conflict_status"]`（缺省 `["unknown"]`） |

### 4.3 task_context 子结构（6 个 key，内联组装）

| Key | 值来源 |
|-----|--------|
| `event` | `event` |
| `task_ref` | `payload["task_ref"]` 或 `"{project_scope}:{event}"` |
| `session_id` | `payload["session_id"]` 或 `""` |
| `surface_id` | 入参 |
| `workspace_id` | 入参 |
| `payload_keys` | `sorted(payload.keys())` |

---

## 5. Status 状态机

### 5.1 判定条件（`_derive_status` :228）

| 状态 | 条件 |
|------|------|
| `"ok"` | 全部 6 个错误列表均为空 |
| `"degraded"` | 任意 1 个及以上错误列表非空 |
| `"error"` | **代码中不存在此状态**；函数不会返回 `"error"` |

注意：`warnings`（missing_canonical_files 桶）**不参与** status 判定。

### 5.2 参与判定的 6 个错误源

1. `missing_paths` — 文件不存在（error 级）
2. `project_map_errors` — 项目映射验证失败
3. `contract_errors` — 合法系统合约验证失败
4. `policy_errors` — 策略校验失败（含 policy_validate_fn 异常、policy_pack 获取失败、unsupported project_scope）
5. `truth_basis_errors` — truth basis 交叉验证失败（subset / overlap）
6. `blocker_errors` — 治理冻结元组 + 事件合约 + 注册提交门控的错误合并

### 5.3 project_truth_status 独立判定（`_derive_project_truth_status` :249）

| 状态 | 条件 |
|------|------|
| `"truth-ready"` | `truth_basis["validation"] == "pass"` **且** `truth_basis_errors` 为空 |
| `"truth-incomplete"` | 否则 |

---

## 6. 辅助函数

### 6.1 registration_phase_from_policy_pack()（:76-90）

**签名：**

```python
def registration_phase_from_policy_pack(
    policy_pack: dict[str, Any],
    default_phase: str = "declared-not-enforced",
) -> str
```

**逻辑：** 从 `policy_pack["policies"]` 提取 `registration_phase`；是 dict 且 phase 为非空字符串则返回该值，否则返回 `default_phase`。对缺失或格式错误的 policy_pack 安全降级。

### 6.2 evaluate_registration_commit_gate()（:92-128）

**签名：**

```python
def evaluate_registration_commit_gate(
    policy_pack: dict[str, Any],
    registration_commit_gate: dict[str, Any],
    event: str,
    default_phase: str = "declared-not-enforced",
) -> tuple[dict[str, Any], list[str]]
```

**执行步骤：**

1. **浅拷贝 gate**，避免修改入参。
2. **解析 phase**：调用 `registration_phase_from_policy_pack`。
3. **判定是否 enforced**：`enforced = phase == "enforced"`。
4. **回填 gate 元数据**：写入 `phase`、`enforced` 字段。
5. **判定 gate_event 是否匹配**：`triggered = event == gate.get("gate_event", "stop")`，写入 `triggered_on_current_event`。
6. **三分支判定：**

| 条件 | enforcement_result | 返回值 |
|------|-------------------|--------|
| `not enforced` | `"not-enforced"` | `(gate, [])` |
| `enforced and not triggered` | `"awaiting-gate-event"` | `(gate, [])` |
| `enforced and triggered and status == "committed-coupled"` | `"passed"` | `(gate, [])` |
| `enforced and triggered and status != "committed-coupled"` | `"failed"` | `(gate, [error])` |

**核心语义：** 仅在 phase 为 `"enforced"` 且当前事件匹配 gate_event 时，才要求 git 注册状态为 `"committed-coupled"`；否则不阻塞。

### 6.3 私有辅助函数总表

| 函数 | 行号 | 职责 |
|------|------|------|
| `_resolve_callbacks` | :16-74 | 从 CoreConfig 的 `policy_registry` / `path_utils` 复合接口对象提取 bound methods，否则回退到平铺回调字段 |
| `_safe_tb` | :131 | 运行时安全提取 truth_basis dict 的 key（带默认值） |
| `_collect_canonical_missing` | :139-157 | canonical 缺失分桶（error / warning） |
| `_resolve_project_file` | :159-176 | 解析项目 canonical 文件（unsupported scope fallback + 缺失记录） |
| `_compute_truth_basis_errors` | :180-226 | reads 构建 + 全局 KB fallback + subset/overlap 交叉验证 |
| `_derive_status` | :228-247 | 6 错误源 → `"ok"` / `"degraded"` |
| `_derive_project_truth_status` | :249-253 | → `"truth-ready"` / `"truth-incomplete"` |
| `_assemble_system_context` | :256-307 | 组装 system_context（25 key） |
| `_assemble_project_context` | :309-329 | 组装 project_context（9 key） |

---

## 7. 结构化入口：build_context_package_from_config() 与 CoreConfig

### 7.1 build_context_package_from_config()（:507-552）

**签名：** `def build_context_package_from_config(config: "CoreConfig") -> dict[str, Any]`

行为与 `build_context_package_core(**kwargs)` 完全一致，仅参数接口不同：先经 `_resolve_callbacks(config)`（:16）归一化回调（config 携带 `policy_registry` / `path_utils` 接口对象时直接提取 bound methods，否则使用平铺回调字段），再委托 `build_context_package_core`。

**已知边界（定性）：** 当前该入口未转发 `global_kb_root` / `global_kb_enabled`（CoreConfig 尚无这两个字段），config 路径下使用默认值 `None` / `True`，即不追加全局 KB fallback reads。

### 7.2 CoreConfig（memory_hook_config.py:21，全文件 262 行）

`@dataclass`，按关注点分 5 组字段：

| 组 | 字段数 | 内容 |
|----|--------|------|
| Group 1 环境 | 7 | host、event、payload、cwd、project_scope、workspace_root、repo_root |
| Group 2 路径 | 7 | required_canonical、project_canonical、project_runtime_root、global_canonical、project_map_governance、event_log、hook_contract_path |
| Group 3 策略 | 6 | legality_source_policy、registration_commit_policy、registration_commit_phase、project_map_refs、surface_id、workspace_id |
| Group 4 回调 | 13 | extract / now_iso / write_targets + 10 个验证与查询回调 |
| Group 5 接口对象与可选 | 5 | policy_registry、path_utils（默认 None）+ governance_blocker_scopes、event_contract_blocker_scopes、core_evidence_refs（默认 None） |

附带能力：`__post_init__` 分组校验（host 必须在 `SUPPORTED_HOSTS` 内等）；`uses_interfaces` property；`from_gateway_kwargs()` / `to_gateway_kwargs()` 与旧 kwargs 风格双向桥接。
