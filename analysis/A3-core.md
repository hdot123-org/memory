# A3: Core 模块分析

**文件**: `workspace/tools/memory_hook_core.py` (383 行)
**配套**: `workspace/tools/memory_hook_config.py` (CoreConfig dataclass, 227 行)
**分析日期**: 2026-04-27

---

## 1. 函数清单

### 1.1 `_resolve_callbacks(config: CoreConfig) -> dict[str, Callable]`

| 项目 | 详情 |
|------|------|
| 参数 | `config: CoreConfig` |
| 返回值 | `dict[str, Callable]` — 12 个 callback 的键值映射 |
| 职责 | 从 CoreConfig 中"解包"出 12 个回调函数。支持两种来源：(a) composite interface objects (`policy_registry`, `path_utils`)，(b) flat callback 字段 |
| 行范围 | 14-71 |

**解包的 12 个回调**:
- `validate_project_map_fn` — 验证项目映射
- `validate_unique_legal_system_contract_fn` — 验证合法系统合约
- `policy_validate_fn` — 策略验证（接受 dict 参数）
- `get_policy_pack_fn` — 获取策略包（接受 scope 字符串）
- `governance_frozen_tuple_errors_fn` — 治理冻结元组错误
- `event_contract_blocker_errors_fn` — 事件合约阻断错误
- `git_registration_probe_fn` — Git 注册探测（接受 event + payload）
- `truth_basis_for_scope_fn` — 获取 truth basis（接受 scope）
- `decision_refs_for_scope_fn` — 获取决策引用
- `lesson_refs_for_scope_fn` — 获取经验引用
- `docs_refs_for_scope_fn` — 获取文档引用
- `extract_excerpt_fn` — 提取摘要（接受 Path）
- `write_targets_fn` — 写入目标列表

### 1.2 `registration_phase_from_policy_pack(policy_pack, default_phase) -> str`

| 项目 | 详情 |
|------|------|
| 参数 | `policy_pack: dict[str, Any]`, `default_phase: str` (默认 `"declared-not-enforced"`) |
| 返回值 | `str` — 注册阶段标识 |
| 职责 | 从 policy_pack 深层结构 `policies.registration_phase` 中安全提取阶段值。缺失或格式错误时返回 default_phase |
| 行范围 | 74-87 |

### 1.3 `evaluate_registration_commit_gate(policy_pack, registration_commit_gate, event, default_phase) -> tuple[dict, list[str]]`

| 项目 | 详情 |
|------|------|
| 参数 | `policy_pack`, `registration_commit_gate`, `event`, `default_phase` |
| 返回值 | `(gate_dict, errors_list)` — 被修改的 gate 字典 + 错误列表 |
| 职责 | 评估注册提交门禁。三态决策树：(a) 非 enforced → not-enforced, (b) enforced 但事件不匹配 → awaiting-gate-event, (c) enforced + 事件匹配 → 检查 status == committed-coupled |
| 行范围 | 90-126 |

### 1.4 `build_context_package_core(**kwargs) -> dict[str, Any]`

| 项目 | 详情 |
|------|------|
| 参数 | 35 个 keyword-only 参数（见 CoreConfig 分析） |
| 返回值 | `dict[str, Any]` — 完整的 context package |
| 职责 | 核心装配函数：聚合所有验证、策略、引用、错误信息，输出标准化的 context package 字典 |
| 行范围 | 129-335 |

### 1.5 `build_context_package_from_config(config: CoreConfig) -> dict[str, Any]`

| 项目 | 详情 |
|------|------|
| 参数 | `config: CoreConfig` |
| 返回值 | `dict[str, Any]` — 同 build_context_package_core |
| 职责 | 便捷入口：将 CoreConfig 解包后转发给 build_context_package_core。推荐使用的入口 |
| 行范围 | 338-383 |

### 1.6 `_safe_tb(basis, key, default) -> Any` (内嵌函数)

| 项目 | 详情 |
|------|------|
| 参数 | `basis: dict`, `key: str`, `default: Any` |
| 返回值 | `Any` |
| 职责 | 安全地从 truth_basis dict 中提取键值。仅在 build_context_package_core 内部使用 |
| 行范围 | 174-176 |

---

## 2. 数据流：Input Payload → Output Context Package

