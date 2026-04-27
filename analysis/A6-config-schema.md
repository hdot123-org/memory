# A6: Config & Schema 分析

> 分析目标：`workspace/tools/memory_hook_config.py`（227 行） + `workspace/tools/memory_hook_schema.py`（74 行）
> 日期：2026-04-27

---

## 1. CoreConfig 字段清单

### Group 1: Environment（7 个字段，全必填）

| # | 字段 | 类型 | 默认值 | 说明 |
|---|------|------|--------|------|
| 1 | `host` | `str` | — | 宿主名，仅接受 `"codex"` / `"claude"` |
| 2 | `event` | `str` | — | 事件标识，非空字符串 |
| 3 | `payload` | `dict[str, Any]` | — | 网关传入的原始事件载荷 |
| 4 | `cwd` | `Path` | — | 当前工作目录 |
| 5 | `project_scope` | `str` | — | 项目范围标识，非空 |
| 6 | `workspace_root` | `Path` | — | 工作空间根目录 |
| 7 | `repo_root` | `Path` | — | 仓库根目录 |

### Group 2: Paths（7 个字段，全必填）

| # | 字段 | 类型 | 默认值 | 说明 |
|---|------|------|--------|------|
| 8 | `required_canonical` | `list[Path]` | — | 必需的 canonical 路径列表 |
| 9 | `project_canonical` | `dict[str, Path]` | — | project → canonical path 映射 |
| 10 | `project_runtime_root` | `dict[str, Path]` | — | project → runtime root 映射 |
| 11 | `global_canonical` | `list[Path]` | — | 全局 canonical 路径列表 |
| 12 | `project_map_governance` | `Path` | — | 项目治理策略文件路径 |
| 13 | `event_log` | `Path` | — | 事件日志文件路径 |
| 14 | `hook_contract_path` | `Path` | — | Hook 契约文件路径 |

### Group 3: Policy config（6 个必填字段）

| # | 字段 | 类型 | 默认值 | 说明 |
|---|------|------|--------|------|
| 15 | `legality_source_policy` | `str` | — | 合法性来源策略 |
| 16 | `registration_commit_policy` | `str` | — | 注册 commit 策略 |
| 17 | `registration_commit_phase` | `str` | — | 注册 commit 阶段 |
| 18 | `project_map_refs` | `list[str]` | — | 项目映射引用列表 |
| 19 | `surface_id` | `str` | — | 表面/界面 ID |
| 20 | `workspace_id` | `str` | — | 工作空间 ID |

### Group 4: Callbacks（13 个字段，全必填）

| # | 字段 | 签名 | 说明 |
|---|------|------|------|
| 21 | `extract_excerpt_fn` | `(Path) → list[str]` | 从文件提取摘要 |
| 22 | `now_iso_fn` | `() → str` | 获取当前 ISO 时间戳 |
| 23 | `write_targets_fn` | `() → dict` | 写入目标信息 |
| 24 | `validate_project_map_fn` | `() → list[str]` | 验证项目映射 |
| 25 | `validate_unique_legal_system_contract_fn` | `() → list[str]` | 验证唯一合法系统契约 |
| 26 | `policy_validate_fn` | `(dict) → list[str]` | 策略验证 |
| 27 | `get_policy_pack_fn` | `(str) → dict` | 获取策略包 |
| 28 | `governance_frozen_tuple_errors_fn` | `() → list[str]` | 治理冻结元组错误检查 |
| 29 | `event_contract_blocker_errors_fn` | `() → list[str]` | 事件契约阻塞错误检查 |
| 30 | `git_registration_probe_fn` | `(str, dict) → dict` | Git 注册探测 |
| 31 | `truth_basis_for_scope_fn` | `(str) → dict` | 获取范围的事实基础 |
| 32 | `decision_refs_for_scope_fn` | `(str) → list[str]` | 获取范围的决策引用 |
| 33 | `lesson_refs_for_scope_fn` | `(str) → list[str]` | 获取范围的教训引用 |

