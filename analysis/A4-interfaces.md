# A4: Interfaces 分析

> 分析对象：`workspace/tools/memory_hook_interfaces.py`（335 行）
> 对照实现：`workspace/tools/memory_hook_impls.py`（1251 行）

---

## 1. 接口清单

### 1.1 ABC 接口

| # | 接口名 | 抽象方法 | 设计意图 |
|---|--------|---------|----------|
| IF-1 | `HostDelegate` | `can_handle()`, `execute()`, `noop_response()` | 将 hook 事件委托给宿主运行时（Codex / Claude），提供能力探测、正式执行、降级兜底三件事 |
| IF-2 | `PolicyRegistry` | `get_policy()`, `validate()`, `get_policy_pack()`, `resolve_conflict()`, `validate_project_map()`, `validate_unique_legal_system_contract()`, `governance_frozen_tuple_errors()`, `event_contract_blocker_errors()`, `git_registration_probe()`, `truth_basis_for_scope()`, `decision_refs_for_scope()`, `lesson_refs_for_scope()`, `docs_refs_for_scope()` | 策略查询、策略包打包、冲突解决，以及大量与治理/事件合约/事实基准相关的校验方法 |
| IF-3 | `RouteTargetPolicy` | `resolve(kind)` | 将路由类别（kind）解析为目标路径 |
| IF-3 | `WriteTargetPolicy` | `get_targets()` | 获取所有写入目标的映射字典 |
| IF-3.5 | `GatewayBusinessPolicy` | 16 个抽象方法 + 1 个带默认实现的方法 | 网关编排层所需的宿主/业务策略：项目范围判定、canonical 映射、治理校验、scope 查找等 |
| IF-4 | `ArtifactSink` | `write()`, `ensure_dirs()` | 工件输出：将 artifact package 写入文件 |
| IF-4 | `ErrorSink` | `log()` | 错误日志记录 |
| IF-6 | `PathUtils` | `extract_excerpt()`, `write_targets()` | 路径相关工具回调：文件片段提取、写入目标映射 |

### 1.2 TypedDict

| 名称 | 字段 | 设计意图 |
|------|------|----------|
| `TruthBasis` | `refs`, `errors`, `validation`, `policy`, `project_ref`, `source_refs`, `authority_refs`, `evidence_refs`, `conflict_status` | 事实基准包的结构化契约，描述某一 scope 下的 truth model 所需的全部引用及校验状态 |
| `RegistrationCommitGate` | `phase`, `enforced`, `gate_event`, `triggered_on_current_event`, `enforcement_result`, `status` | 注册提交门控的探测结果，用于检查 git registration 的阶段与执行状态 |

---

## 2. 契约完整性

### 2.1 签名完整性

| 接口 | 评估 | 说明 |
|------|------|------|
| `HostDelegate` | ✅ 完整 | 三个方法职责清晰，签名与实现匹配 |
| `PolicyRegistry` | ⚠️ 签名正确但语义模糊 | `validate(context: dict[str, Any])` 的返回类型是 `list[str]`（错误列表），但输入是任意 dict，调用方无法从类型层面知道需要传哪些 key；`resolve_conflict()` 的 `ValueError` 在 docstring 中声明但方法签名没有用 `raises` 标注（Python 静态检查无法捕获） |
| `RouteTargetPolicy` | ✅ 完整 | 单一职责，签名精确 |
| `WriteTargetPolicy` | ⚠️ 返回类型过宽 | `get_targets() -> dict[str, Any]` 实际上返回的是已知结构的 dict，建议用 TypedDict 精确化 |
| `GatewayBusinessPolicy` | ⚠️ 存在不一致 | `get_required_gateway_inputs()` 有默认实现（非 abstract），但 `get_required_canonical()` 仍标记为 `@abstractmethod`，二者在语义上高度重叠（见下方改进建议 #4） |
| `ArtifactSink` | ⚠️ `write()` 返回类型模糊 | `dict[str, str]` 实际上返回 `{"snapshot": path, "latest": path}`，应使用 TypedDict |
| `ErrorSink` | ✅ 完整 | 方法简单，契约明确 |
| `PathUtils` | ⚠️ `write_targets()` 命名歧义 | 返回类型 `dict[str, Any]`，且与 `WriteTargetPolicy.get_targets()` 功能几乎相同，存在职责重叠 |

### 2.2 TypedDict 字段匹配

#### `TruthBasis`

- **接口声明的字段**：`refs`, `errors`, `validation`, `policy`, `project_ref`, `source_refs`, `authority_refs`, `evidence_refs`, `conflict_status`
- **`PolicyRegistryImpl` stub 实现**：返回 `{}` — 不匹配任何字段
- **`GatewayBusinessPolicyImpl` 实际返回**：除接口声明的 9 个字段外，还多返回了 `global_refs` 字段