```
payload (dict) + CoreConfig (35+ 字段)
    │
    ├─► 路径检查 ──────────────────── missing_paths (list[str])
    │     required_canonical 中不存在的 path
    │
    ├─► 验证链 ────────────────────── project_map_errors (list[str])
    │     validate_project_map_fn()      contract_errors (list[str])
    │     validate_unique_legal...()     policy_errors (list[str])
    │     policy_validate_fn({...})
    │
    ├─► 治理/合约检查 ───────────── governance_tuple_errors (list[str])
    │     governance_frozen_tuple...     event_contract_errors (list[str])
    │     event_contract_blocker...
    │
    ├─► Git 注册探测 ────────────── registration_commit_gate (dict)
    │     git_registration_probe_fn(event, payload)
    │          │
    │          └─► evaluate_registration_commit_gate()
    │                   从 policy_pack 取 phase
    │                   三态决策 → gate["enforcement_result"]
    │                   失败时产生 registration_gate_errors
    │
    ├─► Policy Pack 解析 ────────── policy_pack (dict)
    │     get_policy_pack_fn(project_scope)
    │     异常时 fallback → {"error": str(exc), "scope": project_scope}
    │
    ├─► Truth Basis 聚合 ────────── truth_basis (dict)
    │     truth_basis_for_scope_fn(project_scope)
    │     提取: refs, errors, validation, policy,
    │           project_ref, source_refs, authority_refs,
    │           evidence_refs, conflict_status
    │
    ├─► Scope Refs ──────────────── decisions, lessons, docs_refs
    │     decision_refs_for_scope_fn(project_scope)
    │     lesson_refs_for_scope_fn(project_scope)
    │     docs_refs_for_scope_fn(project_scope)
    │
    ├─► Reads 列表构建 ──────────── reads (list[str])
    │     NOW.md + project_map_refs + kb/INDEX.md + docs/INDEX.md
    │     + truth_basis_refs + decisions + lessons + docs_refs
    │
    ├─► 引用交叉验证 ───────────── truth_basis_errors (list[str])
    │     truth_basis_refs ⊆ reads ?
    │     decisions ∩ truth_basis_refs == ∅ ?
    │     lessons ∩ truth_basis_refs == ∅ ?
    │     docs_refs ∩ truth_basis_refs == ∅ ?
    │
    └─► 组装输出 ────────────────── context_package (dict)
          schema_version: "wb-hook-v2"
          generated_at: now_iso_fn()
          status: "ok" | "degraded"
          missing_paths, validation_errors
          system_context: { boot_entry, state_entry, 16+ 字段 }
          project_context: { scope, canonical, truth_status, 7+ 字段 }
          task_context: { event, task_ref, session_id, surface_id, workspace_id, payload_keys }
          allowed_reads: reads
          allowed_writes: write_targets_fn()
          evidence_refs: [project_map_refs, core_evidence_refs, governance, event_log]
```

---

## 3. CoreConfig 使用分析

### 3.1 字段分组与消费映射

CoreConfig 有 **38 个字段**，分为 5 组：

| 分组 | 字段数 | 消费位置 |
|------|--------|----------|
| **Group 1: Environment** | 7 | `build_context_package_core` 直接使用，大部分透传到输出 |
| **Group 2: Paths** | 7 | 路径检查、canonical 解析、runtime_root 推导 |
| **Group 3: Policy config** | 9 (6 必选 + 3 可选) | 策略透传、引用列表、ID 标识 |
| **Group 4: Callbacks** | 13 | 全部通过 `_resolve_callbacks` 解包后在核心流程中调用 |
| **Group 5: Interfaces + Optional** | 5 | `policy_registry`/`path_utils` 用于 provider 切换；其余 3 个可选字段直接透传 |

### 3.2 CoreConfig 到 build_context_package_core 的映射

`build_context_package_from_config()` 做了 **1:1 的字段映射**，没有任何变换逻辑：

- 所有 `config.*` 直接作为同名 kwargs 传递
- 唯一例外：callbacks 组通过 `_resolve_callbacks(config)` 间接获取
- `hook_contract_path` 在 CoreConfig 中属于 Group 2 (Paths)，但在 core 函数签名中放在末尾附近，属于参数位置不一致

