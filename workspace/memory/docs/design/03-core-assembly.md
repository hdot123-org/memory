---
type: "[DOC:DESIGN]"
title: "Core Assembly 核心装配"
shortname: DES-003
status: 可评审
scope: default
created: 2026-04-26
updated: 2026-04-26
source: code-analysis
confidence: medium
tags: [core,assembly,context]
related: [DES-001, DES-004, DES-005]
---

> 文档编号：DES-003 | 版本：V1.0 | 日期：2026-04-26 | 状态：可评审 | 维护人：codex

# Core Assembly 设计文档

> 来源文件：`workspace/tools/memory_hook_core.py`（271 行）
> 生成日期：2026-04-26

---

## 1. build_context_package_core() 完整签名

函数定义在 memory_hook_core.py:69-108，全部参数均为 **keyword-only**（`*` 之后）。

### 1.1 参数列表

| # | 参数名 | 类型 | 用途 |
|---|--------|------|------|
| 1 | `host` | `str` | 当前执行主机标识 |
| 2 | `event` | `str` | 触发事件名（如 `"stop"`），用于 gate 判定和 task_ref 构造 |
| 3 | `payload` | `dict[str, Any]` | 上游传入的原始事件载荷，从中提取 `task_ref`、`session_id` |
| 4 | `cwd` | `Path` | 当前工作目录 |
| 5 | `project_scope` | `str` | 项目作用域标识，用于查找 project_canonical、truth_basis 等 |
| 6 | `workspace_root` | `Path` | 工作区根目录 |
| 7 | `repo_root` | `Path` | Git 仓库根目录 |
| 8 | `required_canonical` | `list[Path]` | 必须存在的规范文件路径列表，缺失将被记录 |
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
| 20 | `write_targets_fn` | `Callable[[], dict[str, Any]]` | 返回写入目标列表的回调 |
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

### 1.2 返回类型

`dict[str, Any]` — 完整的 context package，见第 4 节。

---

## 2. 核心装配逻辑 — 执行顺序

函数体从 line 114 开始，到 line 271 返回。执行顺序如下：

### Step 1：基础文件存在性检查（line 114）

遍历 `required_canonical`，将不存在的路径记录到 `missing_paths` 列表。

### Step 2：项目映射验证（line 115）

调用 `validate_project_map_fn()`，返回错误字符串列表。

### Step 3：合法系统合约验证（line 116）

调用 `validate_unique_legal_system_contract_fn()`。

### Step 4：策略校验（lines 118-128）

构造 context dict `{host, event, cwd, project_scope}` 传给 `policy_validate_fn`；若抛异常则捕获为单条错误。

### Step 5：治理冻结元组检查（lines 130-132）

仅当 `project_scope` 在 `governance_blocker_scopes` 集合中时才执行 `governance_frozen_tuple_errors_fn()`。

### Step 6：事件合约阻塞检查（line 133）

仅当 `project_scope` 在 `event_contract_blocker_scopes` 集合中时才执行 `event_contract_blocker_errors_fn()`。

### Step 7：Git 注册探测（line 134）

调用 `git_registration_probe_fn(event, payload)` 获取 gate 初始状态。

### Step 8：获取策略包（lines 136-140）

调用 `get_policy_pack_fn(project_scope)`；若获取失败，构造 error dict 并追加到 `policy_errors`。

### Step 9：评估注册提交门控（lines 142-147）

调用 `evaluate_registration_commit_gate()`（见第 6.2 节），返回更新后的 gate dict 和错误列表。

### Step 10：项目文件解析（lines 149-154）

- 若 `project_scope` 不在 `project_canonical` 中 → 追加不支持错误，构造默认 fallback 路径。
- 若路径存在但文件不存在 → 追加到 `missing_paths`。

### Step 11：引用收集（lines 156-161）

依次获取 decisions、lessons、docs_refs、truth_basis 完整信息。

### Step 12：构建 allowed_reads（lines 163-172）

固定包含 `NOW.md`、项目映射引用、知识库索引、文档索引、truth basis / decisions / lessons / docs 引用。

### Step 13：Truth Basis 交叉验证（lines 173-182）

- 检查 truth_basis_refs 是否全部在 allowed_reads 中（subset 检查）。
- 检查 decisions / lessons / docs_refs 是否与 truth_basis_refs 有重叠（不允许交叉）。

### Step 14：汇总 blocker 错误（line 184）

合并 governance_tuple_errors + event_contract_errors + registration_gate_errors。

### Step 15：判定 status（lines 185-193）

见第 5 节状态机。

### Step 16：判定 project_truth_status（line 195）

`truth_basis["validation"] == "pass"` 且无 truth_basis_errors → `"truth-ready"`，否则 `"truth-incomplete"`。

### Step 17：计算 runtime_root（line 196）

从 `project_runtime_root` 查找，fallback 到 `workspace_root / "projects" / project_scope`。

### Step 18：构建 evidence_refs（lines 197-202）

合并 project_map_refs + core_evidence_refs + project_map_governance + event_log。

### Step 19：组装返回值（lines 204-271）

见第 4 节。

---

## 3. 验证链条顺序（摘要）

按执行先后排列：

```
1. required_canonical 文件存在性检查          (line 114)
2. validate_project_map_fn()                  (line 115)
3. validate_unique_legal_system_contract_fn() (line 116)
4. policy_validate_fn(context_dict)           (lines 118-128)
5. governance_frozen_tuple_errors_fn()        (line 132, 条件)
6. event_contract_blocker_errors_fn()         (line 133, 条件)
7. git_registration_probe_fn(event, payload)  (line 134)
8. get_policy_pack_fn(project_scope)          (lines 136-140)
9. evaluate_registration_commit_gate(...)     (lines 142-147)
10. project_canonical 查找 + fallback         (lines 149-154)
11. 引用收集 (decisions/lessons/docs/truth)   (lines 156-161)
12. 构建 allowed_reads                        (lines 163-172)
13. Truth Basis 交叉验证 (subset + overlap)   (lines 173-182)
```