```
Mismatch: GatewayBusinessPolicyImpl.truth_basis_for_scope() 返回了接口中不存在的 "global_refs" 字段
```

**结论**：`TruthBasis` 缺少 `global_refs` 字段定义，属于 `total=False` 的遗漏。

#### `RegistrationCommitGate`

- **接口声明的字段**：`phase`, `enforced`, `gate_event`, `triggered_on_current_event`, `enforcement_result`, `status`
- **`PolicyRegistryImpl` stub 实现**：返回 `{}` — 技术上合法（`total=False`），但不提供任何信息

**结论**：契约在技术上是正确的，但 stub 实现返回空 dict 使得调用方无法区分"门控未触发"和"门控已触发但未配置"。

---

## 3. 接口隔离（ISP 分析）

### 3.1 胖接口识别

| 接口 | 方法数 | 职责域 | ISP 评级 |
|------|--------|--------|----------|
| `HostDelegate` | 3 | 宿主委托 | ✅ 合理 |
| `PolicyRegistry` | 13 | 策略查询 + 治理校验 + 事实基准 | ❌ 胖接口 |
| `RouteTargetPolicy` | 1 | 路由解析 | ✅ 合理 |
| `WriteTargetPolicy` | 1 | 写入目标 | ✅ 合理 |
| `GatewayBusinessPolicy` | 17 | 项目解析 + canonical 管理 + 治理校验 + scope 查找 | ❌ 胖接口 |
| `ArtifactSink` | 2 | 工件写入 | ✅ 合理 |
| `ErrorSink` | 1 | 错误日志 | ✅ 合理 |
| `PathUtils` | 2 | 路径工具 | ⚠️ 混合职责 |

### 3.2 具体问题

**`PolicyRegistry` 职责混杂**：
- 核心策略操作：`get_policy()`, `validate()`, `get_policy_pack()`, `resolve_conflict()` — 4 个方法
- 治理校验：`validate_project_map()`, `validate_unique_legal_system_contract()`, `governance_frozen_tuple_errors()`, `event_contract_blocker_errors()` — 4 个方法
- 事实基准/引用查找：`truth_basis_for_scope()`, `decision_refs_for_scope()`, `lesson_refs_for_scope()`, `docs_refs_for_scope()` — 4 个方法
- Git 注册探测：`git_registration_probe()` — 1 个方法

这四组职责关注点完全不同。`PolicyRegistryImpl` 的治理/基准方法全是 stub，注释写着"Real impl delegates to GatewayBusinessPolicy"，说明这些方法本就不该属于 `PolicyRegistry`。

**`GatewayBusinessPolicy` 与 `PolicyRegistry` 方法重叠**：

| 重叠方法 | `PolicyRegistry` | `GatewayBusinessPolicy` |
|----------|-----------------|------------------------|
| `truth_basis_for_scope()` | ✓ | ✓ |
| `decision_refs_for_scope()` | ✓ | ✓ |
| `lesson_refs_for_scope()` | ✓ | ✓ |
| `docs_refs_for_scope()` | ✓ | ✓ |
| `validate_project_map()` / `validate_project_map_files()` | ✓ | ✓ |
| `validate_unique_legal_system_contract()` | ✓ | ✓ |
| `governance_frozen_tuple_errors()` / `governance_frozen_tuple_blocker_errors()` | ✓ | ✓ |
| `event_contract_blocker_errors()` | ✓ | ✓ |

8 对方法名高度相似（部分有 `_files` / `_blocker` 后缀差异），说明两个接口在演进过程中产生了重复定义。

**`PathUtils.write_targets()` 与 `WriteTargetPolicy.get_targets()`**：
- 两者返回相同结构的 dict
- 两者实现完全一致（硬编码相同的路径映射）
- 应该统一为一个接口

---

## 4. 与实现的关系

### 4.1 实现矩阵