### Group 5: Interface objects & optional fields（5 个字段，全可选）

| # | 字段 | 类型 | 默认值 | 说明 |
|---|------|------|--------|------|
| 34 | `policy_registry` | `PolicyRegistry \| None` | `None` | 策略注册表接口对象 |
| 35 | `path_utils` | `PathUtils \| None` | `None` | 路径工具接口对象 |
| 36 | `governance_blocker_scopes` | `Collection[str] \| None` | `None` | 治理阻塞范围 |
| 37 | `event_contract_blocker_scopes` | `Collection[str] \| None` | `None` | 事件契约阻塞范围 |
| 38 | `core_evidence_refs` | `list[str] \| None` | `None` | 核心证据引用 |

**总计：37 个字段**（注：Gateway 构造时传了 37 个，config 声明了 38 个，其中 `docs_refs_for_scope_fn` 是第 33 个 callback，实际上总数应为 37 个必填 + 5 个可选 = 42？重新核对：Group1(7) + Group2(7) + Group3(6) + Group4(13) + Group5(5) = 38。但 Group3 标注说 6 个必填，实际列了 6 个。Gateway 传的 kwargs 是 37 个，对应 `from_gateway_kwargs` 的参数签名。）

**实际字段数：37**（`from_gateway_kwargs` 签名字段数 = 37，`CoreConfig` 类体字段数 = 37，分组统计应为 7+7+6+13+4 = 37，其中 `docs_refs_for_scope_fn` 属 Group4，Group5 有 4 个非-callback 可选字段 + `docs_refs_for_scope_fn` 不在 Group5）。

---

## 2. 验证逻辑（`__post_init__`）

### 已覆盖验证（14/37 字段）

| 字段 | 检查内容 | 异常类型 |
|------|----------|----------|
| `host` | `in ("codex", "claude")` | `ValueError` |
| `event` | `isinstance(str)` 且非空 | `ValueError` |
| `payload` | `isinstance(dict)` | `TypeError` |
| `cwd` | `isinstance(Path)` | `TypeError` |
| `project_scope` | `isinstance(str)` 且非空 | `ValueError` |
| `workspace_root` | `isinstance(Path)` | `TypeError` |
| `repo_root` | `isinstance(Path)` | `TypeError` |
| `required_canonical` | `isinstance(list)` | `TypeError` |
| `project_map_refs` | `isinstance(list)` | `TypeError` |
| `now_iso_fn` | `callable()` | `TypeError` |
| `write_targets_fn` | `callable()` | `TypeError` |
| `extract_excerpt_fn` | `callable()` | `TypeError` |
| `surface_id` | `isinstance(str)` | `TypeError` |
| `workspace_id` | `isinstance(str)` | `TypeError` |

### 未覆盖验证（23/37 字段）

以下字段在 `__post_init__` 中 **没有** 类型/值校验：

- **Group 2 全部 7 个**：`required_canonical`（仅检查 list 类型，未检查元素）、`project_canonical`、`project_runtime_root`、`global_canonical`、`project_map_governance`、`event_log`、`hook_contract_path`
- **Group 3 前 4 个**：`legality_source_policy`、`registration_commit_policy`、`registration_commit_phase`、`project_map_refs`（仅检查 list 类型）
- **Group 4 中 10 个 callbacks**：除了已验证的 3 个外，剩余 10 个 callback 均未检查 `callable()`
- **Group 5**：全是 optional，合理跳过了

---

## 3. 工厂方法分析

### `from_gateway_kwargs()`

**职责**：桥接函数，接收当前 37 个 `**kwargs` 参数，原封不动地构造 `CoreConfig` 实例。

**转换逻辑**：零转换。参数名 → 字段名完全一一对应，纯传递。

**特点**：
- 签名包含全部 37 个参数，其中 32 个必填 + 5 个 optional（带 `= None`）
- 与 Gateway 中 `CoreConfig(...)` 直接构造的调用方式功能完全相同
- 实际 Gateway 代码（`memory_hook_gateway.py:759`）使用的是 `CoreConfig(...)` 直接构造，**未调用** `from_gateway_kwargs()`
- 这是一个**未使用**的桥接方法，可能是为未来迁移预留的