### 3.3 `__post_init__` 校验

CoreConfig 在构造时做 **11 项类型/值校验**：
- `host` ∈ `{"codex", "claude"}`
- `event` 非空字符串
- `workspace_root`, `repo_root`, `cwd` 必须是 Path
- `payload` 必须是 dict
- `project_scope` 非空字符串
- `required_canonical`, `project_map_refs` 必须是 list
- `now_iso_fn`, `write_targets_fn`, `extract_excerpt_fn` 必须 callable
- `surface_id`, `workspace_id` 必须是字符串

**注意**: Group 4 中的 10 个 callback 没有在 `__post_init__` 中校验 callable，只有 3 个被校验。

---

## 4. Provider 机制：external-core vs legacy

### 4.1 双模式设计

`_resolve_callbacks()` 实现了一个 **双源 callback 解析** 机制：

```
                    CoreConfig
                   /          \
         policy_registry    flat callback fields
         path_utils         (37 kwargs style)
              \              /
               12 callbacks dict
```

### 4.2 Provider 切换逻辑

1. **external-core 模式** (新):
   - `config.policy_registry` 和 `config.path_utils` 均不为 None
   - callbacks 从这两个 interface object 的 bound methods 提取
   - `config.uses_interfaces` property 返回 True

2. **legacy 模式** (旧):
   - `config.policy_registry` 和 `config.path_utils` 为 None
   - callbacks 从 CoreConfig 的 flat 字段直接读取

3. **混合模式** (部分实现):
   - 代码支持只设置其中一个 interface object
   - 比如 `policy_registry` 有值但 `path_utils` 为 None → policy 相关从 interface 取，path 相关从 flat 字段取
   - 但这种混合状态没有文档说明，可能产生意外行为

### 4.3 接口对象类型

```python
if TYPE_CHECKING:
    from memory_hook_interfaces import PathUtils, PolicyRegistry
```

- 导入在 `TYPE_CHECKING` 块内，运行时不依赖这两个类型
- 这意味着接口对象的实际结构在运行时不做类型检查
- 如果 interface object 缺少某个方法，会在 `_resolve_callbacks` 的 `getattr` 处静默失败 → AttributeError

### 4.4 `from_gateway_kwargs()` 桥接

`CoreConfig.from_gateway_kwargs()` 接受 37 个 kwargs，返回 CoreConfig 实例。这是 legacy → structured 的迁移桥。

---

## 5. 错误处理

### 5.1 异常类型与处理点

| 位置 | 异常类型 | 处理策略 | 行号 |
|------|----------|----------|------|
| `policy_validate_fn()` 调用 | `Exception` (catch-all) | 捕获 → `policy_errors = [f"policy validation failed: {exc}"]` | 191-192 |
| `get_policy_pack_fn()` 调用 | `Exception` (catch-all) | 捕获 → `policy_pack = {"error": str(exc)}` + 追加到 `policy_errors` | 202-204 |
| `_resolve_callbacks()` 中 `getattr` | 无保护 | 如果 interface object 存在但缺少方法 → **会抛出 AttributeError** | 22-46 |
| `build_context_package_core` 内部 | 无 try/except | 其他 callback 调用未做保护 | 全文 |

### 5.2 Fallback 策略

1. **provider 切换 fallback**: `policy_registry` 为 None → 自动回退到 flat callback 字段
2. **policy_pack 解析失败**: 返回 `{"error": str(exc), "scope": project_scope}`，不阻断流程
3. **project_scope 未映射**: `project_canonical.get()` 返回 None → 追加错误 + 推导默认路径 `workspace_root / "projects" / {scope} / "PROJECT.md"`
4. **phase 缺失**: `registration_phase_from_policy_pack` 返回 default_phase

### 5.3 错误聚合与状态决策

所有错误最终汇集到 `validation_errors` 列表，同时决定 `status`:

```python
status = "ok" if not (
    missing_paths or project_map_errors or contract_errors
    or policy_errors or truth_basis_errors or blocker_errors
) else "degraded"
```

**无 "failed" 状态**：只有 `ok` 和 `degraded`。即使所有检查都失败，status 也只是 `degraded`。

---

## 6. 复杂度评估

### 6.1 函数粒度