| 实现类 | 实现的接口 | 所在文件 | 备注 |
|--------|-----------|----------|------|
| `CodexDelegate` | `HostDelegate` | `memory_hook_impls.py` | 完整实现 |
| `ClaudeDelegate` | `HostDelegate` | `memory_hook_impls.py` | 完整实现，依赖注入丰富 |
| `PolicyRegistryImpl` | `PolicyRegistry` | `memory_hook_impls.py` | 核心策略完整；治理/基准方法为 stub |
| `RouteTargetPolicyImpl` | `RouteTargetPolicy` | `memory_hook_impls.py` | 完整实现 |
| `WriteTargetPolicyImpl` | `WriteTargetPolicy` | `memory_hook_impls.py` | 完整实现 |
| `GatewayBusinessPolicyConfig` | 无（dataclass） | `memory_hook_impls.py` | 配置载荷，40+ 字段 |
| `GatewayBusinessPolicyImpl` | `GatewayBusinessPolicy` | `memory_hook_impls.py` | 完整实现，含大量校验逻辑 |
| `ArtifactSinkImpl` | `ArtifactSink` | `memory_hook_impls.py` | 完整实现 |
| `ErrorSinkImpl` | `ErrorSink` | `memory_hook_impls.py` | 完整实现 |
| `PathUtilsImpl` | `PathUtils` | `memory_hook_impls.py` | 完整实现 |
| `ArtifactWriter` | 无（组合类） | `memory_hook_impls.py` | 包装 `ArtifactSinkImpl`，加非阻塞错误处理 |
| `DelegateRouter` | 无（组合类） | `memory_hook_impls.py` | 路由 `CodexDelegate` / `ClaudeDelegate` |
| `NeutralGatewayBusinessPolicy` | `GatewayBusinessPolicy`（间接） | `neutral_policy.py` | 继承 `GatewayBusinessPolicyImpl` |
| `WorkbotGatewayBusinessPolicy` | `GatewayBusinessPolicy`（间接） | `workbot_policy.py` | 继承 `NeutralGatewayBusinessPolicy` |

### 4.2 未被实现的接口方法

- `PolicyRegistry` 的治理/基准方法在 `PolicyRegistryImpl` 中全部是 stub（返回空列表/空 dict），注释明确表示应由 `GatewayBusinessPolicy` 负责
- 这意味着 `PolicyRegistry` 接口上实际有 **8 个方法是"名义上抽象但实现为空"** 的

---

## 5. 改进建议

### 建议 1：拆分 `PolicyRegistry` 胖接口

将 `PolicyRegistry` 拆分为三个独立接口：

```
PolicyRegistry        → get_policy(), validate(), get_policy_pack(), resolve_conflict()
GovernanceValidator   → validate_project_map(), validate_unique_legal_system_contract(),
                        governance_frozen_tuple_errors(), event_contract_blocker_errors()
ScopeRefProvider      → truth_basis_for_scope(), decision_refs_for_scope(),
                        lesson_refs_for_scope(), docs_refs_for_scope()
```

`git_registration_probe()` 可归入 `GovernanceValidator` 或单独为 `RegistrationProbe`。

### 建议 2：消除 `PolicyRegistry` 与 `GatewayBusinessPolicy` 的方法重叠

两个接口共享 8 对同名/近名方法。建议在 `PolicyRegistry` 中移除这些方法，调用方直接依赖 `GatewayBusinessPolicy`（或上面的 `GovernanceValidator` + `ScopeRefProvider`）。当前 `PolicyRegistryImpl` 的 stub 已经证明了这些方法不在策略注册表的职责范围内。

### 建议 3：用 TypedDict 精确化返回类型

以下方法的返回类型应从 `dict[str, Any]` 改为精确的 TypedDict：

| 方法 | 当前返回类型 | 建议 |
|------|-------------|------|
| `WriteTargetPolicy.get_targets()` | `dict[str, Any]` | 新增 `WriteTargets` TypedDict |
| `ArtifactSink.write()` | `dict[str, str]` | 新增 `ArtifactWriteResult` TypedDict (`snapshot: str`, `latest: str`) |
| `PathUtils.write_targets()` | `dict[str, Any]` | 复用上述 `WriteTargets` TypedDict |
| `PolicyRegistry.get_policy_pack()` | `dict[str, Any]` | 新增 `PolicyPack` TypedDict |

### 建议 4：清理 `GatewayBusinessPolicy.get_required_gateway_inputs()` 的默认实现

该方法有默认实现（调用 `get_required_canonical()`），但 `get_required_canonical()` 仍是 `@abstractmethod`。如果默认实现足以满足所有子类，应将 `get_required_canonical()` 改为带默认实现的普通方法并标记 `get_required_gateway_inputs()` 为 deprecated；反之如果子类必须覆盖 `get_required_canonical()`，则去掉 `get_required_gateway_inputs()` 的默认实现，让子类也实现它。当前的"半抽象半具体"状态会让子类作者困惑。

### 建议 5：统一 `write_targets` 相关职责

`PathUtils.write_targets()` 与 `WriteTargetPolicy.get_targets()` 返回相同结构、使用相同硬编码逻辑。建议：

- 删除 `PathUtils.write_targets()` 方法
- 在需要 write targets 的地方统一注入 `WriteTargetPolicy`
- 或将 `WriteTargetPolicy` 作为 `PathUtils` 的构造参数，让 `PathUtils` 委托给它