### `to_gateway_kwargs()`

**职责**：用 `dataclasses.asdict(self)` 将 CoreConfig 展平为 `dict`。

**问题**：
- 直接 `asdict()` 会将 `Path` 对象保留为 `Path`（不会自动转 `str`）
- 如果目标是给旧的 `**kwargs` 接口用，`Path` 类型需要转换为字符串
- `callable` 字段经过 `asdict()` 后仍保持引用，这点正确

### `uses_interfaces` property

```python
return self.policy_registry is not None and self.path_utils is not None
```

判断是否提供了复合接口对象（而非单个 callback）。在 `_resolve_callbacks()` 中被 `getattr()` 间接使用，但该 property 本身**未被直接调用**。

---

## 4. Schema 模块分析

### v2（wb-hook-v2）→ v1（context-package-v1）

`memory_hook_schema.py` 只做一件事：**将 v2 格式转换为 v1 格式**。

#### 结构变换

| 操作 | v2 | v1 |
|------|----|----|
| `schema_version` | `"wb-hook-v2"` | `"context-package-v1"` |
| `repo_root`, `workspace_root`, `cwd` | 顶层散列 | 收入 `paths` 子 dict |
| `project_context` | 顶层 | 重命名为 `project` |
| `task_context` | 顶层 | 重命名为 `task` |
| `system_context` | 顶层 | **删除** |
| `missing_paths` | 顶层 | **删除** |

#### 保持不变的键（`_KEEP_KEYS`）

`generated_at`, `host`, `event`, `status`, `project_scope`, `allowed_reads`, `allowed_writes`, `evidence_refs`, `validation_errors`

#### 被删除的键（`_DROP_KEYS`）

| 键 | 去向 |
|----|------|
| `system_context` | 诊断信息，转 stderr/logs |
| `missing_paths` | 已合并到上游 `validation_errors` |

### 辅助函数

- `is_v1(package)`: 检查 `schema_version == "context-package-v1"`
- `is_v2(package)`: 检查 `schema_version == "wb-hook-v2"`

### v1 → v2 反向转换

**不存在**。只有 v2 → v1 单向转换，意味着 v2 是"旧格式"、v1 是"新格式"。

---

## 5. 向后兼容性分析

### Schema 转换

**基本无损，但有两个已知信息丢弃：**

1. **`system_context` 被丢弃**：包含 `core_provider`、`core_provider_requested`、`core_provider_fallback_errors` 等诊断信息。这些在 Gateway 代码中被写入 v2 package，转换时丢失。如果下游消费者需要这些信息，会造成信息断裂。

2. **`missing_paths` 被丢弃**：说明文档称"已合并到 validation_errors upstream"。如果上游确实做了合并，则无损；如果上游未做，则此信息丢失。

### CoreConfig 兼容性

- `from_gateway_kwargs()` 的签名与现有 37 个 kwargs **完全一一对应**，无信息丢失
- `to_gateway_kwargs()` 理论上可还原，但 `Path` 类型不自动转 `str` 可能导致下游期望字符串的场景出错
- 整体：**CoreConfig 是 kwargs 的结构化包装，无损等价**

---

## 6. 字段冗余分析

### 6.1 高可疑冗余字段

| 字段 | 可疑原因 |
|------|----------|
| `project_canonical` | 与 `project_runtime_root` 和 `global_canonical` 有语义重叠；实际仅通过 `project_canonical.get(project_scope)` 取单值 |
| `project_runtime_root` | 同上，仅通过 `get(project_scope)` 取单值；可考虑与 `project_canonical` 合并或延迟计算 |
| `global_canonical` | 始终为单元素列表 `[WORKSPACE_ROOT / "memory" / "kb" / "global"]`（见 Gateway:693），用 `list` 类型过于泛化 |