条件执行说明：
- Step 5 仅在 `project_scope ∈ governance_blocker_scopes` 时执行。
- Step 6 仅在 `project_scope ∈ event_contract_blocker_scopes` 时执行。
- Step 9 始终执行，但其内部逻辑根据 `phase` 和 `gate_event` 决定是否产生错误。

---

## 4. 返回值结构

返回 dict 包含以下 **顶层 key**（lines 204-271）：

| Key | 类型 | 来源 |
|-----|------|------|
| `schema_version` | `str` | 硬编码 `"wb-hook-v2"` |
| `generated_at` | `str` | `now_iso_fn()` |
| `host` | `str` | 入参 `host` |
| `event` | `str` | 入参 `event` |
| `repo_root` | `str` | `str(repo_root)` |
| `workspace_root` | `str` | `str(workspace_root)` |
| `cwd` | `str` | `str(cwd)` |
| `project_scope` | `str` | 入参 `project_scope` |
| `status` | `str` | `"ok"` / `"degraded"`（见第 5 节） |
| `missing_paths` | `list[str]` | 不存在的 required_canonical + project_file |
| `validation_errors` | `list[str]` | 合并所有验证阶段的错误列表 |
| `system_context` | `dict` | 系统级上下文（见下表） |
| `project_context` | `dict` | 项目级上下文（见下表） |
| `task_context` | `dict` | 任务级上下文（见下表） |
| `allowed_reads` | `list[str]` | 构建的 reads 列表 |
| `allowed_writes` | `dict[str, Any]` | `write_targets_fn()` |
| `evidence_refs` | `list[str]` | 证据引用汇总 |

### 4.1 system_context 子结构

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
| `registration_commit_enforced` | gate 的 `enforced` 字段 |
| `registration_commit_enforcement_result` | gate 的 `enforcement_result` 字段 |
| `global_canonical` | `[str(p) for p in global_canonical]` |
| `truth_basis_policy` | `truth_basis["policy"]` |
| `truth_basis_validation` | `"pass"` / `"fail"`（有 truth_basis_errors 时强制 `"fail"`） |
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

### 4.2 project_context 子结构

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
| `conflict_status` | `truth_basis["conflict_status"]` |

### 4.3 task_context 子结构

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

判定逻辑在 lines 185-193：

### 5.1 判定条件

| 状态 | 条件 |
|------|------|
| `"ok"` | 全部 6 个错误列表均为空 |
| `"degraded"` | 任意 1 个及以上错误列表非空 |
| `"error"` | **代码中不存在此状态**；函数不会返回 `"error"` |

### 5.2 参与判定的 6 个错误源

1. `missing_paths` — 文件不存在
2. `project_map_errors` — 项目映射验证失败
3. `contract_errors` — 合法系统合约验证失败
4. `policy_errors` — 策略校验失败（含 policy_validate_fn 异常、policy_pack 获取失败、unsupported project_scope）
5. `truth_basis_errors` — truth basis 交叉验证失败（subset / overlap）
6. `blocker_errors` — 治理冻结元组 + 事件合约 + 注册提交门控的错误合并

### 5.3 project_truth_status 独立判定

| 状态 | 条件 |
|------|------|
| `"truth-ready"` | `truth_basis["validation"] == "pass"` **且** `truth_basis_errors` 为空 |
| `"truth-incomplete"` | 否则 |

---

## 6. 两个辅助函数

### 6.1 registration_phase_from_policy_pack()

定义在 lines 14-27。

**签名：**

```python
def registration_phase_from_policy_pack(
    policy_pack: dict[str, Any],
    default_phase: str = "declared-not-enforced",
) -> str
```

**逻辑：**

1. 从 `policy_pack` 中提取 `policies` 字段（line 22）。
2. 若 `policies` 是 dict，则从中提取 `registration_phase`（lines 23-24）。
3. 若 `phase` 是非空字符串，返回该值（lines 25-26）。
4. 否则返回 `default_phase`（line 27）。

**用途：** 为 `evaluate_registration_commit_gate` 提供 phase 解析能力，对缺失或格式错误的 policy_pack 安全降级。

### 6.2 evaluate_registration_commit_gate()

定义在 lines 30-66。

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

1. **浅拷贝 gate**：`gate = dict(registration_commit_gate)`（line 43），避免修改入参。
2. **解析 phase**：调用 `registration_phase_from_policy_pack` 获取 phase（line 44）。
3. **判定是否 enforced**：`enforced = phase == "enforced"`（line 45）。
4. **回填 gate 元数据**：写入 `phase` 和 `enforced` 字段（lines 47-48）。
5. **判定 gate_event 是否匹配**：`triggered = event == gate.get("gate_event", "stop")`（lines 49-50），写入 `triggered_on_current_event`（line 51）。
6. **三分支判定：**

| 条件 | enforcement_result | 返回值 |
|------|-------------------|--------|
| `not enforced` | `"not-enforced"` | `(gate, [])` |
| `enforced and not triggered` | `"awaiting-gate-event"` | `(gate, [])` |
| `enforced and triggered and status == "committed-coupled"` | `"passed"` | `(gate, [])` |
| `enforced and triggered and status != "committed-coupled"` | `"failed"` | `(gate, [error])` |

**返回值：** 更新后的 gate dict 和错误列表（最多 1 条错误）。

**核心语义：** 仅在 phase 为 `"enforced"` 且当前事件匹配 gate_event 时，才要求 git 注册状态为 `"committed-coupled"`；否则不阻塞。