| 函数 | 复杂度 | 评价 |
|------|--------|------|
| `_resolve_callbacks` | 低 (纯映射) | ✅ 职责清晰，但 12 个 key 的重复映射可考虑代码生成 |
| `registration_phase_from_policy_pack` | 极低 | ✅ 单一职责 |
| `evaluate_registration_commit_gate` | 低-中 | ✅ 三态决策清晰，但直接修改输入 dict (side-effect) |
| `build_context_package_core` | **高** (207 行) | ⚠️ 这是整个模块的核心，承担了所有验证、聚合、组装逻辑。建议拆分为 3-4 个子函数 |
| `build_context_package_from_config` | 极低 | ✅ 纯转发 |
| `_safe_tb` | 极低 | ✅ 但作为内嵌函数，如果其他地方需要会重复 |

### 6.2 `build_context_package_core` 内部结构分析

该函数 207 行，内部可识别出 **7 个逻辑阶段**：

1. **路径验证** (178-180): missing_paths + project_map + contract 检查
2. **策略验证** (182-192): policy_validate_fn 调用 + 异常保护
3. **治理/合约检查** (194-197): governance + event_contract 条件检查
4. **注册门禁** (198-211): git probe + gate evaluation
5. **Truth Basis 聚合** (213-246): scope refs + 交叉验证
6. **状态决策** (248-266): status + truth_status + evidence 计算
7. **输出组装** (268-335): 大型 return dict (67 行)

**建议拆分**:
- `_validate_paths_and_contracts(...)` → 阶段 1
- `_validate_policies(...)` → 阶段 2
- `_evaluate_governance_and_registration(...)` → 阶段 3-4
- `_assemble_truth_basis(...)` → 阶段 5
- `_build_output(...)` → 阶段 6-7

### 6.3 参数数量

`build_context_package_core` 有 **35 个参数**。即使全是 keyword-only，这个数字也偏高。`CoreConfig` 的引入正是为了解决这个问题。

---

## 7. 代码质量评分

### 评分: **7 / 10**

#### 加分项 (+)
1. **单一职责**: Core 模块只做 context package 构建，不做 gateway wiring
2. **结构化配置**: CoreConfig dataclass 取代了 37 个 kwargs，接口清晰
3. **Provider 双模式**: 支持新/旧两种 callback 来源，迁移友好
4. **防御性编程**: `policy_validate_fn` 和 `get_policy_pack_fn` 有 try/except 保护
5. **输入校验**: CoreConfig `__post_init__` 做了 11 项校验
6. **不可变输出**: 返回的是新构建的 dict，不修改输入

#### 减分项 (-)
1. **`evaluate_registration_commit_gate` 的副作用**: 直接 `gate = dict(registration_commit_gate)` 做浅拷贝后修改，调用方如果期望输入不被修改可能会意外
2. **回调校验不完整**: `__post_init__` 只校验了 3 个 callback 的 callable，另外 10 个没有校验
3. **`_resolve_callbacks` 无接口保护**: 如果 `policy_registry` 存在但缺少某个方法，会直接抛 AttributeError 而不是优雅 fallback
4. **`build_context_package_core` 过大**: 207 行的单函数承担了 7 个阶段的逻辑，输出 dict 有 67 行，可读性受损
5. **无 "failed" 状态**: 只有 ok/degraded 二态，无法区分轻微降级和严重失败
6. **`now_iso_fn` 参数签名不一致**: 在 CoreConfig callbacks 中声明为 `Callable[[], str]`，但在 `_resolve_callbacks` 中直接作为 `config.now_iso_fn` 使用（不经 resolve），与其他 callback 处理路径不同
7. **`from_gateway_kwargs()` 中 `asdict()` 会递归展开 dataclass**: 如果某个字段是复杂对象，`to_gateway_kwargs()` 的行为可能不符合预期

#### 改进建议优先级
- **P1**: 拆分 `build_context_package_core` 为 3-4 个子函数
- **P2**: 补全 `__post_init__` 中所有 callback 的 callable 校验
- **P2**: `_resolve_callbacks` 增加对 interface object 方法的 `hasattr` 保护
- **P3**: 考虑引入 `status = "failed"` 第三态
- **P3**: 消除 `evaluate_registration_commit_gate` 对输入 dict 的修改