### 6.2 低使用率字段

| 字段 | 使用情况 |
|------|----------|
| `event_log` | 在 `from_gateway_kwargs` 中传递，但在 `build_context_package_from_config` 和 `_resolve_callbacks` 中**未被使用** |
| `project_map_governance` | 同上，传入后未被消费 |
| `docs_refs_for_scope_fn` | 定义了 13 个 callback 之一，但在 `_resolve_callbacks` 的返回值 dict 中**没有包含**这个 key |
| `core_evidence_refs` | Gateway 传入，但 config 消费端未见使用 |

### 6.3 双通道设计（callback vs interface）

Group4 的 13 个 callback 与 Group5 的 `policy_registry` + `path_utils` 形成**双通道**：
- 当 `policy_registry` 存在时，9 个 callback 从 registry 提取
- 当 `path_utils` 存在时，2 个 callback 从 path_utils 提取
- 否则回退到 Group4 的独立 callback 字段

**这是有意设计，不是冗余**。但代价是 11 个 callback 字段在 interface 模式下被忽略（死字段），增加了理解负担。

---

## 7. 改进建议

### 建议 1：补充 `__post_init__` 缺失验证

目前 37 个字段仅 14 个被校验。至少应对剩余 10 个 callback 字段加 `callable()` 检查，对 Path 字段加 `isinstance(Path)` 检查。可在 `__post_init__` 末尾追加：

```python
# 批量 callback 校验
for _name in (
    "validate_project_map_fn", "validate_unique_legal_system_contract_fn",
    "policy_validate_fn", "get_policy_pack_fn",
    "governance_frozen_tuple_errors_fn", "event_contract_blocker_errors_fn",
    "git_registration_probe_fn", "truth_basis_for_scope_fn",
    "decision_refs_for_scope_fn", "lesson_refs_for_scope_fn",
):
    if not callable(getattr(self, _name)):
        raise TypeError(f"{_name} must be callable")

# 批量 Path 校验
for _name in (
    "project_map_governance", "event_log", "hook_contract_path",
):
    if not isinstance(getattr(self, _name), Path):
        raise TypeError(f"{_name} must be a Path")
```

### 建议 2：移除未使用的 `docs_refs_for_scope_fn` 或将其纳入回调分发

`_resolve_callbacks()` 返回 12 个 callback，但 `docs_refs_for_scope_fn`（第 33 个 callback）不在返回 dict 中。要么：
- 从 CoreConfig 中删除该字段，或
- 在 `_resolve_callbacks()` 中补上

### 建议 3：清理未消费的字段

`event_log`、`project_map_governance`、`core_evidence_refs` 传入 CoreConfig 后未被 `build_context_package_from_config` 或 `_resolve_callbacks` 消费。确认是否可以移除，或补充使用场景。

### 建议 4：`to_gateway_kwargs()` 增加 Path → str 转换

```python
def to_gateway_kwargs(self) -> dict[str, Any]:
    from dataclasses import asdict
    result = asdict(self)
    for key in ("host", "event", "project_scope", "surface_id", "workspace_id",
                "legality_source_policy", "registration_commit_policy", "registration_commit_phase"):
        pass  # str 字段无需转换
    # Path 字段转 str
    for key in ("cwd", "workspace_root", "repo_root", "project_map_governance",
                "event_log", "hook_contract_path"):
        if key in result and result[key] is not None:
            result[key] = str(result[key])
    return result
```

### 建议 5：考虑用 `__init_subclass__` 或 `Validator` pattern 简化 `__post_init__`

当前 `__post_init__` 用了大量重复的 `if not isinstance(...) raise TypeError` 模式。可以提取为一个验证元组列表：

```python
_VALIDATORS: ClassVar = [
    ("host", lambda v: v in ("codex", "claude"), "must be 'codex' or 'claude'"),
    ("event", lambda v: isinstance(v, str) and v, "must be a non-empty string"),
    # ...
]
```

循环执行，减少重复代码 60%+。
